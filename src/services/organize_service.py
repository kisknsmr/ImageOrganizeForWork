"""
Qt 非依存のスマート整理（イベントグルーピング）サービス。

既存の EventGrouper（modules/event_grouper.py、Qt 非依存）の時間ベースグルーピングを再利用し、
FastAPI から呼び出せるプレビュー / 適用 API を提供する。

CLIP を使った内容ベース・ハイブリッドのグルーピングは AIWorker（QThread）に依存しているため
API サーバーからは利用できない。capabilities() で利用可否を返し、フロントエンド側で
時間ベースのみを有効化する。
"""
from __future__ import annotations

import importlib.util
import logging
import os
import re
from typing import Callable, Optional

from modules.event_grouper import EventGrouper
from src.database import DatabaseManager

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

# Windows で使えない文字 + パス区切りをフォルダ名から除去する
_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def capabilities() -> dict:
    """整理モードごとの利用可否を返す。"""
    torch_ok = (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("transformers") is not None
    )
    return {
        "time": True,
        # 内容ベース/ハイブリッドは CLIP（torch + transformers）が必要。
        # 現状 AIWorker が QThread 依存のため API サーバーからは常に無効。
        "content": False,
        "hybrid": False,
        "ai_dependencies_installed": torch_ok,
    }


def sanitize_folder_name(name: str) -> str:
    """グループ名を安全なフォルダ名に変換する。空になる場合は '無題' を返す。"""
    cleaned = _INVALID_FOLDER_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned or "無題"


def build_time_groups(
    db: DatabaseManager,
    gap_hours: float = 6.0,
    min_group_size: int = 1,
    max_items_per_group: int = 8,
) -> list[dict]:
    """
    撮影時刻（mtime）ベースでイベントグループを構築して JSON 化可能な形で返す。

    Returns:
        [{ id, suggested_name, start_time, end_time, count, file_ids, items }, ...]
        items はプレビュー用に先頭 max_items_per_group 件のみ詳細を含む。
    """
    files = db.get_all_files_with_info()
    grouper = EventGrouper(db)
    events = grouper.group_by_time(files, gap_hours=gap_hours)

    groups: list[dict] = []
    for event in events:
        if event["count"] < min_group_size:
            continue
        file_ids = [f["id"] for f in event["files"]]
        items = []
        for fid in file_ids[:max_items_per_group]:
            row = db.get_file_by_id(fid)
            if row:
                items.append(row)
        groups.append({
            "id": ",".join(str(fid) for fid in file_ids),
            "suggested_name": event["suggested_name"],
            "start_time": event["start_time"].isoformat() if event.get("start_time") else None,
            "end_time": event["end_time"].isoformat() if event.get("end_time") else None,
            "count": event["count"],
            "file_ids": file_ids,
            "items": items,
        })
    return groups


def apply_groups(
    db: DatabaseManager,
    destination_root: str,
    groups: list[dict],
    status_cb: Optional[StatusCallback] = None,
) -> dict:
    """
    グループごとに destination_root/<グループ名> フォルダを作成してファイルを移動する。

    Args:
        groups: [{ "name": str, "file_ids": [int] }, ...]

    Returns:
        { moved, failed_ids, folders: [{ name, path, moved, failed_ids }] }
    """
    emit_status = status_cb or (lambda _msg: None)
    root = os.path.normpath(destination_root)

    total_moved = 0
    total_failed: list[int] = []
    folder_results: list[dict] = []

    for group in groups:
        name = sanitize_folder_name(str(group.get("name", "")))
        file_ids = [int(fid) for fid in group.get("file_ids", [])]
        folder = os.path.join(root, name)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            logger.error("apply_groups: failed to create folder %s: %s", folder, exc)
            total_failed.extend(file_ids)
            folder_results.append({
                "name": name, "path": folder, "moved": 0, "failed_ids": file_ids,
                "error": f"フォルダ作成に失敗: {exc}",
            })
            continue

        moved = 0
        failed: list[int] = []
        for fid in file_ids:
            row = db.get_file_by_id(fid)
            if not row or row.get("status") == "trash":
                failed.append(fid)
                continue
            if db.move_file_to_folder(fid, row["path"], folder):
                moved += 1
            else:
                failed.append(fid)
        emit_status(f"「{name}」へ {moved} 件移動")
        total_moved += moved
        total_failed.extend(failed)
        folder_results.append({"name": name, "path": folder, "moved": moved, "failed_ids": failed})

    return {"moved": total_moved, "failed_ids": total_failed, "folders": folder_results}
