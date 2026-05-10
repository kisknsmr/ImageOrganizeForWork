"""
スマートフォルダ整理サービス
- DBから解析済みファイルを取得
- 時間ベースでグルーピング
- CLIP ゼロショット分類でフォルダ名を提案
- 物理移動と Undo（セッション内）
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# presets.json の読み込み
# --------------------------------------------------------------------------- #

_PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "presets.json")


def load_presets() -> list[dict]:
    try:
        with open(_PRESETS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("labels", [])
    except Exception as e:
        logger.error("Failed to load presets.json: %s", e)
        return []


# --------------------------------------------------------------------------- #
# CLIP モデルの遅延ロード
# --------------------------------------------------------------------------- #

_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_clip_device = None
_clip_label_embeddings: Optional[np.ndarray] = None
_clip_labels: list[str] = []


def _load_clip():
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_device
    global _clip_label_embeddings, _clip_labels

    if _clip_model is not None:
        return True
    try:
        import torch
        import open_clip

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai", device=device
        )
        model.eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")

        _clip_model = model
        _clip_preprocess = preprocess
        _clip_tokenizer = tokenizer
        _clip_device = device

        # ラベル埋め込みを事前計算
        presets = load_presets()
        labels = []
        texts = []
        for entry in presets:
            display = entry["display"]
            for kw in entry["keywords"]:
                labels.append(display)
                texts.append(kw)

        with torch.no_grad():
            tokens = tokenizer(texts).to(device)
            embs = model.encode_text(tokens)
            embs = embs / embs.norm(dim=-1, keepdim=True)

        # ラベルごとに平均ベクトルを計算
        unique_labels = list(dict.fromkeys(labels))
        label_vecs = []
        for lbl in unique_labels:
            idxs = [i for i, l in enumerate(labels) if l == lbl]
            vec = embs[idxs].mean(dim=0)
            vec = vec / vec.norm()
            label_vecs.append(vec.cpu().numpy())

        _clip_label_embeddings = np.stack(label_vecs)
        _clip_labels = unique_labels

        logger.info("CLIP model loaded on %s. Labels: %d", device, len(unique_labels))
        return True
    except Exception as e:
        logger.error("Failed to load CLIP model: %s", e)
        return False


# --------------------------------------------------------------------------- #
# 時間グルーピング
# --------------------------------------------------------------------------- #

def _group_by_time(files: list[dict], gap_hours: float) -> list[list[dict]]:
    """mtime 昇順に並べ、gap_hours を超える箇所でグループ分割"""
    sorted_files = sorted(files, key=lambda f: (f["mtime"] or 0, f["path"]))
    gap_sec = gap_hours * 3600
    groups: list[list[dict]] = []
    current: list[dict] = []
    for f in sorted_files:
        if not current:
            current.append(f)
        else:
            prev_ts = current[-1]["mtime"] or 0
            curr_ts = f["mtime"] or 0
            if curr_ts - prev_ts > gap_sec:
                groups.append(current)
                current = [f]
            else:
                current.append(f)
    if current:
        groups.append(current)
    return groups


# --------------------------------------------------------------------------- #
# CLIP 推論
# --------------------------------------------------------------------------- #

def _clip_score_files(paths: list[str]) -> Optional[str]:
    """代表画像パスのリストから最もスコアの高いラベルを返す。閾値未満なら None"""
    if not _clip_model or not paths:
        return None
    try:
        import torch
        from PIL import Image

        images = []
        for p in paths:
            try:
                img = _clip_preprocess(Image.open(p).convert("RGB"))
                images.append(img)
            except Exception:
                continue
        if not images:
            return None

        img_tensor = torch.stack(images).to(_clip_device)
        with torch.no_grad():
            img_embs = _clip_model.encode_image(img_tensor)
            img_embs = img_embs / img_embs.norm(dim=-1, keepdim=True)
            img_embs_np = img_embs.cpu().numpy()

        # 全代表画像のスコアを平均
        scores = img_embs_np @ _clip_label_embeddings.T  # (n_imgs, n_labels)
        avg_scores = scores.mean(axis=0)  # (n_labels,)
        best_idx = int(np.argmax(avg_scores))
        best_score = float(avg_scores[best_idx])
        best_label = _clip_labels[best_idx]
        logger.debug("CLIP best=%s score=%.3f", best_label, best_score)
        return best_label, best_score
    except Exception as e:
        logger.error("CLIP inference error: %s", e)
        return None


# --------------------------------------------------------------------------- #
# 提案生成
# --------------------------------------------------------------------------- #

@dataclass
class OrganizeSuggestion:
    group_id: str
    suggested_name: str
    reason: str
    date_range: dict
    items: list[dict]


def generate_suggestions(
    files: list[dict],
    destination_root: str,
    time_gap_hours: float = 4.0,
    confidence_threshold: float = 0.25,
    sample_per_group: int = 3,
) -> list[OrganizeSuggestion]:
    """DB から渡されたファイルリストから提案を生成"""
    clip_ok = _load_clip()
    groups = _group_by_time(files, time_gap_hours)
    suggestions: list[OrganizeSuggestion] = []

    for grp in groups:
        group_id = str(uuid.uuid4())
        ts_list = [f["mtime"] for f in grp if f["mtime"]]
        date_start = _ts_to_iso(min(ts_list)) if ts_list else ""
        date_end = _ts_to_iso(max(ts_list)) if ts_list else ""

        # 代表画像サンプリング（最初・中間・最後）
        n = len(grp)
        sample_idxs = list({0, n // 2, n - 1})[:sample_per_group]
        representative_ids = {grp[i]["id"] for i in sample_idxs}
        rep_paths = [grp[i]["path"] for i in sample_idxs if os.path.exists(grp[i]["path"])]

        items = [
            {
                "id": f["id"],
                "path": f["path"],
                "filename": f["filename"],
                "mtime": f["mtime"],
                "is_representative": f["id"] in representative_ids,
            }
            for f in grp
        ]

        # CLIP 推論
        suggested_name = ""
        reason = "no_clip"
        if clip_ok and rep_paths:
            result = _clip_score_files(rep_paths)
            if result:
                label, score = result
                if score >= confidence_threshold:
                    suggested_name = label
                    reason = f"CLIP_match: {score:.2f}"

        if not suggested_name:
            fallback_date = date_start[:10].replace("-", "") if date_start else "unknown"
            suggested_name = f"未分類_{fallback_date}"
            reason = "below_threshold"

        suggestions.append(OrganizeSuggestion(
            group_id=group_id,
            suggested_name=suggested_name,
            reason=reason,
            date_range={"start": date_start, "end": date_end},
            items=items,
        ))

    return suggestions


def _ts_to_iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# --------------------------------------------------------------------------- #
# 適用（物理移動）と Undo
# --------------------------------------------------------------------------- #

@dataclass
class _MoveRecord:
    src: str
    dst: str


@dataclass
class _UndoSession:
    records: list[_MoveRecord] = field(default_factory=list)


_undo_session: Optional[_UndoSession] = None


def _resolve_dest_folder(destination_root: str, folder_name: str) -> str:
    """連番で衝突を回避したフォルダパスを返す"""
    base = os.path.join(destination_root, folder_name)
    if not os.path.exists(base):
        return base
    i = 2
    while True:
        candidate = f"{base}_{i}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def apply_suggestions(
    plan: list[dict],  # [{group_id, suggested_name, items:[{path}]}]
    destination_root: str,
) -> dict:
    """
    plan を実際に適用してファイルを移動する。
    同名フォルダが既存なら連番サフィックスを付与。
    移動ログを _undo_session に保存。
    """
    global _undo_session
    _undo_session = _UndoSession()

    moved = 0
    failed: list[str] = []

    # フォルダ名ごとに移動先を決定（グループ間で同名がある場合も連番）
    used_folders: dict[str, str] = {}

    for group in plan:
        folder_name = (group.get("suggested_name") or "未分類").strip() or "未分類"
        if folder_name not in used_folders:
            dest_folder = _resolve_dest_folder(destination_root, folder_name)
            used_folders[folder_name] = dest_folder
        else:
            dest_folder = used_folders[folder_name]

        try:
            os.makedirs(dest_folder, exist_ok=True)
        except OSError as e:
            logger.error("Cannot create folder %s: %s", dest_folder, e)
            for item in group.get("items", []):
                failed.append(item.get("path", ""))
            continue

        for item in group.get("items", []):
            src = item.get("path", "")
            if not src or not os.path.exists(src):
                failed.append(src)
                continue
            fname = os.path.basename(src)
            dst = os.path.join(dest_folder, fname)
            if os.path.exists(dst):
                base, ext = os.path.splitext(fname)
                dst = os.path.join(dest_folder, f"{base}_{int(time.time())}{ext}")
            try:
                shutil.move(src, dst)
                _undo_session.records.append(_MoveRecord(src=src, dst=dst))
                moved += 1
            except (OSError, shutil.Error) as e:
                logger.error("Failed to move %s -> %s: %s", src, dst, e)
                failed.append(src)

    return {"moved": moved, "failed": failed}


def undo_last_apply() -> dict:
    """直前の apply を取り消す（逆順に元のパスへ戻す）"""
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
            logger.error("Undo failed %s -> %s: %s", record.dst, record.src, e)
            failed.append(record.dst)

    _undo_session = None
    return {"ok": True, "restored": restored, "failed": failed}


def can_undo() -> bool:
    return _undo_session is not None and len(_undo_session.records) > 0
