"""
Qt 非依存のスキャン・解析サービス。
Tauri/FastAPI から利用することを想定した同期処理APIを提供する。
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

from src.config import config
from src.database import DatabaseManager
from src.utils import format_eta, path_under_root

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
PercentCallback = Callable[[int], None]
ProgressCallback = Callable[[int, int], None]
StopCallback = Callable[[], bool]


def run_scan(
    db: DatabaseManager,
    root_path: str,
    status_cb: Optional[StatusCallback] = None,
    percent_cb: Optional[PercentCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> dict:
    """ファイル走査を実行して DB に新規ファイルを登録する。"""
    root = os.path.normpath(root_path)
    emit_status = status_cb or (lambda _msg: None)
    emit_percent = percent_cb or (lambda _n: None)
    stopper = should_stop or (lambda: False)

    try:
        emit_status("DB登録パスの実在確認中...")
        n_pruned = db.prune_missing_file_paths(include_trash=True)
        if n_pruned:
            emit_status(f"実在しないパス {n_pruned} 件をDBから削除しました。フォルダ走査を続けます…")
    except Exception as exc:
        logger.error("run_scan prune_missing_file_paths failed: %s", exc, exc_info=True)

    emit_status(f"フォルダ走査中: {root}")
    disk_files: set[str] = set()

    for current_root, _dirs, files in os.walk(root):
        if stopper():
            return {"stopped": True, "registered": 0}
        if config.TRASH_FOLDER_NAME in current_root:
            continue
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in config.ALL_EXTENSIONS:
                continue
            full_path = os.path.normpath(os.path.join(current_root, filename))
            if config.validate_path(full_path):
                disk_files.add(full_path)
        if len(disk_files) % 1000 == 0 and disk_files:
            emit_status(f"発見: {len(disk_files)}...")

    db_files = set(os.path.normpath(p) for p in db.get_all_files())
    new_files = list(disk_files - db_files)
    missing_candidates = db_files - disk_files
    missing_files = [path for path in missing_candidates if path_under_root(path, root)]
    if missing_files:
        emit_status(f"削除同期: {len(missing_files)} 件の古い情報を削除中...")
        db.remove_files(set(missing_files))

    total = len(new_files)
    if total == 0:
        emit_status("最新の状態です")
        db.set_setting("root_path", root)
        emit_percent(100)
        return {"stopped": False, "registered": 0}

    emit_status(f"新規 {total} 件を登録中...")
    started_at = time.time()
    registered = 0
    for idx, path in enumerate(new_files, 1):
        if stopper():
            return {"stopped": True, "registered": registered}
        try:
            st = os.stat(path)
            inserted = db.insert_file(path, st.st_size, os.path.getmtime(path))
            if inserted:
                registered += 1
            if config.LOW_LOAD_MODE:
                time.sleep(config.LOW_LOAD_SLEEP_TIME)
            if idx % config.PROGRESS_UPDATE_INTERVAL_SCAN == 0 or idx == total:
                percent = int((idx / total) * 100)
                emit_percent(percent)
                elapsed = time.time() - started_at
                remain = (total - idx) / (idx / elapsed) if idx and elapsed > 0 else 0
                emit_status(f"登録中: {idx}/{total} 残り{format_eta(remain)}")
        except Exception as exc:
            logger.error("run_scan failed for path %s: %s", path, exc, exc_info=True)

    db.set_setting("root_path", root)
    emit_status("完了")
    emit_percent(100)
    return {"stopped": False, "registered": registered}


def run_analyze(
    db: DatabaseManager,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> dict:
    """未解析ファイルの解析処理を実行する。"""
    emit_status = status_cb or (lambda _msg: None)
    emit_progress = progress_cb or (lambda _done, _total: None)
    stopper = should_stop or (lambda: False)

    total = db.get_unprocessed_count()
    if total == 0:
        emit_status("解析対象なし")
        return {"stopped": False, "processed": 0, "total": 0}

    done = 0
    started_at = time.time()
    while not stopper():
        files = db.get_unprocessed_files(config.BATCH_SIZE_ANALYZER)
        if not files:
            break
        for fid, path, ext, size in files:
            if stopper():
                return {"stopped": True, "processed": done, "total": total}
            if config.LOW_LOAD_MODE:
                time.sleep(config.LOW_LOAD_SLEEP_TIME)
            if not os.path.exists(path):
                db.update_analysis_result(fid, None, "", 0, "missing")
                done += 1
                continue
            if size > config.MAX_FILE_SIZE_FOR_PROCESSING:
                db.update_analysis_result(fid, None, "", 0, "skipped")
                done += 1
                continue
            try:
                md5_hash = _head_md5(path)
                blur = 0.0
                phash = ""
                if ext in config.IMAGE_EXTENSIONS:
                    blur = _calc_blur(path)
                    phash = _calc_phash(path)
                    thumb = _build_thumbnail_bytes(path, config.DEFAULT_THUMBNAIL_SIZE)
                    if thumb:
                        db.save_thumbnail(fid, thumb)
                elif ext in config.VIDEO_EXTENSIONS:
                    thumb = _build_video_thumbnail_bytes(path, config.DEFAULT_THUMBNAIL_SIZE)
                    if thumb:
                        db.save_thumbnail(fid, thumb)
                db.update_analysis_result(fid, md5_hash, phash, blur)
            except Exception as exc:
                logger.error("run_analyze failed for %s: %s", path, exc, exc_info=True)
                db.update_analysis_result(fid, None, "", 0, "error")
            done += 1
            if done % config.PROGRESS_UPDATE_INTERVAL_ANALYZE == 0 or done == total:
                elapsed = time.time() - started_at
                remain = (total - done) / (done / elapsed) if done and elapsed > 0 else 0
                emit_status(f"解析中: {done}/{total} 残り{format_eta(remain)}")
                emit_progress(done, total)
    emit_status("完了")
    emit_progress(total, total)
    return {"stopped": False, "processed": done, "total": total}


def _head_md5(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fp:
            return hashlib.md5(fp.read(config.MD5_READ_SIZE)).hexdigest()
    except Exception as exc:
        logger.warning("MD5 calculation failed for %s: %s", path, exc)
        return None


def _calc_blur(path: str) -> float:
    try:
        if os.path.getsize(path) > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
            return 0.0
        with open(path, "rb") as fp:
            buf = np.frombuffer(fp.read(), np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return 0.0
        return float(cv2.Laplacian(img, cv2.CV_64F).var())
    except Exception as exc:
        logger.warning("Blur calculation failed for %s: %s", path, exc)
        return 0.0


def _calc_phash(path: str) -> str:
    try:
        if os.path.getsize(path) > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
            return ""
        with open(path, "rb") as fp:
            buf = np.frombuffer(fp.read(), np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return ""
        img_small = cv2.resize(img, config.PHASH_SIZE, interpolation=cv2.INTER_AREA)
        diff = img_small[:, 1:] > img_small[:, :-1]
        decimal_val = 0
        for idx, flag in enumerate(diff.flatten()):
            if flag:
                decimal_val |= 1 << (63 - idx)
        return f"{decimal_val:016x}"
    except Exception as exc:
        logger.warning("pHash calculation failed for %s: %s", path, exc)
        return ""


def _build_thumbnail_bytes(path: str, size: int) -> Optional[bytes]:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=config.THUMBNAIL_QUALITY, optimize=True)
            return out.getvalue()
    except Exception as exc:
        logger.warning("Image thumbnail generation failed for %s: %s", path, exc)
        return None


def _build_video_thumbnail_bytes(path: str, size: int) -> Optional[bytes]:
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=config.THUMBNAIL_QUALITY, optimize=True)
        return out.getvalue()
    except Exception as exc:
        logger.warning("Video thumbnail generation failed for %s: %s", path, exc)
        return None
    finally:
        cap.release()

