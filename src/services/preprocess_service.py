"""
Qt 非依存のフォルダ前処理サービス。

選択フォルダ直下を再帰的に走査し、画像/動画/その他へ
「01 Pictures」「02 Movies」「03 Others」の3フォルダへ、
元のサブフォルダ構成を保ったまま振り分ける。
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Callable, Optional

from src.config import config
from src.utils import format_eta

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
StopCallback = Callable[[], bool]

PICTURES_DIR = "01 Pictures"
MOVIES_DIR = "02 Movies"
OTHERS_DIR = "03 Others"
CATEGORY_DIRS = (PICTURES_DIR, MOVIES_DIR, OTHERS_DIR)


def _category_for(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in config.IMAGE_EXTENSIONS:
        return PICTURES_DIR
    if ext in config.VIDEO_EXTENSIONS:
        return MOVIES_DIR
    return OTHERS_DIR


def collect_targets(root: str) -> list[tuple[str, str]]:
    """
    振り分け対象を集める。返すのは (絶対パス, root からの相対ディレクトリ)。

    対象の定義はここ 1 箇所に集約する。実行と事前カウントで基準がずれると、
    「見つかった件数」と「振り分け総数」が食い違って見える。

    対象外:
      - 既にカテゴリフォルダ(01 Pictures/02 Movies/03 Others)の中にあるもの
        （再実行しても二重に振り分けられないようにするため）
      - ゴミ箱フォルダの中
    なお拡張子による絞り込みは**しない**。未対応の拡張子は 03 Others 行きになる。
    """
    targets: list[tuple[str, str]] = []
    for current_root, dirs, files in os.walk(root):
        rel_from_root = os.path.relpath(current_root, root)
        top = rel_from_root.split(os.sep, 1)[0] if rel_from_root != "." else ""
        if top in CATEGORY_DIRS or config.TRASH_FOLDER_NAME in current_root:
            dirs[:] = []
            continue
        for filename in files:
            full_path = os.path.join(current_root, filename)
            if not config.validate_path(full_path):
                continue
            targets.append((full_path, "" if rel_from_root == "." else rel_from_root))
    return targets


def count_targets(root_path: str) -> dict:
    """
    実行前に、振り分け対象の件数と内訳を返す（移動は行わない）。

    run_preprocess と同じ collect_targets を使うので、ここで出た total は
    実行後の「対象N件中」と必ず一致する。
    """
    root = os.path.normpath(root_path)
    counts = {PICTURES_DIR: 0, MOVIES_DIR: 0, OTHERS_DIR: 0}
    targets = collect_targets(root)
    for full_path, _rel_dir in targets:
        counts[_category_for(os.path.basename(full_path))] += 1
    return {
        "total": len(targets),
        "pictures": counts[PICTURES_DIR],
        "movies": counts[MOVIES_DIR],
        "others": counts[OTHERS_DIR],
    }


def run_preprocess(
    root_path: str,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> dict:
    """
    root_path 配下の全ファイルを 01 Pictures / 02 Movies / 03 Others へ移動する。
    サブフォルダの構成はカテゴリフォルダの下にそのまま再現する。
    既にカテゴリフォルダの中にあるファイルはスキャン対象から除外するため、
    再実行しても安全（二重に振り分けられない）。
    """
    root = os.path.normpath(root_path)
    emit_status = status_cb or (lambda _msg: None)
    emit_progress = progress_cb or (lambda _done, _total: None)
    stopper = should_stop or (lambda: False)

    emit_status("対象ファイルを検索中...")
    targets = collect_targets(root)

    total = len(targets)
    counts = {PICTURES_DIR: 0, MOVIES_DIR: 0, OTHERS_DIR: 0}
    if total == 0:
        emit_status("振り分け対象のファイルがありません")
        return {
            "stopped": False, "moved": 0, "skipped": 0, "total": 0,
            "pictures": 0, "movies": 0, "others": 0,
        }

    emit_status(f"{total}件を振り分け中...")
    moved = 0
    skipped = 0
    started_at = time.time()

    def _result(stopped: bool) -> dict:
        return {
            "stopped": stopped, "moved": moved, "skipped": skipped, "total": total,
            "pictures": counts[PICTURES_DIR], "movies": counts[MOVIES_DIR], "others": counts[OTHERS_DIR],
        }

    for idx, (full_path, rel_dir) in enumerate(targets, 1):
        if stopper():
            return _result(stopped=True)
        filename = os.path.basename(full_path)
        category = _category_for(filename)
        dest_dir = os.path.join(root, category, rel_dir) if rel_dir else os.path.join(root, category)
        dest_path = os.path.join(dest_dir, filename)
        try:
            if os.path.exists(dest_path):
                logger.warning(f"Skip preprocess move (destination exists): {dest_path}")
                skipped += 1
            else:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(full_path, dest_path)
                moved += 1
                counts[category] += 1
        except OSError as e:
            logger.error(f"Failed to move {full_path} -> {dest_path}: {e}")
            skipped += 1

        if idx % 20 == 0 or idx == total:
            elapsed = time.time() - started_at
            remain = (total - idx) / (idx / elapsed) if idx and elapsed > 0 else 0
            emit_status(f"振り分け中: {idx}/{total} 残り{format_eta(remain)}")
            emit_progress(idx, total)

    emit_status("完了")
    emit_progress(total, total)
    return _result(stopped=False)
