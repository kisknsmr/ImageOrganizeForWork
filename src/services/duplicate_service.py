"""
重複判定サービス。

簡易ハッシュ (先頭 8KB の MD5) で重複候補になったファイルについて、
ファイル全体の MD5 を計算して full_hash カラムへ保存する。
PyQt 版の FullHashThread と同じ処理を、Qt に依存しない同期関数として提供し、
FastAPI (Tauri UI) からも「完全 (精密)」モードを利用できるようにする。
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1MB
MAX_FILES = 50000


def file_md5(path: str) -> str:
    """ファイル全体の MD5 を計算する"""
    h = hashlib.md5()
    with open(path, 'rb') as fp:
        while True:
            chunk = fp.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def run_full_hash(
    db,
    status_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict:
    """重複候補ファイルの完全ハッシュを計算する（同期実行）"""
    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    def progress(done: int, total: int) -> None:
        if progress_cb:
            progress_cb(done, total)

    files = db.get_files_needing_full_hash(limit=MAX_FILES)
    total = len(files)
    if total == 0:
        status("完全ハッシュ: 対象ファイルなし")
        progress(0, 0)
        return {"total": 0, "hashed": 0, "failed": 0, "stopped": False}

    status(f"完全ハッシュ: {total} 件を計算中...")
    hashed = 0
    failed = 0
    stopped = False

    for done, (fid, path, _size) in enumerate(files, 1):
        if should_stop and should_stop():
            stopped = True
            break
        if not os.path.exists(path):
            failed += 1
        else:
            try:
                db.update_full_hash(fid, file_md5(path))
                hashed += 1
            except OSError as exc:
                failed += 1
                logger.warning("Full hash read error: %s: %s", path, exc)
            except Exception as exc:
                failed += 1
                logger.error("Full hash error: %s: %s", path, exc, exc_info=True)
        progress(done, total)
        if done % 20 == 0 or done == total:
            status(f"完全ハッシュ: {done}/{total} 件")

    if not stopped:
        status(f"完全ハッシュ完了: {hashed} 件（失敗 {failed} 件）")
    return {"total": total, "hashed": hashed, "failed": failed, "stopped": stopped}
