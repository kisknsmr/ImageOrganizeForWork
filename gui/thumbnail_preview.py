"""
サムネイル・プレビュー共通モジュール

全画面でサムネイル・プレビューを統一して扱い、元画像の縦横比を保持して表示します。
実装は core に委譲し、ここでは API と表示ヘルパーを提供します。
"""
import os
import subprocess
import platform
import logging
from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel

logger = logging.getLogger(__name__)

# 実装は src.core に一元化
from src.core import (
    create_error_pixmap as _create_error_pixmap,
    get_db_thumbnail as _get_db_thumbnail,
    get_preview_image as _get_preview_image,
)

# 定数（全モジュールで共通）
DEFAULT_PREVIEW_MAX_SIZE = 800
DEFAULT_PREVIEW_MAX_WIDTH = 320
DEFAULT_PREVIEW_MAX_HEIGHT = 600


def create_error_pixmap(size: int) -> QPixmap:
    """エラー表示用プレースホルダー。共通API。"""
    return _create_error_pixmap(size)


def get_thumbnail(db_manager, file_id: int, file_path: str, max_size: int = None) -> QPixmap:
    """
    サムネイル取得（共通API）。
    縦横比を保ったまま、幅・高さとも max_size 以下に収めます。
    DB キャッシュがあればそれを、なければファイルから生成して保存します。
    """
    from src.config import config
    if max_size is None:
        max_size = config.DEFAULT_THUMBNAIL_SIZE
    return _get_db_thumbnail(db_manager, file_id, file_path, max_size)


def get_preview(file_path: str, max_size: int = DEFAULT_PREVIEW_MAX_SIZE) -> QPixmap:
    """
    プレビュー用画像取得（共通API）。
    縦横比を保ったまま、幅・高さとも max_size 以下に収めます。DB にはキャッシュしません。
    """
    return _get_preview_image(file_path, max_size)


def apply_thumbnail_to_label(
    label: QLabel,
    pixmap: QPixmap,
    cell_size: int,
    style_sheet: str = "border: none; border-radius: 4px; background: #1a1a1a;",
) -> None:
    """
    サムネイル用 QLabel に縦横比を保持して表示します。
    セルは cell_size x cell_size の正方形で、画像はその中に中央配置され、
    伸縮せず元の縦横比のまま表示されます（余白は背景色で埋まります）。
    """
    label.setFixedSize(cell_size, cell_size)
    label.setPixmap(pixmap)
    label.setScaledContents(False)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if style_sheet:
        label.setStyleSheet(style_sheet)


def compute_preview_size(
    pix_width: int,
    pix_height: int,
    max_width: int = DEFAULT_PREVIEW_MAX_WIDTH,
    max_height: int = DEFAULT_PREVIEW_MAX_HEIGHT,
) -> Tuple[int, int]:
    """
    プレビュー用ラベルの推奨サイズを計算します。
    縦横比を保ったまま max_width x max_height に収めます。
    """
    if pix_width <= 0 or pix_height <= 0:
        return (max_width, max_height)
    aspect = pix_height / pix_width
    w, h = max_width, int(max_width * aspect)
    if h > max_height:
        h = max_height
        w = int(max_height / aspect)
    return (w, h)


def apply_preview_to_label(
    label: QLabel,
    pixmap: QPixmap,
    max_width: int = DEFAULT_PREVIEW_MAX_WIDTH,
    max_height: int = DEFAULT_PREVIEW_MAX_HEIGHT,
    style_sheet: Optional[str] = "border: none; background: #252526;",
) -> None:
    """
    プレビュー用 QLabel に縦横比を保持して表示します。
    max_width x max_height 以内にスケーリングしたピクスマップを設定しますが、
    ラベル自体のサイズ制約（setFixedSize）は変更しません。
    ラベルの min/max サイズはビューの init_ui 側で管理してください。
    """
    label.setScaledContents(False)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if style_sheet:
        label.setStyleSheet(style_sheet)

    if pixmap.isNull():
        label.clear()
        return

    w, h = compute_preview_size(pixmap.width(), pixmap.height(), max_width, max_height)
    # ピクスマップをスケーリング（高品質）— ラベルサイズは変えない
    scaled_pix = pixmap.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    label.setPixmap(scaled_pix)


def open_file_in_viewer(file_path: str) -> bool:
    """
    OS のデフォルトビューアでファイルを開く（共通API）。
    成功時 True、失敗時 False。
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"Cannot open file: not found: {file_path}")
        return False
    try:
        if platform.system() == 'Windows':
            os.startfile(file_path)
        elif platform.system() == 'Darwin':
            subprocess.run(['open', file_path], check=False)
        else:
            subprocess.run(['xdg-open', file_path], check=False)
        return True
    except Exception as e:
        logger.error(f"Failed to open file: {file_path}: {e}", exc_info=True)
        return False


def open_file_in_explorer(file_path: str) -> bool:
    """
    ファイルを選択した状態でエクスプローラーを開く（共通API）。
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"Cannot reveal file: not found: {file_path}")
        return False
    try:
        if platform.system() == 'Windows':
            subprocess.run(['explorer', '/select,', file_path], check=False)
        elif platform.system() == 'Darwin':
            subprocess.run(['open', '-R', file_path], check=False)
        else:
            subprocess.run(['xdg-open', os.path.dirname(file_path)], check=False)
        return True
    except Exception as e:
        logger.error(f"Failed to reveal file: {file_path}: {e}", exc_info=True)
        return False


# 後方互換のため core と同じ名前でも公開（他モジュールが get_db_thumbnail / get_preview_image で参照する場合用）
get_db_thumbnail = _get_db_thumbnail
get_preview_image = _get_preview_image
