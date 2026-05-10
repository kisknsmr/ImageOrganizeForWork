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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, ImageOps

from .config import config
from .database import DatabaseManager
from .services.scan_analyze_service import run_analyze, run_full_hash, run_scan
from .services import organize_service
from .services import separate_service
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


class BatchTrashRequest(BaseModel):
    file_ids: list[int]


class MoveFileRequest(BaseModel):
    destination_folder: str = Field(..., min_length=1)


class BatchMoveRequest(BaseModel):
    file_ids: list[int]
    destination_folder: str = Field(..., min_length=1)


class CreateFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


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
        self._stop_requested = False

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def request_stop(self) -> bool:
        with self._lock:
            if not self._state.running:
                return False
            self._stop_requested = True
            self._state.message = "中止リクエスト受付中..."
            return True

    def should_stop(self) -> bool:
        with self._lock:
            return self._stop_requested

    def start(self, kind: str, target, *args) -> None:
        with self._lock:
            if self._state.running:
                raise RuntimeError(f"{self._state.kind} is already running")
            self._stop_requested = False
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
                if self._stop_requested:
                    self._state.message = "中止しました"
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_scanner(root_path: str) -> None:
    run_scan(db, root_path=root_path, status_cb=jobs.set_status, percent_cb=jobs.set_percent, should_stop=jobs.should_stop)


def _run_analyzer() -> None:
    run_analyze(db, status_cb=jobs.set_status, progress_cb=jobs.set_progress, should_stop=jobs.should_stop)


def _run_full_hash_job() -> None:
    run_full_hash(db, status_cb=jobs.set_status, progress_cb=jobs.set_progress, should_stop=jobs.should_stop)


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


@app.post("/api/analyze/full-hash/start")
def full_hash_start() -> dict:
    pending = db.get_files_needing_full_hash(limit=1)
    if not pending:
        return {"started": False, "message": "完全ハッシュの対象がありません。", "job": jobs.snapshot()}
    try:
        jobs.start("full_hash", _run_full_hash_job)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"started": True, "job": jobs.snapshot()}


@app.post("/api/job/stop")
def job_stop() -> dict:
    ok = jobs.request_stop()
    if not ok:
        return {"ok": False, "message": "実行中のジョブがありません"}
    return {"ok": True, "message": "中止リクエストを送信しました。現在処理中のファイルが完了次第、停止します。"}


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


@app.post("/api/files/{file_id}/trash")
def move_file_to_trash(file_id: int) -> dict:
    ok = db.move_to_trash(file_id)
    if not ok:
        raise HTTPException(status_code=400, detail="failed to move file to trash")
    return {"ok": True}


@app.post("/api/files/{file_id}/move")
def move_file(file_id: int, payload: MoveFileRequest) -> dict:
    row = db.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    folder = os.path.normpath(payload.destination_folder)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=400, detail="destination folder does not exist")
    ok = db.move_file_to_folder(file_id, row["path"], folder)
    if not ok:
        raise HTTPException(status_code=400, detail="failed to move file")
    return {"ok": True, "file": db.get_file_by_id(file_id)}


@app.post("/api/files/batch-move")
def batch_move(payload: BatchMoveRequest) -> dict:
    folder = os.path.normpath(payload.destination_folder)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=400, detail="destination folder does not exist")
    moved = 0
    failed: list[int] = []
    for file_id in payload.file_ids:
        row = db.get_file_by_id(file_id)
        if not row:
            failed.append(file_id)
            continue
        if db.move_file_to_folder(file_id, row["path"], folder):
            moved += 1
        else:
            failed.append(file_id)
    return {"ok": True, "moved": moved, "failed_ids": failed}


@app.post("/api/files/batch-trash")
def batch_move_to_trash(payload: BatchTrashRequest) -> dict:
    moved = 0
    failed: list[int] = []
    for file_id in payload.file_ids:
        if db.move_to_trash(file_id):
            moved += 1
        else:
            failed.append(file_id)
    return {"ok": True, "moved": moved, "failed_ids": failed}


