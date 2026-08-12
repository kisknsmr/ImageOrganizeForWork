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


#: 振り分け対象 1 件。(絶対パス, 移動先での相対ディレクトリ, 見直しによる移動か)
Target = tuple[str, str, bool]


def scan_folder(root: str, full: bool = False) -> tuple[list[Target], int]:
    """
    フォルダ内のファイルを「振り分け対象」と「対応不要」に分ける。

    対象の定義はここ 1 箇所に集約する。実行と事前カウントで基準がずれると
    画面上の件数が食い違って見える。

    Args:
        full:
            False（差分）… カテゴリフォルダ(01/02/03)の中は走査しない。
                振り分け済みのファイルは触らないので速く、結果も予測しやすい。
            True（フル）… カテゴリフォルダの中も走査し、**分類が正しいか判定する**。
                対応拡張子が増えると分類結果は変わるため
                （例: HEIC 対応前に 03 Others へ入ったファイルは、今の基準では画像）、
                見直せないと誤った振り分けが永久に残る。

    Returns:
        (targets, already_sorted)
        targets       … 振り分け対象
        already_sorted… 既に正しいカテゴリフォルダにあり、動かす必要がない件数
                        （差分モードでは走査しないので 0 のまま）

    拡張子による絞り込みは**しない**。未対応の拡張子は 03 Others 行きになる。
    """
    targets: list[Target] = []
    already_sorted = 0

    for current_root, dirs, files in os.walk(root):
        if config.TRASH_FOLDER_NAME in current_root:
            dirs[:] = []
            continue
        rel_from_root = "" if current_root == root else os.path.relpath(current_root, root)
        parts = rel_from_root.split(os.sep) if rel_from_root else []
        top = parts[0] if parts else ""
        in_category = top in CATEGORY_DIRS

        if in_category and not full:
            # 差分モードでは中へ降りない（走査そのものを省く）
            dirs[:] = []
            continue

        for filename in files:
            full_path = os.path.join(current_root, filename)
            if not config.validate_path(full_path):
                continue

            if not in_category:
                targets.append((full_path, rel_from_root, False))
                continue

            # カテゴリフォルダ内。今の基準での正しい分類と一致するか見る
            if _category_for(filename) == top:
                already_sorted += 1
            else:
                # 移動先ではカテゴリ名を除いた残りの階層を保つ
                # （01 Pictures/Event1/x.mp4 → 02 Movies/Event1/x.mp4）
                targets.append((full_path, os.sep.join(parts[1:]), True))

    return targets, already_sorted


def collect_targets(root: str, full: bool = False) -> list[Target]:
    """振り分け対象だけを返す（scan_folder の薄いラッパ）。"""
    return scan_folder(root, full)[0]


def _category_counts(targets: list[Target]) -> dict:
    counts = {PICTURES_DIR: 0, MOVIES_DIR: 0, OTHERS_DIR: 0}
    for full_path, _rel_dir, _recheck in targets:
        counts[_category_for(os.path.basename(full_path))] += 1
    return counts


def summarize_folder(root_path: str, full: bool = False) -> dict:
    """
    実行前に、フォルダの内訳を返す（移動は行わない）。

    run_preprocess と同じ scan_folder を同じモードで使うので、ここで出た数は
    実行後の結果表示と必ず一致する。
    """
    root = os.path.normpath(root_path)
    targets, already_sorted = scan_folder(root, full)
    counts = _category_counts(targets)
    misplaced = sum(1 for _p, _d, recheck in targets if recheck)
    return {
        "all_files": len(targets) + already_sorted,
        "total": len(targets),
        # 未振り分け（カテゴリフォルダの外にある）
        "unsorted": len(targets) - misplaced,
        # 既に振り分け済みだが、今の基準では別カテゴリに入るべきもの
        "misplaced": misplaced,
        "already_sorted": already_sorted,
        "full": full,
        "pictures": counts[PICTURES_DIR],
        "movies": counts[MOVIES_DIR],
        "others": counts[OTHERS_DIR],
    }


def run_preprocess(
    root_path: str,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
    full: bool = False,
) -> dict:
    """
    root_path 配下の全ファイルを 01 Pictures / 02 Movies / 03 Others へ移動する。
    サブフォルダの構成はカテゴリフォルダの下にそのまま再現する。

    既に正しいカテゴリにあるファイルは触らないので、再実行しても安全。
    一方で、**間違ったカテゴリにあるファイルは正しい方へ移し直す**。
    対応拡張子が増えると分類結果が変わるため（HEIC 対応前に 03 Others へ
    入ったファイルなど）、見直しができないと誤りが永久に残る。
    """
    root = os.path.normpath(root_path)
    emit_status = status_cb or (lambda _msg: None)
    emit_progress = progress_cb or (lambda _done, _total: None)
    stopper = should_stop or (lambda: False)

    emit_status("対象ファイルを検索中...")
    targets, already_sorted = scan_folder(root, full)

    total = len(targets)
    all_files = total + already_sorted
    misplaced = sum(1 for _p, _d, recheck in targets if recheck)
    unsorted = total - misplaced
    counts = {PICTURES_DIR: 0, MOVIES_DIR: 0, OTHERS_DIR: 0}
    if total == 0:
        emit_status("振り分け対象のファイルがありません")
        return {
            "stopped": False, "moved": 0, "skipped": 0, "total": 0,
            "all_files": all_files, "already_sorted": already_sorted,
            "unsorted": 0, "misplaced": 0, "rechecked": 0, "full": full,
            "pictures": 0, "movies": 0, "others": 0,
        }

    emit_status(f"{total}件を振り分け中...")
    moved = 0
    skipped = 0
    rechecked = 0
    started_at = time.time()

    def _result(stopped: bool) -> dict:
        return {
            "stopped": stopped, "moved": moved, "skipped": skipped, "total": total,
            # フォルダ全体の内訳も返す（全ファイル = 対象 + 対応不要）
            "all_files": all_files, "already_sorted": already_sorted,
            "unsorted": unsorted, "misplaced": misplaced,
            # 実際に別カテゴリへ移し直した件数
            "rechecked": rechecked, "full": full,
            "pictures": counts[PICTURES_DIR], "movies": counts[MOVIES_DIR], "others": counts[OTHERS_DIR],
        }

    for idx, (full_path, rel_dir, is_recheck) in enumerate(targets, 1):
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
                if is_recheck:
                    rechecked += 1
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
