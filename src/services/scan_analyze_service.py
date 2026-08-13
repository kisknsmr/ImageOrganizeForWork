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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

from src.config import config
from src.database import DatabaseManager
from src.image_formats import decode_grayscale
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

    # 探索フェーズは総数が未知でパーセントを出せないため、
    # 発見件数を時間ベース（約0.4秒毎）で通知して「動いている」ことを見せる。
    last_walk_emit = time.time()
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
        now = time.time()
        if now - last_walk_emit >= 0.4:
            emit_status(f"フォルダ走査中... 発見 {len(disk_files)} 件")
            last_walk_emit = now

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


def count_disk_files(root_path: str) -> int:
    """フォルダ配下の対象拡張子ファイル数をカウントする（DB登録は行わない、事前確認用）。"""
    root = os.path.normpath(root_path)
    count = 0
    for current_root, _dirs, files in os.walk(root):
        if config.TRASH_FOLDER_NAME in current_root:
            continue
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in config.ALL_EXTENSIONS:
                continue
            full_path = os.path.normpath(os.path.join(current_root, filename))
            if config.validate_path(full_path):
                count += 1
    return count


def run_analyze(
    db: DatabaseManager,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
    wait_if_paused: Optional[Callable[[], None]] = None,
    workers: Optional[int] = None,
) -> dict:
    """
    未解析ファイルの解析処理を実行する。

    デコードはスレッドプールで並列化し、DB 書き込みは呼び出し元スレッドに
    集約する（SQLite への書き込みを 1 本にまとめ、ロック競合を避けるため）。
    OpenCV / Pillow のデコードは GIL を解放するので、スレッドでも実効的に
    並列化される。

    一時停止は各バッチの境界で効く。処理中のバッチは完走させるため、
    停止までに最大 workers 件ぶんの遅れがある。
    """
    emit_status = status_cb or (lambda _msg: None)
    emit_progress = progress_cb or (lambda _done, _total: None)
    stopper = should_stop or (lambda: False)
    pause_gate = wait_if_paused or (lambda: None)
    pool_size = max(1, workers or config.ANALYZE_WORKERS)

    total = db.get_unprocessed_count()
    if total == 0:
        emit_status("解析対象なし")
        return {"stopped": False, "processed": 0, "total": 0}

    done = 0
    started_at = time.time()

    def emit_progress_line() -> None:
        elapsed = time.time() - started_at
        rate = done / elapsed if elapsed > 0 else 0
        remain = (total - done) / rate if rate > 0 else 0
        speed = f" {rate:.1f}件/秒" if rate > 0 else ""
        emit_status(f"解析中: {done}/{total} 残り{format_eta(remain)}{speed}")
        emit_progress(done, total)

    with ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="analyze") as pool:
        while not stopper():
            pause_gate()
            if stopper():
                break

            files = db.get_unprocessed_files(config.BATCH_SIZE_ANALYZER)
            if not files:
                break

            # 先に DB だけで片付くもの（欠損・サイズ超過）を除いてから並列に回す
            pending: list[tuple] = []
            for fid, path, ext, size in files:
                if not os.path.exists(path):
                    db.update_analysis_result(fid, None, None, 0, "missing")
                    done += 1
                elif size > config.MAX_FILE_SIZE_FOR_PROCESSING:
                    db.update_analysis_result(fid, None, None, 0, "skipped")
                    done += 1
                else:
                    pending.append((fid, path, ext))

            # 一度に全件投入せず、プール幅ぶんずつ流す。
            # まとめて投入すると、一時停止・中止がバッチ 1 個ぶん（最大 64 件）
            # 待たされる。小分けにすれば待ちは実行中のタスク数までで済む。
            chunk_size = max(1, pool_size * 2)
            for offset in range(0, len(pending), chunk_size):
                if stopper():
                    break
                pause_gate()
                if stopper():
                    break

                chunk = pending[offset:offset + chunk_size]
                futures = {
                    pool.submit(_analyze_media, path, ext): fid for fid, path, ext in chunk
                }
                for future in as_completed(futures):
                    fid = futures[future]
                    try:
                        res = future.result()
                    except Exception as exc:  # _analyze_media 内で捕捉済みだが保険
                        logger.error("run_analyze worker failed (id=%s): %s", fid, exc)
                        res = {"md5": None, "blur": 0.0, "phash": None,
                               "thumb": None, "status": "error"}
                    if res.get("thumb"):
                        db.save_thumbnail(fid, res["thumb"])
                    if res.get("status"):
                        db.update_analysis_result(
                            fid, res["md5"], res["phash"] or None, res["blur"], res["status"]
                        )
                    else:
                        db.update_analysis_result(
                            fid, res["md5"], res["phash"] or None, res["blur"]
                        )
                    done += 1
                    if done % config.PROGRESS_UPDATE_INTERVAL_ANALYZE == 0 or done == total:
                        emit_progress_line()

            if config.LOW_LOAD_MODE:
                time.sleep(config.LOW_LOAD_SLEEP_TIME)

    if stopper():
        emit_status(f"停止しました（{done}/{total} 件処理済み）")
        emit_progress(done, total)
        return {"stopped": True, "processed": done, "total": total}

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


