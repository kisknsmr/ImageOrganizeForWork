"""
画像・動画分離サービス

指定フォルダ配下を走査し、サブフォルダ構造を保ったまま
画像と動画を別々の出力先フォルダへコピー（または移動）する。

フロー:
  1. preview()  → 移動予定リストを返す（ファイルは動かさない）
  2. apply()    → 実際に移動し、undo 用ログを保持
  3. undo()     → 直前の apply を逆順で取り消す
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Optional

from src.config import config

logger = logging.getLogger(__name__)

IMAGE_EXTS = config.IMAGE_EXTENSIONS
VIDEO_EXTS = config.VIDEO_EXTENSIONS


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #

@dataclass
class SeparateItem:
    src: str
    dst: str
    kind: str          # "image" | "video"
    rel_path: str      # 元フォルダからの相対パス（表示用）


def preview(
    source_root: str,
    image_dest: str,
    video_dest: str,
) -> list[SeparateItem]:
    """
    source_root 配下を走査して移動予定リストを返す。
    サブフォルダ構造は image_dest / video_dest の下に再現する。
    _TrashBox フォルダは除外する。
    """
    source_root = os.path.normpath(source_root)
    image_dest = os.path.normpath(image_dest)
    video_dest = os.path.normpath(video_dest)

    items: list[SeparateItem] = []

    for dirpath, dirnames, filenames in os.walk(source_root):
        # _TrashBox を除外
        dirnames[:] = [d for d in dirnames if d != config.TRASH_FOLDER_NAME]

        # 出力先フォルダ自体が source_root 配下にある場合も除外
        norm_dir = os.path.normpath(dirpath)
        if norm_dir.startswith(image_dest) or norm_dir.startswith(video_dest):
            continue

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in IMAGE_EXTS:
                kind = "image"
                base_dest = image_dest
            elif ext in VIDEO_EXTS:
                kind = "video"
                base_dest = video_dest
            else:
                continue

            src = os.path.normpath(os.path.join(dirpath, filename))
            # source_root からの相対パスをそのまま出力先に付ける
            rel = os.path.relpath(src, source_root)
            dst = os.path.normpath(os.path.join(base_dest, rel))
            items.append(SeparateItem(src=src, dst=dst, kind=kind, rel_path=rel))

    return items


# --------------------------------------------------------------------------- #
# Apply & Undo
# --------------------------------------------------------------------------- #

@dataclass
class _MoveRecord:
    src: str
    dst: str


@dataclass
class _UndoSession:
    records: list[_MoveRecord] = field(default_factory=list)


_undo_session: Optional[_UndoSession] = None


# --------------------------------------------------------------------------- #
# 進捗管理
# --------------------------------------------------------------------------- #

import threading

@dataclass
class _Progress:
    total: int = 0
    done: int = 0
    moved: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    running: bool = False
    finished: bool = False

    @property
    def percent(self) -> int:
        return int(self.done / self.total * 100) if self.total else 0


_progress = _Progress()
_progress_lock = threading.Lock()


def get_progress() -> dict:
    with _progress_lock:
        return {
            "running": _progress.running,
            "finished": _progress.finished,
            "total": _progress.total,
            "done": _progress.done,
            "moved": _progress.moved,
            "skipped": _progress.skipped,
            "failed_count": len(_progress.failed),
            "percent": _progress.percent,
        }


def apply(items: list[dict]) -> dict:
    """
    バックグラウンドスレッドで移動を実行し、進捗を _progress に随時反映する。
    呼び出し側は get_progress() でポーリングして進捗を取得する。
    """
    global _undo_session, _progress

    with _progress_lock:
        if _progress.running:
            return {"started": False, "message": "既に実行中です"}
        _progress = _Progress(total=len(items), running=True)
        _undo_session = _UndoSession()

    def _run():
        global _progress
        for item in items:
            src = item["src"]
            dst = item["dst"]

            if not os.path.exists(src):
                with _progress_lock:
                    _progress.skipped += 1
                    _progress.done += 1
                continue

            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(dst)
                    dst = f"{base}_{int(time.time())}{ext}"
                shutil.move(src, dst)
                with _progress_lock:
                    _undo_session.records.append(_MoveRecord(src=src, dst=dst))
                    _progress.moved += 1
                    _progress.done += 1
            except (OSError, shutil.Error) as e:
                logger.error("separate apply failed %s -> %s: %s", src, dst, e)
                with _progress_lock:
                    _progress.failed.append(src)
                    _progress.done += 1

        with _progress_lock:
            _progress.running = False
            _progress.finished = True

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"started": True}


def undo() -> dict:
    global _undo_session
    if not _undo_session or not _undo_session.records:
        return {"ok": False, "message": "Undo 対象がありません"}

    restored = 0
    failed: list[str] = []

    for record in reversed(_undo_session.records):
        if not os.path.exists(record.dst):
            failed.append(record.dst)
            continue
        try:
            os.makedirs(os.path.dirname(record.src), exist_ok=True)
            shutil.move(record.dst, record.src)
            restored += 1
        except (OSError, shutil.Error) as e:
            logger.error("separate undo failed %s -> %s: %s", record.dst, record.src, e)
            failed.append(record.dst)

    _undo_session = None
    return {"ok": True, "restored": restored, "failed": failed}


def can_undo() -> bool:
    return _undo_session is not None and len(_undo_session.records) > 0