@app.delete("/api/files/{file_id}")
def delete_file_record(file_id: int) -> dict:
    ok = db.delete_file_record(file_id)
    if not ok:
        raise HTTPException(status_code=400, detail="failed to delete file record")
    return {"ok": True}


@app.get("/api/files/{file_id}/permanent-delete-check")
def permanent_delete_check(file_id: int) -> dict:
    return {
        "allowed": db.is_permanent_delete_allowed(file_id),
        "blocked_reason": db.permanent_delete_blocked_reason(file_id),
    }


@app.post("/api/files/{file_id}/permanent-delete")
def permanent_delete(file_id: int) -> dict:
    block = db.permanent_delete_blocked_reason(file_id)
    if block:
        raise HTTPException(status_code=400, detail=block)
    ok = db.permanently_delete_file(file_id, force=False)
    if not ok:
        raise HTTPException(status_code=400, detail="failed to permanently delete file")
    return {"ok": True}


@app.get("/api/folders")
def folders() -> dict:
    tree = db.get_folder_tree()
    folder_list = sorted(tree.keys())
    return {"folders": folder_list}


@app.post("/api/folders")
def create_folder(payload: CreateFolderRequest) -> dict:
    path = os.path.normpath(payload.path.strip())
    if not path or path in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid folder path")
    invalid_chars = set('<>"|?*') if os.name == "nt" else set("\x00")
    if any(c in invalid_chars for c in path):
        raise HTTPException(status_code=400, detail="folder path contains invalid characters")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"failed to create folder: {exc}") from exc
    return {"ok": True, "path": path}


@app.get("/api/tiny")
def tiny_files(max_size: int = Query(50 * 1024, ge=1, le=50 * 1024 * 1024)) -> dict:
    """指定バイト以下のファイル一覧を返す"""
    rows = db.get_tiny_files(max_size)
    return {"items": rows, "max_size": max_size}


class SaveSettingRequest(BaseModel):
    key: str = Field(..., min_length=1)
    value: str


# --------------------------------------------------------------------------- #
# Separate エンドポイント（画像・動画分離）
# --------------------------------------------------------------------------- #

class SeparatePreviewRequest(BaseModel):
    source_root: str
    image_dest: str
    video_dest: str


class SeparateApplyRequest(BaseModel):
    items: list[dict]


@app.post("/api/separate/preview")
def separate_preview(payload: SeparatePreviewRequest) -> dict:
    if not os.path.isdir(payload.source_root):
        raise HTTPException(status_code=400, detail=f"source_root が存在しません: {payload.source_root}")
    items = separate_service.preview(
        source_root=payload.source_root,
        image_dest=payload.image_dest,
        video_dest=payload.video_dest,
    )
    image_count = sum(1 for i in items if i.kind == "image")
    video_count = sum(1 for i in items if i.kind == "video")
    return {
        "items": [{"src": i.src, "dst": i.dst, "kind": i.kind, "rel_path": i.rel_path} for i in items],
        "image_count": image_count,
        "video_count": video_count,
    }


@app.post("/api/separate/apply")
def separate_apply(payload: SeparateApplyRequest) -> dict:
    return separate_service.apply(payload.items)


@app.get("/api/separate/progress")
def separate_progress() -> dict:
    return separate_service.get_progress()


@app.post("/api/separate/undo")
def separate_undo() -> dict:
    return separate_service.undo()


@app.get("/api/separate/undo/status")
def separate_undo_status() -> dict:
    return {"can_undo": separate_service.can_undo()}


@app.post("/api/db/reset-analysis")
def db_reset_analysis() -> dict:
    """blur_score・サムネ・ハッシュをリセットして全ファイルを未解析状態に戻す。"""
    count = db.reset_blur_scores()
    return {"ok": True, "reset": count}


