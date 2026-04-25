"""
PhotoSortX v3 API server.

既存の Python コアを Tauri / React フロントエンドから呼び出すための薄い FastAPI ラッパー。
起動例:
    uvicorn src.api_server:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import asyncio
import io
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal, Optional

import cv2
from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from PIL import Image, ImageOps

from .config import config
from .database import DatabaseManager
from .services.scan_analyze_service import run_analyze, run_scan
from .utils import hamming_dist


TRIAGE_ACTIONS = {"keep", "discard", "skip"}


class ScanStartRequest(BaseModel):
    root_path: str = Field(..., min_length=1)


class TriageRequest(BaseModel):
    action: Optional[Literal["keep", "discard", "skip"]] = None


class BatchTriageItem(BaseModel):
    id: int
    action: Optional[Literal["keep", "discard", "skip"]] = None


class BatchTriageRequest(BaseModel):
    items: list[BatchTriageItem]


@dataclass
class JobState:
    kind: str = "idle"
    running: bool = False
    current: int = 0
    total: int = 0
    percent: int = 0
    message: str = "待機中"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = JobState()

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def start(self, kind: str, target, *args) -> None:
        with self._lock:
            if self._state.running:
                raise RuntimeError(f"{self._state.kind} is already running")
            self._state = JobState(kind=kind, running=True, message="開始中...", started_at=time.time())

        thread = threading.Thread(target=self._run, args=(target, args), daemon=True)
        thread.start()

    def _run(self, target, args) -> None:
        try:
            target(*args)
            with self._lock:
                self._state.running = False
                self._state.percent = 100
                self._state.finished_at = time.time()
        except Exception as exc:
            with self._lock:
                self._state.running = False
                self._state.error = str(exc)
                self._state.message = f"エラー: {exc}"
                self._state.finished_at = time.time()

    def set_status(self, message: str) -> None:
        with self._lock:
            self._state.message = message

    def set_percent(self, percent: int) -> None:
        with self._lock:
            self._state.percent = max(0, min(100, int(percent)))

    def set_progress(self, current: int, total: int) -> None:
        with self._lock:
            self._state.current = int(current)
            self._state.total = int(total)
            self._state.percent = int(current / total * 100) if total else 0


db = DatabaseManager()
jobs = JobManager()
app = FastAPI(title="PhotoSortX API", version="3.0.0")


def _run_scanner(root_path: str) -> None:
    run_scan(db, root_path=root_path, status_cb=jobs.set_status, percent_cb=jobs.set_percent)


def _run_analyzer() -> None:
    run_analyze(db, status_cb=jobs.set_status, progress_cb=jobs.set_progress)


def _image_preview_bytes(path: str, max_size: int = 1920) -> bytes:
    if not config.validate_path(path) or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")

    ext = os.path.splitext(path)[1].lower()
    if ext in config.VIDEO_EXTENSIONS:
        return _video_preview_bytes(path, max_size)

    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=88, optimize=True)
            return buf.getvalue()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"preview generation failed: {exc}") from exc


def _video_preview_bytes(path: str, max_size: int) -> bytes:
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise HTTPException(status_code=422, detail="video open failed")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise HTTPException(status_code=422, detail="video frame read failed")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    finally:
        cap.release()


def _similar_groups(distance: int, max_items: int) -> list[dict]:
    rows = db.get_files_with_phash()[:max_items]
    items = []
    for fid, path, phash, _mtime, size in rows:
        if not phash:
            continue
        try:
            items.append({"id": fid, "path": path, "hash": int(phash, 16), "size": size})
        except (TypeError, ValueError):
            continue

    visited: set[int] = set()
    groups: list[dict] = []
    for item in items:
        if item["id"] in visited:
            continue
        members = [other for other in items if other["id"] not in visited and hamming_dist(item["hash"], other["hash"]) <= distance]
        if len(members) < 2:
            continue
        for member in members:
            visited.add(member["id"])
        groups.append(_group_payload(members))
    return groups


def _group_payload(members: list[dict]) -> dict:
    enriched = []
    for member in members:
        file_row = db.get_file_by_id(member["id"])
        if file_row:
            enriched.append(file_row)
    best = _best_shot(enriched)
    return {
        "id": ",".join(str(item["id"]) for item in enriched),
        "count": len(enriched),
        "best_id": best["id"] if best else None,
        "items": enriched,
    }


def _best_shot(items: list[dict]) -> Optional[dict]:
    if not items:
        return None
    return max(items, key=lambda item: (float(item.get("blur_score") or 0), int(item.get("size") or 0)))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": "3.0.0", "stats": db.get_library_stats()}


@app.get("/api/library/stats")
def library_stats() -> dict:
    return db.get_library_stats()


@app.post("/api/scan/start")
def scan_start(payload: ScanStartRequest) -> dict:
    root_path = os.path.normpath(payload.root_path)
    if not os.path.isdir(root_path):
        raise HTTPException(status_code=400, detail="root_path is not a directory")
    try:
        jobs.start("scan", _run_scanner, root_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jobs.snapshot()


@app.get("/api/scan/status")
def scan_status() -> dict:
    return jobs.snapshot()


@app.post("/api/analyze/start")
def analyze_start() -> dict:
    if db.get_unprocessed_count() == 0:
        return {"started": False, "message": "解析対象のファイルがありません。", "job": jobs.snapshot()}
    try:
        jobs.start("analyze", _run_analyzer)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"started": True, "job": jobs.snapshot()}


@app.get("/api/files")
def files(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    triage_status: Optional[Literal["keep", "discard", "skip"]] = None,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    untriaged_only: bool = False,
    include_trash: bool = False,
) -> dict:
    return db.get_files_page(
        page=page,
        limit=limit,
        triage_status=triage_status,
        include_trash=include_trash,
        content_type=content_type,
        status=status,
        untriaged_only=untriaged_only,
    )


@app.get("/api/files/{file_id}")
def file_detail(file_id: int) -> dict:
    row = db.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    return row


@app.get("/api/files/{file_id}/thumbnail")
def file_thumbnail(file_id: int) -> Response:
    blob = db.get_thumbnail(file_id)
    if not blob:
        raise HTTPException(status_code=404, detail="thumbnail not found")
    return Response(content=blob, media_type="image/jpeg")


@app.get("/api/files/{file_id}/preview")
def file_preview(file_id: int, max_size: int = Query(1920, ge=320, le=4096)) -> Response:
    row = db.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    return Response(content=_image_preview_bytes(row["path"], max_size), media_type="image/jpeg")


@app.post("/api/files/{file_id}/triage")
def triage_file(file_id: int, payload: TriageRequest) -> dict:
    ok = db.update_triage_status(file_id, payload.action)
    if not ok:
        raise HTTPException(status_code=404, detail="file not found or invalid action")
    return {"ok": True, "file": db.get_file_by_id(file_id)}


@app.post("/api/files/batch-triage")
def batch_triage(payload: BatchTriageRequest) -> dict:
    updated = db.batch_update_triage_status([(item.id, item.action) for item in payload.items])
    return {"ok": True, "updated": updated}


@app.get("/api/triage/next")
def triage_next(after_id: int = Query(0, ge=0)) -> dict:
    row = db.get_next_triage_file(after_id=after_id)
    return {"item": row}


@app.get("/api/duplicates")
def duplicates(use_full_hash: bool = False) -> dict:
    groups = []
    for hash_value, count in db.get_duplicate_hashes(use_full_hash=use_full_hash):
        rows = db.get_files_by_hash(hash_value, use_full_hash=use_full_hash)
        groups.append({
            "hash": hash_value,
            "count": count,
            "items": [db.get_file_by_id(row[0]) for row in rows],
        })
    return {"groups": groups}


@app.get("/api/blurry")
def blurry(threshold: int = Query(config.DEFAULT_BLUR_THRESHOLD, ge=1, le=1000)) -> dict:
    rows = db.get_blurry_files(threshold)
    return {"items": [db.get_file_by_id(fid) for fid, _path in rows]}


@app.get("/api/similar")
def similar(
    distance: int = Query(config.DEFAULT_SIMILARITY_THRESHOLD, ge=0, le=config.MAX_SIMILARITY_DISTANCE),
    max_items: int = Query(5000, ge=1, le=50000),
) -> dict:
    groups = _similar_groups(distance, max_items)
    return {"distance": distance, "groups": groups}


@app.get("/api/similar/{group_id}/best")
def similar_best(group_id: str) -> dict:
    try:
        ids = [int(part) for part in group_id.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="group_id must be comma-separated file ids") from exc
    items = [row for fid in ids if (row := db.get_file_by_id(fid))]
    best = _best_shot(items)
    if not best:
        raise HTTPException(status_code=404, detail="group not found")
    return {"best": best}


@app.websocket("/ws/progress")
async def progress_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(jobs.snapshot())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


def main() -> None:
    import uvicorn

    uvicorn.run("src.api_server:app", host="127.0.0.1", port=8765, reload=False)
