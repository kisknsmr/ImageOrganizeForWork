"""
空フォルダ削除サービス

指定フォルダ配下を走査し、空フォルダ（ファイルを一切含まないフォルダ）を
ボトムアップで検出・削除する。
_TrashBox フォルダは除外する。
"""
from __future__ import annotations

import logging
import os

from src.config import config

logger = logging.getLogger(__name__)


def find_empty_folders(root: str) -> list[str]:
    """
    root 配下の空フォルダを返す（ボトムアップ順）。
    サブフォルダがすべて空の親フォルダも対象に含む。
    """
    root = os.path.normpath(root)
    empty: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dirnames[:] = [d for d in dirnames if d != config.TRASH_FOLDER_NAME]

        if dirpath == root:
            continue

        # ファイルがなく、残っているサブフォルダがすべてすでに empty リストにある場合
        has_files = bool(filenames)
        has_non_empty_subdirs = any(
            os.path.normpath(os.path.join(dirpath, d)) not in set(empty)
            for d in dirnames
            if d != config.TRASH_FOLDER_NAME
        )

        if not has_files and not has_non_empty_subdirs:
            empty.append(os.path.normpath(dirpath))

    return empty


def delete_empty_folders(folders: list[str]) -> dict:
    """指定フォルダリストを削除する。"""
    deleted = 0
    failed: list[str] = []

    for path in folders:
        try:
            os.rmdir(path)
            deleted += 1
        except OSError as e:
            logger.error("empty folder delete failed %s: %s", path, e)
            failed.append(path)

    return {"deleted": deleted, "failed": failed}