@app.post("/api/db/clear-all")
def db_clear_all() -> dict:
    """files・thumbnails を全消去する。スキャンからやり直す場合に使用。"""
    count = db.clear_all_files()
    return {"ok": True, "cleared": count}


@app.get("/api/settings")
def get_settings() -> dict:
    keys = ["root_path", "trash_retention_days", "blur_threshold", "similarity_threshold"]
    return {k: db.get_setting(k) for k in keys}


@app.post("/api/settings")
def save_setting(payload: SaveSettingRequest) -> dict:
    db.set_setting(payload.key, payload.value)
    return {"ok": True}


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


# --------------------------------------------------------------------------- #
# Organize エンドポイント
# --------------------------------------------------------------------------- #

class OrganizeConfig(BaseModel):
    time_gap_hours: float = Field(4.0, ge=0.5, le=72.0)
    confidence_threshold: float = Field(0.25, ge=0.0, le=1.0)
    sample_per_group: int = Field(3, ge=1, le=10)


class OrganizeSuggestRequest(BaseModel):
    target_path: str
    destination_root: str
    config: OrganizeConfig = OrganizeConfig()


class OrganizeApplyItem(BaseModel):
    path: str


class OrganizeApplyGroup(BaseModel):
    group_id: str
    suggested_name: str
    items: list[OrganizeApplyItem]


class OrganizeApplyRequest(BaseModel):
    destination_root: str
    plan: list[OrganizeApplyGroup]


@app.post("/api/organize/suggest")
def organize_suggest(payload: OrganizeSuggestRequest) -> dict:
    target = payload.target_path
    if not os.path.isdir(target):
        raise HTTPException(status_code=400, detail=f"target_path が存在しないか、ディレクトリではありません: {target}")
    if not os.path.isabs(payload.destination_root):
        raise HTTPException(status_code=400, detail="destination_root は絶対パスで指定してください")

    # DB からスキャン済みファイルを取得（target_path 配下かつ解析済み）
    all_files = db.get_all_files_with_info()
    target_norm = os.path.normpath(target)
    files = []
    for f in all_files:
        path_norm = os.path.normpath(f["path"])
        if path_norm.startswith(target_norm + os.sep) or path_norm == target_norm:
            row = db.get_file_by_id(f["id"])
            if row and row.get("status") not in ("trash",) and row.get("blur_score") is not None:
                files.append(row)

    if not files:
        return {"suggestions": [], "message": "対象ファイルが見つかりませんでした（スキャン・解析済みのファイルのみ対象です）"}

    cfg = payload.config
    suggestions = organize_service.generate_suggestions(
        files=files,
        destination_root=payload.destination_root,
        time_gap_hours=cfg.time_gap_hours,
        confidence_threshold=cfg.confidence_threshold,
        sample_per_group=cfg.sample_per_group,
    )

    return {
        "suggestions": [
            {
                "group_id": s.group_id,
                "suggested_name": s.suggested_name,
                "reason": s.reason,
                "date_range": s.date_range,
                "items": s.items,
            }
            for s in suggestions
        ]
    }


@app.post("/api/organize/apply")
def organize_apply(payload: OrganizeApplyRequest) -> dict:
    dest = payload.destination_root
    if not os.path.isabs(dest):
        raise HTTPException(status_code=400, detail="destination_root は絶対パスで指定してください")
    plan = [
        {"group_id": g.group_id, "suggested_name": g.suggested_name,
         "items": [{"path": i.path} for i in g.items]}
        for g in payload.plan
    ]
    result = organize_service.apply_suggestions(plan=plan, destination_root=dest)
    return result


@app.post("/api/organize/undo")
def organize_undo() -> dict:
    return organize_service.undo_last_apply()


@app.get("/api/organize/undo/status")
def organize_undo_status() -> dict:
    return {"can_undo": organize_service.can_undo()}


@app.get("/api/organize/presets")
def organize_presets() -> dict:
    return {"labels": organize_service.load_presets()}


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