def _blur_from_gray(gray) -> float:
    """グレースケール配列からぼけスコア（Laplacian 分散）を求める。"""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _phash_from_gray(gray) -> str:
    """
    グレースケール配列から pHash を求める。

    差分を numpy のビット演算でまとめて畳む（64 回の Python ループを避ける）。
    """
    small = cv2.resize(gray, config.PHASH_SIZE, interpolation=cv2.INTER_AREA)
    diff = (small[:, 1:] > small[:, :-1]).flatten()
    weights = 1 << np.arange(63, -1, -1, dtype=np.uint64)
    value = int(np.bitwise_or.reduce(weights[diff])) if diff.any() else 0
    return f"{value:016x}"


def _calc_blur(path: str) -> float:
    """互換用。単発で呼ぶ場合のみ使う（解析ループは _analyze_media を使う）。"""
    try:
        if os.path.getsize(path) > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
            return 0.0
        with open(path, "rb") as fp:
            data = fp.read()
        gray = decode_grayscale(data, path)
        return 0.0 if gray is None else _blur_from_gray(gray)
    except Exception as exc:
        logger.warning("Blur calculation failed for %s: %s", path, exc)
        return 0.0


def _calc_phash(path: str) -> str:
    """互換用。単発で呼ぶ場合のみ使う（解析ループは _analyze_media を使う）。"""
    try:
        if os.path.getsize(path) > config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
            return ""
        with open(path, "rb") as fp:
            data = fp.read()
        gray = decode_grayscale(data, path)
        return "" if gray is None else _phash_from_gray(gray)
    except Exception as exc:
        logger.warning("pHash calculation failed for %s: %s", path, exc)
        return ""


def _thumbnail_from_bytes(data: bytes, size: int, path_for_log: str = "") -> Optional[bytes]:
    """
    バイト列からサムネイルを作る。

    JPEG は draft() で縮小デコードを指示する。libjpeg が DCT 段階で間引くため、
    4000px 級の写真を 320px にする場合はフルデコードの数分の一で済む。
    JPEG 以外では no-op なので、そのまま安全に呼べる。
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.draft("RGB", (size, size))
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=config.THUMBNAIL_QUALITY, optimize=True)
            return out.getvalue()
    except Exception as exc:
        logger.warning("Image thumbnail generation failed for %s: %s", path_for_log, exc)
        return None


def _build_thumbnail_bytes(path: str, size: int) -> Optional[bytes]:
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except OSError as exc:
        logger.warning("Image thumbnail generation failed for %s: %s", path, exc)
        return None
    return _thumbnail_from_bytes(data, size, path)


def _analyze_media(path: str, ext: str) -> dict:
    """
    1 ファイル分の解析を行う（DB には触れない）。

    ファイルの読み込みとデコードをここに集約する。従来は blur / pHash /
    サムネイルがそれぞれ独立にファイルを開いて全体をデコードしていたため、
    1 枚あたりフルデコードが 3 回走っていた。読み込み 1 回・
    グレースケールデコード 1 回に集約し、サムネイルは縮小デコードで作る。

    DB を触らないので、スレッドプールから安全に並列実行できる
    （OpenCV / Pillow のデコードは GIL を解放する）。
    """
    result: dict = {"md5": None, "blur": 0.0, "phash": None, "thumb": None, "status": None}

    try:
        if ext in config.VIDEO_EXTENSIONS:
            # 動画はフレーム取得が別経路。ハッシュは先頭ブロックのみ
            result["md5"] = _head_md5(path)
            result["thumb"] = _build_video_thumbnail_bytes(path, config.WEB_THUMBNAIL_SIZE)
            return result

        with open(path, "rb") as fp:
            data = fp.read()
        result["md5"] = hashlib.md5(data[: config.MD5_READ_SIZE]).hexdigest()

        if ext not in config.IMAGE_EXTENSIONS:
            return result

        if len(data) <= config.MAX_IMAGE_SIZE_FOR_ANALYSIS:
            gray = decode_grayscale(data, path)
            if gray is not None:
                # ぼけスコアは原寸で求める（縮小すると値が変わり、
                # ユーザーが設定したしきい値の意味が変わってしまう）
                result["blur"] = _blur_from_gray(gray)
                result["phash"] = _phash_from_gray(gray)

        result["thumb"] = _thumbnail_from_bytes(data, config.WEB_THUMBNAIL_SIZE, path)
        return result
    except Exception as exc:
        logger.error("analyze failed for %s: %s", path, exc, exc_info=True)
        return {"md5": None, "blur": 0.0, "phash": None, "thumb": None, "status": "error"}


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

