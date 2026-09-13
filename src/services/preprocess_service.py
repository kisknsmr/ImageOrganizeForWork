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

#: フォルダ自体を消すなら一緒に消えても困らない OS/ビューアの残骸。
#: これしか入っていないフォルダは、エクスプローラー上は空に見えるので空として扱う。
JUNK_FILENAMES = frozenset({"thumbs.db", "desktop.ini", ".ds_store", "picasa.ini"})


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


def _is_protected_dir(root: str, path: str) -> bool:
    """
    空でも消してはいけないフォルダか。

    - ゴミ箱（配下も含む）… 退避期間中のファイルの置き場所なので触らない
    - 直下の 01/02/03 … 振り分けの受け皿。空になったからと消えると、
      次の実行で作り直されるだけで、ユーザーからはフォルダが消えたように見える
    """
    parts = os.path.relpath(path, root).split(os.sep)
    if config.TRASH_FOLDER_NAME in parts:
        return True
    return len(parts) == 1 and parts[0] in CATEGORY_DIRS


def find_empty_dirs(root_path: str) -> list[str]:
    """
    削除できる空フォルダを、**深い方から順に**返す。

    「中身がサブフォルダだけで、そのサブフォルダも全部空」という連なり
    （a/b/c/d が全部空）も丸ごと対象になる。os.walk を bottom-up で回し、
    子が削除対象だと分かってから親を判定するので、階層はいくつでも構わない。
    返り値の順序どおりに削除すれば、必ず子が先に消える。
    """
    root = os.path.normpath(root_path)
    removable: set[str] = set()
    ordered: list[str] = []

    for current_root, dirs, files in os.walk(root, topdown=False):
        if current_root == root or _is_protected_dir(root, current_root):
            continue
        # 残るサブフォルダが 1 つでもあれば、このフォルダは空にならない
        if any(os.path.join(current_root, name) not in removable for name in dirs):
            continue
        if any(name.lower() not in JUNK_FILENAMES for name in files):
            continue
        removable.add(current_root)
        ordered.append(current_root)

    return ordered


def _depth_of(root: str, path: str) -> int:
    return len(os.path.relpath(path, root).split(os.sep))


def summarize_empty_dirs(root_path: str) -> dict:
    """削除せずに、空フォルダの数と最大の深さだけ返す（実行前の表示用）。"""
    root = os.path.normpath(root_path)
    dirs = find_empty_dirs(root)
    return {
        "total": len(dirs),
        "max_depth": max((_depth_of(root, path) for path in dirs), default=0),
        # 画面で「どれが消えるのか」を確かめられるように先頭だけ添える
        "samples": [os.path.relpath(path, root) for path in dirs[:20]],
    }


def remove_empty_dirs(
    root_path: str,
    status_cb: Optional[StatusCallback] = None,
    progress_cb: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCallback] = None,
) -> dict:
    """
    root_path 配下の空フォルダを削除する（何階層連なっていても、まとめて消える）。

    ファイルが 1 つでも残っているフォルダは消さない。念のため削除は os.rmdir で行い、
    判定と実行の間にファイルが増えていた場合は失敗させる（shutil.rmtree は使わない）。
    root 自身・ゴミ箱・直下の 01/02/03 は残す。
    """
    root = os.path.normpath(root_path)
    emit_status = status_cb or (lambda _msg: None)
    emit_progress = progress_cb or (lambda _done, _total: None)
    stopper = should_stop or (lambda: False)

    emit_status("空フォルダを検索中...")
    dirs = find_empty_dirs(root)
    total = len(dirs)
    max_depth = max((_depth_of(root, path) for path in dirs), default=0)
    removed = 0
    failed = 0
    junk_removed = 0

    def _result(stopped: bool) -> dict:
        return {
            "stopped": stopped, "removed": removed, "failed": failed,
            "total": total, "max_depth": max_depth, "junk_removed": junk_removed,
        }

    if total == 0:
        emit_status("空フォルダはありません")
        return _result(stopped=False)

    emit_status(f"空フォルダ{total}個を削除中...")
    started_at = time.time()

    for idx, path in enumerate(dirs, 1):
        if stopper():
            return _result(stopped=True)
        try:
            for name in os.listdir(path):
                if name.lower() in JUNK_FILENAMES:
                    os.remove(os.path.join(path, name))
                    junk_removed += 1
            os.rmdir(path)
            removed += 1
        except OSError as e:
            # 子の削除に失敗した親もここに来る（空にならないので rmdir が失敗する）
            logger.error(f"Failed to remove empty dir {path}: {e}")
            failed += 1

        if idx % 20 == 0 or idx == total:
            elapsed = time.time() - started_at
            remain = (total - idx) / (idx / elapsed) if idx and elapsed > 0 else 0
            emit_status(f"空フォルダ削除中: {idx}/{total} 残り{format_eta(remain)}")
            emit_progress(idx, total)

    emit_status("完了")
    emit_progress(total, total)
    return _result(stopped=False)


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
