"""
PhotoSortX v3 API server.

既存の Python コアを Tauri / React フロントエンドから呼び出すための薄い FastAPI ラッパー。
起動例:
    uvicorn src.api_server:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import io
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, ImageOps

from .config import config
from .database import DatabaseManager
from .services import organize_service
from .services.duplicate_service import run_full_hash
from .services.preprocess_service import run_preprocess, summarize_folder
from .services.scan_analyze_service import count_disk_files, run_analyze, run_scan


TRIAGE_ACTIONS = {"keep", "discard", "skip"}


class ScanStartRequest(BaseModel):
    root_path: str = Field(..., min_length=1)


class PreprocessStartRequest(BaseModel):
    """振り分けの開始。mode=full はカテゴリフォルダの中も見直す。"""
    root_path: str = Field(..., min_length=1)
    mode: Literal["incremental", "full"] = "incremental"


class LibraryClearRequest(BaseModel):
    """読み込み記録の消去。current = 現在のライブラリのみ / all = 全記録。"""
    scope: Literal["current", "all"] = "current"
    root_path: Optional[str] = None


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


class SettingsUpdateRequest(BaseModel):
    trash_folder: Optional[str] = None


class OrganizeApplyGroup(BaseModel):
    name: str = Field(..., min_length=1)
    file_ids: list[int] = Field(..., min_length=1)


class OrganizeApplyRequest(BaseModel):
    destination_root: str = Field(..., min_length=1)
    groups: list[OrganizeApplyGroup] = Field(..., min_length=1)


@dataclass
class JobState:
    kind: str = "idle"
    running: bool = False
    #: 実行中だがユーザー操作で待機している状態
    paused: bool = False
    current: int = 0
    total: int = 0
    percent: int = 0
    message: str = "待機中"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = JobState()
        # set() = 動作中 / clear() = 一時停止中。ワーカーはこれを待つ
        self._resume = threading.Event()
        self._resume.set()
        self._cancelled = False

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def start(self, kind: str, target, *args) -> None:
        with self._lock:
            if self._state.running:
                raise RuntimeError(f"{self._state.kind} is already running")
            self._state = JobState(kind=kind, running=True, message="開始中...", started_at=time.time())
            self._cancelled = False
            self._resume.set()

        thread = threading.Thread(target=self._run, args=(target, args), daemon=True)
        thread.start()

    # --- 一時停止・中止 ------------------------------------------------
    def pause(self) -> bool:
        with self._lock:
            if not self._state.running or self._state.paused:
                return False
            self._state.paused = True
            self._resume.clear()
            self._state.message = "一時停止中"
            return True

    def resume(self) -> bool:
        with self._lock:
            if not self._state.running or not self._state.paused:
                return False
            self._state.paused = False
            self._state.message = "再開しました"
            self._resume.set()
            return True

    def cancel(self) -> bool:
        with self._lock:
            if not self._state.running:
                return False
            self._cancelled = True
            self._state.paused = False
            self._state.message = "停止中..."
        # 一時停止中に中止された場合、待っているワーカーを起こす
        self._resume.set()
        return True

    def should_stop(self) -> bool:
        with self._lock:
            return self._cancelled

    def wait_if_paused(self) -> None:
        """一時停止中はここで待つ。中止されると待機は解除される。"""
        self._resume.wait()

    def _run(self, target, args) -> None:
        try:
            target(*args)
            with self._lock:
                self._state.running = False
                self._state.paused = False
                # 中止された場合は進捗を 100% に書き換えない（途中で終わっている）
                if not self._cancelled:
                    self._state.percent = 100
                self._state.finished_at = time.time()
        except Exception as exc:
            with self._lock:
                self._state.running = False
                self._state.paused = False
                self._state.error = str(exc)
                self._state.message = f"エラー: {exc}"
                self._state.finished_at = time.time()
        finally:
            # 次のジョブが一時停止状態から始まらないようにする
            self._resume.set()

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

    def reset(self) -> bool:
        """
        完了済みジョブの結果を破棄して待機中に戻す。

        結果を保持したままだと、画面に前回の実行結果がいつまでも残り続ける。
        実行中は破棄しない（進捗表示が消えてしまうため）。
        """
        with self._lock:
            if self._state.running:
                return False
            self._state = JobState()
            return True

    def set_result(self, result: dict) -> None:
        with self._lock:
            self._state.result = result


db = DatabaseManager()
jobs = JobManager()
app = FastAPI(title="PhotoSortX API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost", "https://tauri.localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_scanner(root_path: str) -> None:
    run_scan(db, root_path=root_path, status_cb=jobs.set_status, percent_cb=jobs.set_percent)


def _run_analyzer() -> None:
    result = run_analyze(
        db,
        status_cb=jobs.set_status,
        progress_cb=jobs.set_progress,
        should_stop=jobs.should_stop,
        wait_if_paused=jobs.wait_if_paused,
    )
    jobs.set_result(result)


def _run_preprocessor(root_path: str, full: bool) -> None:
    result = run_preprocess(
        root_path, status_cb=jobs.set_status, progress_cb=jobs.set_progress, full=full
    )
    jobs.set_result(result)
    if not result.get("stopped"):
        recheck = f"・見直し移動{result['rechecked']}件" if result.get("rechecked") else ""
        message = (
            f"完了: 全{result['all_files']}件中 移動{result['moved']}件"
            f"（Pictures {result['pictures']} / Movies {result['movies']} / Others {result['others']}）"
            f"{recheck}・対応不要{result['already_sorted']}件・スキップ{result['skipped']}件"
        )
        jobs.set_status(message)


def _run_full_hash() -> None:
    result = run_full_hash(db, status_cb=jobs.set_status, progress_cb=jobs.set_progress)
    jobs.set_result(result)


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


def _similar_groups(distance: int, max_items: int) -> tuple[list[dict], int, int]:
    """
    pHash のハミング距離が distance 以下の画像をグループ化する。

    Returns:
        (groups, scanned, available) — scanned は実際に比較した件数、
        available は打ち切り前の候補総数。max_items で切られたことを UI に伝える。
    """
    all_rows = db.get_files_with_phash()
    available = len(all_rows)
    rows = all_rows[:max_items]

    ids: list[int] = []
    hashes: list[int] = []
    for fid, _path, phash, _mtime, _size in rows:
        try:
            hashes.append(int(phash, 16))
        except (TypeError, ValueError):
            continue
        ids.append(fid)

    scanned = len(ids)
    if scanned == 0:
        return [], 0, available

    # 総当たりだが、XOR と popcount を numpy でベクトル化して 1 シード 1 回の演算にする。
    # Python ループで hamming_dist を呼ぶと 5000 件で 2500 万回の関数呼び出しになる。
    hash_arr = np.array(hashes, dtype=np.uint64)

    visited = np.zeros(scanned, dtype=bool)
    groups: list[dict] = []
    for i in range(scanned):
        if visited[i]:
            continue
        dist = np.bitwise_count(np.bitwise_xor(hash_arr, hash_arr[i]))
        member_idx = np.flatnonzero((dist <= distance) & ~visited)
        if member_idx.size < 2:
            continue
        visited[member_idx] = True
        groups.append(_group_payload([{"id": ids[j]} for j in member_idx]))
    return groups, scanned, available


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
    # 走査完了を待たずに現在のライブラリを切り替える。
    # 完了時にしか保存しないと、途中でエラー/中断したときに
    # フォルダを変えたのに Home が前のライブラリを表示し続けてしまう。
    db.set_setting("root_path", root_path)
    try:
        jobs.start("scan", _run_scanner, root_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jobs.snapshot()


@app.get("/api/scan/status")
def scan_status() -> dict:
    return jobs.snapshot()


@app.post("/api/preprocess/start")
def preprocess_start(payload: PreprocessStartRequest) -> dict:
    root_path = os.path.normpath(payload.root_path)
    if not os.path.isdir(root_path):
        raise HTTPException(status_code=400, detail="root_path is not a directory")
    try:
        jobs.start("preprocess", _run_preprocessor, root_path, payload.mode == "full")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jobs.snapshot()


@app.post("/api/jobs/pause")
def jobs_pause() -> dict:
    """実行中のジョブを一時停止する。停止はバッチ境界で効く。"""
    if not jobs.pause():
        raise HTTPException(status_code=409, detail="no running job to pause")
    return jobs.snapshot()


@app.post("/api/jobs/resume")
def jobs_resume() -> dict:
    if not jobs.resume():
        raise HTTPException(status_code=409, detail="job is not paused")
    return jobs.snapshot()


@app.post("/api/jobs/cancel")
def jobs_cancel() -> dict:
    """実行中のジョブを中止する。処理済みの分は DB に残る。"""
    if not jobs.cancel():
        raise HTTPException(status_code=409, detail="no running job to cancel")
    return jobs.snapshot()


@app.post("/api/jobs/reset")
def jobs_reset() -> dict:
    """直前のジョブ結果の表示を消す（実行中は不可）。"""
    if not jobs.reset():
        raise HTTPException(status_code=409, detail="job is still running")
    return jobs.snapshot()


@app.get("/api/preprocess/check")
def preprocess_check(root_path: str, mode: Literal["incremental", "full"] = "incremental") -> dict:
    """
    振り分け対象の件数と内訳を事前に返す。

    スキャン用の /api/scan/check とは対象範囲が異なる（あちらは対応拡張子のみ・
    カテゴリフォルダの中も含む）。実行結果と数が食い違わないよう、
    run_preprocess と同じ collect_targets を使う。
    """
    root = os.path.normpath(root_path)
    valid = os.path.isdir(root)
    if not valid:
        return {"root_path": root, "valid": False, "all_files": 0, "total": 0,
                "unsorted": 0, "misplaced": 0, "already_sorted": 0,
                "full": mode == "full", "pictures": 0, "movies": 0, "others": 0}
    return {"root_path": root, "valid": True, **summarize_folder(root, mode == "full")}


@app.get("/api/scan/check")
def scan_check(root_path: str) -> dict:
    root = os.path.normpath(root_path)
    valid = os.path.isdir(root)
    stats = db.get_root_scope_stats(root)
    disk_count = count_disk_files(root) if valid else 0
    return {
        "root_path": root,
        "valid": valid,
        "disk_count": disk_count,
        **stats,
        "already_up_to_date": stats["total"] > 0 and stats["unprocessed"] == 0,
    }


@app.post("/api/analyze/reset")
def analyze_reset(payload: ScanStartRequest) -> dict:
    if jobs.snapshot()["running"]:
        raise HTTPException(status_code=409, detail="job is already running")
    root = os.path.normpath(payload.root_path)
    reset_count = db.reset_analysis_under_root(root)
    return {"reset": reset_count}


@app.post("/api/library/clear")
def library_clear(payload: LibraryClearRequest) -> dict:
    """
    前回の読み込み記録（スキャンで取り込んだファイル一覧）を消す。

    ディスク上のファイルには触れない。ゴミ箱の記録は復元できなくなるため残す。
    """
    if jobs.snapshot()["running"]:
        raise HTTPException(status_code=409, detail="job is already running")

    if payload.scope == "all":
        root = None
    else:
        root = payload.root_path or db.get_setting("root_path")
        if not root:
            raise HTTPException(
                status_code=400,
                detail="対象のライブラリが未設定です。scope=all を指定するか、先にスキャンしてください。",
            )
        root = os.path.normpath(root)

    result = db.clear_scan_records(root)
    return {**result, "root_path": root, "scope": payload.scope}


@app.post("/api/analyze/start")
def analyze_start() -> dict:
    if db.get_unprocessed_count() == 0:
        stats = db.get_library_stats()
        if stats["total"] == 0:
            message = "登録されたファイルがありません。先にフォルダをスキャンしてください。"
        else:
            message = f"解析対象はありません。登録済み{stats['total']}件はすべて解析済みです。"
        return {"started": False, "message": message, "job": jobs.snapshot()}
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


#: サムネイルは内容から決まるので、ある程度キャッシュさせて再取得を減らす。
_THUMB_CACHE_HEADERS = {"Cache-Control": "private, max-age=3600"}


def _is_too_small(blob: bytes) -> bool:
    """
    保存済みサムネイルが Web UI の表示サイズに足りないか。

    PyQt 版や以前の解析は 120px で保存していたため、サイズスライダを上げると
    そういった画像だけ甘く見える。判定は JPEG ヘッダのみの読み取りで、
    画素のデコードは発生しない。
    """
    try:
        with Image.open(io.BytesIO(blob)) as img:
            return max(img.size) < config.WEB_THUMBNAIL_SIZE * 0.9
    except Exception:
        return False


@app.get("/api/files/{file_id}/thumbnail")
def file_thumbnail(file_id: int) -> Response:
    """
    サムネイルを返す。無い場合と、小さすぎる場合はその場で作り直して保存する。

    サムネイルは解析(Analyze)時にしか作られないため、未解析のライブラリでは
    一覧が壊れ画像で埋まっていた。初回だけ生成コストを払い、以降は DB から返す。
    """
    blob = db.get_thumbnail(file_id)
    if not blob or _is_too_small(blob):
        row = db.get_file_by_id(file_id)
        if not row:
            raise HTTPException(status_code=404, detail="file not found")
        try:
            regenerated = _image_preview_bytes(row["path"], config.WEB_THUMBNAIL_SIZE)
        except HTTPException:
            # 元ファイルが消えている等。既存の小さいサムネイルがあるなら使う
            if not blob:
                raise
        else:
            blob = regenerated
            db.save_thumbnail(file_id, blob)
    return Response(content=blob, media_type="image/jpeg", headers=_THUMB_CACHE_HEADERS)


@app.get("/api/files/{file_id}/info")
def file_info(file_id: int) -> dict:
    """
    プレビューペイン用のファイル詳細。

    サイズは DB の値ではなくディスクの実値を返す（スキャン後に差し替えられた
    ファイルでも実態と一致させるため）。画像の寸法は Pillow のヘッダ読み取りだけで
    取得するので、画素のデコードは発生しない。
    """
    row = db.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")

    path = row["path"]
    info = {
        "id": file_id,
        "path": path,
        "filename": row["filename"],
        "extension": row["extension"],
        "content_type": row["content_type"],
        "exists": False,
        "size": row["size"],
        "mtime": row["mtime"],
        "width": None,
        "height": None,
    }

    if not config.validate_path(path) or not os.path.exists(path):
        return info

    info["exists"] = True
    try:
        info["size"] = os.path.getsize(path)
        info["mtime"] = os.path.getmtime(path)
    except OSError:
        pass

    if row["content_type"] == "video":
        width, height = _video_dimensions(path)
    else:
        width, height = _image_dimensions(path)
    info["width"], info["height"] = width, height
    return info


#: EXIF Orientation タグ。5〜8 は 90/270 度回転を含むので幅と高さが入れ替わる
_EXIF_ORIENTATION_TAG = 0x0112
_EXIF_SWAPPED_ORIENTATIONS = {5, 6, 7, 8}


def _image_dimensions(path: str) -> tuple[Optional[int], Optional[int]]:
    """
    表示されるときの寸法を返す。

    サムネイルやプレビューは exif_transpose で回転を反映してから作っている。
    ここで生の値をそのまま返すと、縦位置で撮った写真の寸法が実際の見え方と
    縦横逆になる。EXIF の Orientation を見て入れ替える
    （タグの読み取りだけなので画素のデコードは発生しない）。
    """
    try:
        with Image.open(path) as img:
            width, height = img.width, img.height
            try:
                orientation = img.getexif().get(_EXIF_ORIENTATION_TAG)
            except Exception:
                orientation = None
            if orientation in _EXIF_SWAPPED_ORIENTATIONS:
                width, height = height, width
            return width, height
    except Exception:
        # 画像として開けないものは寸法なしで返す（エラーにはしない）
        return None, None


def _video_dimensions(path: str) -> tuple[Optional[int], Optional[int]]:
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None, None
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        return width, height
    except Exception:
        return None, None
    finally:
        cap.release()


@app.get("/api/files/{file_id}/preview")
def file_preview(file_id: int, max_size: int = Query(1920, ge=320, le=4096)) -> Response:
    row = db.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    return Response(
        content=_image_preview_bytes(row["path"], max_size),
        media_type="image/jpeg",
        headers=_THUMB_CACHE_HEADERS,
    )


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
    """
    移動先候補のフォルダ一覧。

    UI 側でツリー表示するため、パス一覧に加えてライブラリのルートと
    フォルダごとのファイル数も返す（get_folder_tree は元々件数を持っている）。
    """
    tree = db.get_folder_tree()
    folder_list = sorted(tree.keys())
    return {
        "folders": folder_list,
        "root_path": db.get_setting("root_path"),
        "counts": tree,
    }


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


@app.get("/api/settings")
def get_settings() -> dict:
    return {
        "version": app.version,
        "root_path": db.get_setting("root_path"),
        "trash_folder": db.get_trash_folder() or config.get_default_trash_folder(),
        "db_name": config.DB_NAME,
        "defaults": {
            "blur_threshold": config.DEFAULT_BLUR_THRESHOLD,
            "similarity_threshold": config.DEFAULT_SIMILARITY_THRESHOLD,
            "max_similarity_distance": config.MAX_SIMILARITY_DISTANCE,
            "min_file_size_kb": config.MIN_FILE_SIZE_THRESHOLD // 1024,
        },
        "extensions": {
            "image": sorted(config.IMAGE_EXTENSIONS),
            "video": sorted(config.VIDEO_EXTENSIONS),
        },
        "stats": db.get_library_stats(),
    }


@app.post("/api/settings")
def update_settings(payload: SettingsUpdateRequest) -> dict:
    if payload.trash_folder is not None:
        folder = os.path.normpath(payload.trash_folder.strip())
        if not folder or folder in (".", ".."):
            raise HTTPException(status_code=400, detail="invalid trash folder path")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"failed to create trash folder: {exc}") from exc
        db.set_trash_folder(folder)
    return get_settings()


@app.get("/api/triage/next")
def triage_next(after_id: int = Query(0, ge=0)) -> dict:
    row = db.get_next_triage_file(after_id=after_id)
    return {"item": row}


@app.get("/api/duplicates")
def duplicates(use_full_hash: bool = False) -> dict:
    # 簡易ハッシュのグループは pending_full_hash の算出にも使うので一度だけ計算する
    quick_groups = db.get_duplicate_groups(use_full_hash=False)
    raw_groups = db.get_duplicate_groups(use_full_hash=True) if use_full_hash else quick_groups

    groups = []
    for hash_value, size, ids in raw_groups:
        items = [row for fid in ids if (row := db.get_file_by_id(fid))]
        if len(items) < 2:
            continue
        groups.append({
            # 同じ簡易ハッシュでもサイズが異なれば別グループなので、
            # UI 側のキーにはハッシュとサイズの組を使う。
            "key": f"{hash_value}:{size}",
            "hash": hash_value,
            "size": size,
            "count": len(items),
            "items": items,
        })
    return {
        "groups": groups,
        "use_full_hash": use_full_hash,
        # 「完全 (精密)」は full_hash 列が埋まっていないと常に 0 件になる。
        # UI が計算ジョブを促せるように未計算件数を返す。
        "pending_full_hash": db.count_files_needing_full_hash(quick_groups=quick_groups),
    }


@app.post("/api/duplicates/full-hash/start")
def duplicates_full_hash_start() -> dict:
    pending = db.count_files_needing_full_hash()
    if pending == 0:
        return {"started": False, "pending": 0, "message": "完全ハッシュの計算対象はありません。", "job": jobs.snapshot()}
    try:
        jobs.start("full_hash", _run_full_hash)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"started": True, "pending": pending, "job": jobs.snapshot()}


@app.get("/api/blurry")
def blurry(threshold: int = Query(config.DEFAULT_BLUR_THRESHOLD, ge=1, le=1000)) -> dict:
    rows = db.get_blurry_files(threshold)
    available = db.count_blurry_files(threshold)
    return {
        "items": [db.get_file_by_id(fid) for fid, _path in rows],
        # 上限で打ち切られたことを UI に伝える（黙って省略しない）
        "available": available,
        "limit": config.BLUR_LIST_LIMIT,
        "truncated": available > len(rows),
    }


@app.get("/api/tiny")
def tiny_files(
    max_size_kb: int = Query(config.MIN_FILE_SIZE_THRESHOLD // 1024, ge=1, le=1_000_000),
    limit: int = Query(5000, ge=1, le=50000),
) -> dict:
    max_size = max_size_kb * 1024
    rows = db.get_small_files(max_size, limit=limit)
    available = db.count_small_files(max_size)
    items = [row for fid, _path, _size in rows if (row := db.get_file_by_id(fid))]
    return {
        "max_size_kb": max_size_kb,
        "items": items,
        "available": available,
        "limit": limit,
        "truncated": available > len(rows),
    }


@app.get("/api/similar")
def similar(
    distance: int = Query(config.DEFAULT_SIMILARITY_THRESHOLD, ge=0, le=config.MAX_SIMILARITY_DISTANCE),
    max_items: int = Query(5000, ge=1, le=50000),
) -> dict:
    groups, scanned, available = _similar_groups(distance, max_items)
    return {
        "distance": distance,
        "groups": groups,
        "scanned": scanned,
        "available": available,
        "limit": max_items,
        "truncated": available > scanned,
    }


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


@app.get("/api/organize/capabilities")
def organize_capabilities() -> dict:
    return organize_service.capabilities()


@app.get("/api/organize/preview")
def organize_preview(
    gap_hours: float = Query(6.0, ge=0.1, le=168.0),
    min_group_size: int = Query(1, ge=1, le=10000),
    max_items_per_group: int = Query(8, ge=1, le=100),
) -> dict:
    groups = organize_service.build_time_groups(
        db,
        gap_hours=gap_hours,
        min_group_size=min_group_size,
        max_items_per_group=max_items_per_group,
    )
    return {"gap_hours": gap_hours, "min_group_size": min_group_size, "groups": groups}


@app.post("/api/organize/apply")
def organize_apply(payload: OrganizeApplyRequest) -> dict:
    root = os.path.normpath(payload.destination_root)
    parent = os.path.dirname(root) or root
    if not os.path.isdir(root) and not os.path.isdir(parent):
        raise HTTPException(status_code=400, detail="destination_root（または親フォルダ）が存在しません")
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"整理先フォルダを作成できません: {exc}") from exc
    if jobs.snapshot()["running"]:
        raise HTTPException(status_code=409, detail="スキャン/解析の実行中は整理を適用できません")
    result = organize_service.apply_groups(
        db,
        destination_root=root,
        groups=[group.model_dump() for group in payload.groups],
        status_cb=jobs.set_status,
    )
    return {"ok": True, **result}


def main() -> None:
    import uvicorn

    uvicorn.run("src.api_server:app", host="127.0.0.1", port=8765, reload=False)
