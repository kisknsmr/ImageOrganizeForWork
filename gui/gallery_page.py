"""
ギャラリーページ

フォルダツリー（左）+ サムネイルグリッド（中央）+ プレビューパネル（右）の 3 ペイン構成。
各パネルはスプリッターで可変。ウィンドウリサイズに追従してグリッド列数を自動調整。
サムネイルをダブルクリックするとデフォルトビューアで画像を開く。
"""
import os
import logging
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter, QFrame,
    QScrollArea, QGridLayout, QTreeWidget, QTreeWidgetItem, QApplication,
    QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QColor, QFont, QWheelEvent

from src.config import config
from src.core import get_file_info, format_file_size
from gui.thumbnail_preview import (
    get_thumbnail, get_preview, apply_thumbnail_to_label, apply_preview_to_label,
    open_file_in_viewer, open_file_in_explorer,
    DEFAULT_PREVIEW_MAX_WIDTH, DEFAULT_PREVIEW_MAX_HEIGHT,
)

logger = logging.getLogger(__name__)


class GalleryPage(QWidget):
    """フォルダツリー + グリッドビュー + プレビューの統合ギャラリー"""

    RENDER_BATCH = 30   # バッチ描画サイズ

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.current_folder = None
        self.current_items = []       # [(id, path, size, mtime), ...]
        self._render_index = 0
        self._render_timer = None
        self._resize_timer = None
        self._last_cols = 0           # 前回描画時の列数
        self.thumbnail_size = max(config.DEFAULT_GRID_THUMBNAIL_SIZE, 160)
        self._init_ui()

    # =========================================================
    # UI 構築
    # =========================================================
    def _init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QTreeWidget { background-color: #252526; border: none; font-size: 13px; outline: none; }
            QTreeWidget::item { padding: 4px 0; }
            QTreeWidget::item:selected { background-color: #007acc; color: white; }
            QTreeWidget::item:hover:!selected { background-color: #2d2d30; }
            QLabel { font-size: 13px; }
            QSplitter::handle { background-color: #3e3e42; }
            QSplitter::handle:horizontal { width: 3px; }
        """)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 左: フォルダツリー ---
        tree_panel = QFrame()
        tree_panel.setMinimumWidth(180)
        tree_panel.setMaximumWidth(450)
        tree_panel.setStyleSheet("background-color: #252526; border-right: 1px solid #3e3e42;")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        tree_header = QLabel("  フォルダ構成")
        tree_header.setFixedHeight(36)
        tree_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff; "
                                  "background-color: #2d2d30; padding-left: 10px; border: none;")
        tree_layout.addWidget(tree_header)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setIndentation(18)
        self.folder_tree.itemClicked.connect(self._on_folder_selected)
        tree_layout.addWidget(self.folder_tree)

        self.tree_status = QLabel("")
        self.tree_status.setStyleSheet("color: #888; font-size: 11px; padding: 4px 8px; border: none;")
        tree_layout.addWidget(self.tree_status)

        self.splitter.addWidget(tree_panel)

        # --- 中央: サムネイルグリッド ---
        grid_panel = QWidget()
        grid_panel.setMinimumWidth(300)
        grid_panel.setStyleSheet("background-color: #1e1e1e;")
        grid_outer = QVBoxLayout(grid_panel)
        grid_outer.setContentsMargins(10, 10, 10, 10)
        grid_outer.setSpacing(6)

        # ヘッダー行
        header_row = QHBoxLayout()
        self.grid_header = QLabel("フォルダを選択してください")
        self.grid_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        header_row.addWidget(self.grid_header)
        header_row.addStretch()

        self.grid_status = QLabel("")
        self.grid_status.setStyleSheet("color: #888; font-size: 11px;")
        header_row.addWidget(self.grid_status)
        grid_outer.addLayout(header_row)

        # サイズヒント
        self.size_hint_label = QLabel(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
        self.size_hint_label.setStyleSheet("color: #888; font-size: 11px;")
        grid_outer.addWidget(self.size_hint_label)

        # スクロールエリア
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background: transparent;")
        self.scroll_area.wheelEvent = self._on_wheel_event

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.grid_container)

        # リサイズ監視
        self.grid_container.installEventFilter(self)

        grid_outer.addWidget(self.scroll_area)

        self.splitter.addWidget(grid_panel)

        # --- 右: プレビュー ---
        self.preview_panel = QFrame()
        self.preview_panel.setMinimumWidth(200)
        self.preview_panel.setMaximumWidth(500)
        self.preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)

        preview_title = QLabel("プレビュー")
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        preview_layout.addWidget(preview_title)

        self.preview_image = QLabel("画像を選択してください")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumSize(150, 150)
        self.preview_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        preview_layout.addWidget(self.preview_image)

        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #aaa; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)

        hint_label = QLabel("ダブルクリック → ビューアで開く\nCtrl+クリック → フォルダを開く")
        hint_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 4px;")
        preview_layout.addWidget(hint_label)
        preview_layout.addStretch()

        self.splitter.addWidget(self.preview_panel)

        # スプリッター比率: ツリー(0) 伸縮なし / グリッド(1) 伸縮あり / プレビュー(2) 伸縮なし
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        # 初期サイズ（左 260, 中央 残り, 右 320）
        self.splitter.setSizes([260, 600, 320])
        # スプリッタードラッグ時もグリッド再描画
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        root_layout.addWidget(self.splitter)

    # =========================================================
    # リサイズ追従
    # =========================================================
    def eventFilter(self, obj, event):
        """グリッドコンテナのリサイズを検知してデバウンス再描画"""
        if obj == self.grid_container and event.type() == QEvent.Type.Resize:
            if self.current_items and not (self._render_timer and self._render_timer.isActive()):
                self._schedule_relayout()
        return super().eventFilter(obj, event)

    def _on_splitter_moved(self, pos, index):
        """スプリッターのドラッグによるリサイズ"""
        if self.current_items:
            self._schedule_relayout()

    def _schedule_relayout(self):
        """デバウンスして再レイアウト（200ms）"""
        if self._resize_timer:
            self._resize_timer.stop()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._check_relayout)
        self._resize_timer.start(200)

    def _check_relayout(self):
        """列数が変わった場合のみ全再描画"""
        if not self.current_items:
            return
        new_cols = self._calc_cols()
        if new_cols != self._last_cols:
            self._last_cols = new_cols
            self._relayout_all()

    def _calc_cols(self) -> int:
        """現在のビューポート幅から列数を計算"""
        thumb = self.thumbnail_size
        card_w = thumb + 20
        spacing = self.grid.spacing()
        vw = self.scroll_area.viewport().width()
        if vw <= 0:
            vw = 600
        return max(1, int(vw / (card_w + spacing)))

    def _relayout_all(self):
        """全カードを現在の列数で再配置（サムネイルは再読み込みしない）"""
        self._clear_grid()
        self._render_index = 0
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(0)
        self._render_timer.timeout.connect(self._render_batch)
        self._render_timer.start()

    # =========================================================
    # Ctrl+ホイールでサムネイルサイズ変更
    # =========================================================
    def _on_wheel_event(self, event: QWheelEvent):
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = config.GRID_THUMBNAIL_STEP
            if delta > 0:
                new_size = min(self.thumbnail_size + step, config.MAX_GRID_THUMBNAIL_SIZE)
            else:
                new_size = max(self.thumbnail_size - step, config.MIN_GRID_THUMBNAIL_SIZE)
            if new_size != self.thumbnail_size:
                self.thumbnail_size = new_size
                self.size_hint_label.setText(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
                self._last_cols = 0  # 強制再描画
                if self.current_items:
                    self._relayout_all()
        else:
            QScrollArea.wheelEvent(self.scroll_area, event)

    # =========================================================
    # データ読み込み
    # =========================================================
    def load_data(self):
        """ギャラリーページが表示されたときに呼ばれる"""
        self._build_folder_tree()

    def _build_folder_tree(self):
        """DB からフォルダツリーを構築"""
        self.folder_tree.clear()
        folder_counts = self.db.get_folder_tree()

        if not folder_counts:
            self.tree_status.setText("データなし")
            return

        # ルートパスを特定
        root = self.db.get_setting("root_path")
        if root:
            root = os.path.normpath(root)
        else:
            all_dirs = list(folder_counts.keys())
            root = os.path.commonpath(all_dirs) if all_dirs else ""

        # ツリー構造を構築
        tree_data = defaultdict(list)
        total_files = 0
        for folder, count in sorted(folder_counts.items()):
            total_files += count
            try:
                rel = os.path.relpath(folder, root)
            except ValueError:
                rel = folder
            parts = rel.split(os.sep)
            parent = os.sep.join(parts[:-1]) if len(parts) > 1 else ""
            tree_data[parent].append((rel, folder, count))

        # ルートアイテム
        root_name = os.path.basename(root) if root else "ルート"
        root_item = QTreeWidgetItem([f"📁 {root_name} ({total_files})"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, root)
        root_item.setExpanded(True)
        font = root_item.font(0)
        font.setBold(True)
        root_item.setFont(0, font)
        self.folder_tree.addTopLevelItem(root_item)

        item_map = {"": root_item}

        for parent_rel in sorted(tree_data.keys()):
            for rel, abs_path, count in tree_data[parent_rel]:
                name = os.path.basename(abs_path)
                label = f"📁 {name} ({count})"
                tree_item = QTreeWidgetItem([label])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, abs_path)

                parent_item = item_map.get(parent_rel, root_item)
                parent_item.addChild(tree_item)
                item_map[rel] = tree_item

        self.folder_tree.expandAll()
        self.tree_status.setText(f"{len(folder_counts)} フォルダ / {total_files} ファイル")

    def _on_folder_selected(self, item):
        """ツリーでフォルダがクリックされた"""
        folder = item.data(0, Qt.ItemDataRole.UserRole)
        if not folder:
            return
        self.current_folder = folder
        self._load_folder_files(folder)

    def _load_folder_files(self, folder: str):
        """指定フォルダのファイルをグリッドに表示"""
        if self._render_timer:
            self._render_timer.stop()

        self._clear_grid()

        files = self.db.get_files_in_folder(folder)
        self.current_items = files
        self._render_index = 0
        self._last_cols = 0

        folder_name = os.path.basename(folder) or folder
        self.grid_header.setText(f"📁 {folder_name}")

        if not files:
            self.grid_status.setText("このフォルダにファイルはありません")
            return

        self.grid_status.setText(f"描画中: 0 / {len(files)} 枚")

        self._render_timer = QTimer(self)
        self._render_timer.setInterval(0)
        self._render_timer.timeout.connect(self._render_batch)
        self._render_timer.start()

    def _render_batch(self):
        """バッチ描画"""
        total = len(self.current_items)
        end = min(self._render_index + self.RENDER_BATCH, total)

        thumb = self.thumbnail_size
        card_w = thumb + 20
        card_h = thumb + 50
        cols = self._calc_cols()
        if self._last_cols == 0:
            self._last_cols = cols

        for i in range(self._render_index, end):
            fid, path, size, mtime = self.current_items[i]
            row, col = divmod(i, cols)
            self._add_grid_card(fid, path, size, row, col, card_w, card_h, thumb)

        self._render_index = end
        self.grid_status.setText(f"描画中: {end} / {total} 枚")

        if self._render_index >= total:
            self._render_timer.stop()
            self.grid_status.setText(f"{total} 枚")

    def _add_grid_card(self, fid, path, size, row, col, card_w, card_h, thumb):
        """1 枚分のカードを追加"""
        f = QFrame()
        f.setFixedSize(card_w, card_h)
        f.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
            QFrame:hover { border-color: #007acc; background-color: #353538; }
        """)
        f.setCursor(Qt.CursorShape.PointingHandCursor)

        data = {'id': fid, 'path': path, 'size': size}

        def make_click(d):
            return lambda ev: self._on_card_clicked(ev, d)
        f.mousePressEvent = make_click(data)

        def make_dbl(d):
            return lambda ev: self._on_card_double_click(d)
        f.mouseDoubleClickEvent = make_dbl(data)

        layout = QVBoxLayout(f)
        layout.setContentsMargins(5, 5, 5, 3)
        layout.setSpacing(2)

        lbl = QLabel()
        pix = get_thumbnail(self.db, fid, path, thumb)
        apply_thumbnail_to_label(lbl, pix, thumb,
                                 style_sheet="border: none; border-radius: 4px; background: #000;")
        layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(os.path.basename(path))
        name_lbl.setStyleSheet("border: none; font-size: 10px; color: #ccc;")
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setFixedHeight(30)
        layout.addWidget(name_lbl)

        self.grid.addWidget(f, row, col)

    # =========================================================
    # イベントハンドラ
    # =========================================================
    def _on_card_clicked(self, event, data):
        """シングルクリック → プレビュー表示 / Ctrl+クリック → エクスプローラー"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if not open_file_in_explorer(data['path']):
                QMessageBox.warning(self, "エラー", "フォルダを開けませんでした。")
        else:
            self._update_preview(data)

    def _on_card_double_click(self, data):
        """ダブルクリック → OS デフォルトビューアで開く"""
        if not open_file_in_viewer(data['path']):
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{data['path']}")

    def _update_preview(self, data):
        """プレビューパネルを更新（パネル幅に追従）"""
        path = data['path']

        # パネル幅に合わせたプレビューサイズ
        panel_w = self.preview_panel.width() - 30  # マージン分引く
        max_w = max(150, min(panel_w, DEFAULT_PREVIEW_MAX_WIDTH))
        max_h = DEFAULT_PREVIEW_MAX_HEIGHT

        pix = get_preview(path, max_size=max(max_w, max_h))
        apply_preview_to_label(
            self.preview_image, pix,
            max_width=max_w,
            max_height=max_h,
            style_sheet="background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;",
        )
        if pix.isNull():
            self.preview_image.setText("No Preview")

        info = get_file_info(path)
        lines = []
        lines.append(f"<b>ファイル名:</b> {os.path.basename(path)}")
        lines.append(f"<b>パス:</b> {path}")
        if info['exists']:
            lines.append(f"<b>サイズ:</b> {format_file_size(info['file_size'])}")
            if info['image_width'] and info['image_height']:
                lines.append(f"<b>画像:</b> {info['image_width']} x {info['image_height']} px")
        else:
            lines.append("<b style='color: #d83b01;'>ファイルが見つかりません</b>")
        self.preview_info.setText("<br>".join(lines))

    # =========================================================
    # ヘルパー
    # =========================================================
    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
