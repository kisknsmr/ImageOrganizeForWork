import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QListWidgetItem, QScrollArea,
                             QFrame, QApplication, QGridLayout, QButtonGroup, QSizePolicy, QSplitter)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPalette, QColor, QWheelEvent

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager, get_file_info, format_file_size
from config import config

logger = logging.getLogger(__name__)


class DuplicatePage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.view_mode = "grid"
        self.current_group_data = []
        self.thumbnail_size = config.DEFAULT_GRID_THUMBNAIL_SIZE
        self.selected_item_data = None  # 選択中のアイテムデータ
        self.init_ui()

    def init_ui(self):
        # 共通スタイル
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QListWidget { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #3e3e42; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
            QLabel { font-size: 13px; }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 左サイドパネル ---
        left_panel = QWidget()
        left_panel.setFixedWidth(320)
        left_panel.setStyleSheet("border-right: 1px solid #3e3e42; background-color: #252526;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)

        left_layout.addWidget(QLabel("重複グループ一覧"))

        self.list = QListWidget()
        self.list.setStyleSheet("border: none; background-color: transparent;")
        self.list.itemClicked.connect(self.on_group_selected)
        left_layout.addWidget(self.list)

        # --- 右メインパネル（スプリッターで分割） ---
        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.setStyleSheet("background-color: #1e1e1e;")
        
        # 左側: グリッドビュー
        grid_panel = QWidget()
        grid_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(grid_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)

        # ヘッダー
        header_layout = QHBoxLayout()
        header_lbl = QLabel("詳細確認")
        header_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")

        self.btn_view_grid = QPushButton("■ グリッド")
        self.btn_view_list = QPushButton("≡ リスト")

        for btn in [self.btn_view_grid, self.btn_view_list]:
            btn.setCheckable(True)
            btn.setFixedSize(80, 30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { background-color: #2d2d30; border: 1px solid #3e3e42; color: #aaa; }
                QPushButton:checked { background-color: #007acc; color: white; border: none; }
                QPushButton:hover:!checked { background-color: #3e3e42; }
            """)

        self.btn_view_grid.setChecked(True)
        self.view_group = QButtonGroup(self)
        self.view_group.addButton(self.btn_view_grid)
        self.view_group.addButton(self.btn_view_list)
        self.view_group.buttonClicked.connect(self.toggle_view)

        header_layout.addWidget(header_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_view_grid)
        header_layout.addWidget(self.btn_view_list)

        size_label = QLabel(f"サムネイルサイズ: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
        size_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(size_label)
        right_layout.addLayout(header_layout)

        # エリア
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setStyleSheet("border: none; background-color: transparent;")
        self.area.setWidget(self.container)
        # ホイールイベントをインストール
        self.area.wheelEvent = self.on_wheel_event
        
        right_layout.addWidget(self.area)

        
        # 右側: プレビューパネル
        preview_panel = QFrame()
        preview_panel.setFixedWidth(350)
        preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(15)
        
        preview_title = QLabel("プレビュー")
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        preview_layout.addWidget(preview_title)
        
        self.preview_image = QLabel("画像を選択してください")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setFixedSize(320, 320)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        self.preview_image.setScaledContents(True)
        preview_layout.addWidget(self.preview_image)
        
        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #aaa; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        
        preview_layout.addStretch()
        
        right_splitter.addWidget(grid_panel)
        right_splitter.addWidget(preview_panel)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_splitter)

    def load_data(self):
        self.list.clear()
        self.clear_grid()
        try:
            hashes = self.db.get_duplicate_hashes()
            if not hashes:
                self.list.addItem("重複なし")
                return
            for h, cnt in hashes:
                item = QListWidgetItem(f"重複 {cnt}枚")
                item.setData(Qt.ItemDataRole.UserRole, h)
                self.list.addItem(item)
        except Exception as e:
            logger.error(f"Load error: {e}")

    def on_group_selected(self, item):
        h = item.data(Qt.ItemDataRole.UserRole)
        if not h: return

        try:
            # データ取得
            files = self.db.get_files_by_hash(h)
            # 辞書形式に変換して保持
            self.current_group_data = [{'id': f[0], 'path': f[1], 'size': f[2], 'mtime': f[3]} for f in files]
            self.render_items()
        except Exception as e:
            logger.error(f"Failed to load duplicate group: {e}", exc_info=True)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "エラー", "データの読み込みに失敗しました")

    def toggle_view(self, btn):
        self.view_mode = "grid" if btn == self.btn_view_grid else "list"
        if self.current_group_data:
            self.render_items()
    
    def render_items(self):
        self.clear_grid()
        if self.view_mode == "grid":
            self.render_grid_view()
        else:
            self.render_list_view()
        # サイズラベルを更新
        size_label = self.findChild(QLabel)
        if size_label and "サムネイルサイズ" in size_label.text():
            size_label.setText(f"サムネイルサイズ: {self.thumbnail_size}px (Ctrl+ホイールで変更)")

    def render_grid_view(self):
        # 列数をサムネイルサイズに応じて調整
        cols = max(3, int(800 / (self.thumbnail_size + 20)))  # 余白を考慮
        thumb_size = self.thumbnail_size
        frame_width = thumb_size + 20
        frame_height = thumb_size + 60

        for i, data in enumerate(self.current_group_data):
            f = QFrame()
            f.setFixedSize(frame_width, frame_height)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)
            
            # クリックイベントを追加（ラムダのクロージャ問題を回避）
            def make_click_handler(d):
                return lambda event: self.on_item_clicked(d)
            f.mousePressEvent = make_click_handler(data)

            l = QVBoxLayout(f)
            l.setContentsMargins(8, 8, 8, 8)
            l.setSpacing(5)

            lbl = QLabel()
            pix = get_db_thumbnail(self.db, data['id'], data['path'], thumb_size)
            lbl.setPixmap(pix)
            lbl.setScaledContents(True)
            lbl.setFixedSize(thumb_size, thumb_size)
            lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

            name_lbl = QLabel(os.path.basename(data['path']))
            name_lbl.setStyleSheet("border: none; font-size: 10px; color: #ccc;")
            name_lbl.setWordWrap(True)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setFixedHeight(25)

            btn = QPushButton("削除")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet(self.get_del_btn_style())
            btn.clicked.connect(lambda _, fid=data['id'], w=f: self.trash(fid, w))

            l.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            l.addWidget(name_lbl)
            l.addWidget(btn)

            self.grid.addWidget(f, i // cols, i % cols)
    
    def on_item_clicked(self, data):
        """アイテムがクリックされたときの処理"""
        self.selected_item_data = data
        self.update_preview(data)
    
    def update_preview(self, data):
        """プレビューを更新"""
        if not data:
            self.preview_image.clear()
            self.preview_image.setText("画像を選択してください")
            self.preview_info.setText("")
            return
        
        # プレビュー画像を表示
        pix = get_db_thumbnail(self.db, data['id'], data['path'], 300)
        self.preview_image.setPixmap(pix)
        
        # ファイル情報を取得して表示
        file_info = get_file_info(data['path'])
        info_lines = []
        info_lines.append(f"<b>ファイル名:</b> {os.path.basename(data['path'])}")
        info_lines.append(f"<b>パス:</b> {data['path']}")
        
        if file_info['exists']:
            info_lines.append(f"<b>ファイルサイズ:</b> {format_file_size(file_info['file_size'])}")
            if file_info['image_width'] and file_info['image_height']:
                info_lines.append(f"<b>画像サイズ:</b> {file_info['image_width']} × {file_info['image_height']} px")
        else:
            info_lines.append("<b style='color: #d83b01;'>ファイルが見つかりません</b>")
        
        self.preview_info.setText("<br>".join(info_lines))
    
    def on_wheel_event(self, event: QWheelEvent):
        """ホイールイベント処理（Ctrl + ホイールでサムネイルサイズ変更）"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            # Ctrl + ホイールでサムネイルサイズを変更
            delta = event.angleDelta().y()
            if delta > 0:
                # 拡大
                new_size = min(self.thumbnail_size + config.GRID_THUMBNAIL_STEP, 
                              config.MAX_GRID_THUMBNAIL_SIZE)
            else:
                # 縮小
                new_size = max(self.thumbnail_size - config.GRID_THUMBNAIL_STEP, 
                              config.MIN_GRID_THUMBNAIL_SIZE)
            
            if new_size != self.thumbnail_size:
                self.thumbnail_size = new_size
                if self.view_mode == "grid" and self.current_group_data:
                    self.render_items()
        else:
            # 通常のスクロール
            QScrollArea.wheelEvent(self.area, event)

    def render_list_view(self):
        thumb_size = 80
        for i, data in enumerate(self.current_group_data):
            f = QFrame()
            f.setFixedHeight(100)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)

            l = QHBoxLayout(f)
            l.setContentsMargins(10, 10, 10, 10)
            l.setSpacing(15)

            lbl = QLabel()
            pix = get_db_thumbnail(self.db, data['id'], data['path'], thumb_size)
            lbl.setPixmap(pix)
            lbl.setScaledContents(True)
            lbl.setFixedSize(thumb_size, thumb_size)
            lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

            info_layout = QVBoxLayout()
            name_lbl = QLabel(os.path.basename(data['path']))
            name_lbl.setStyleSheet("border: none; font-size: 14px; font-weight: bold; color: #fff;")
            path_lbl = QLabel(data['path'])
            path_lbl.setStyleSheet("border: none; font-size: 11px; color: #888;")
            path_lbl.setWordWrap(True)

            info_layout.addWidget(name_lbl)
            info_layout.addWidget(path_lbl)
            info_layout.addStretch()

            btn = QPushButton("ゴミ箱へ")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet(self.get_del_btn_style())
            btn.clicked.connect(lambda _, fid=data['id'], w=f: self.trash(fid, w))

            l.addWidget(lbl)
            l.addLayout(info_layout, stretch=1)
            l.addWidget(btn)

            self.grid.addWidget(f, i, 0)

    def get_del_btn_style(self):
        return """
            QPushButton { background-color: #d83b01; color: white; border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #ff5522; }
            QPushButton:pressed { background-color: #b33000; }
        """

    def trash(self, fid, widget):
        if self.db.move_to_trash(fid):
            widget.hide()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "削除失敗", "ファイルの削除に失敗しました。\nログを確認してください。")

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()


if __name__ == "__main__":
    setup_logging()
    app = QApplication(sys.argv)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "photos.db")
    db = DatabaseManager(db_path)
    window = QWidget()
    window.setWindowTitle("重複整理 - デザイン統一版")
    window.resize(1100, 750)
    layout = QVBoxLayout(window)
    layout.addWidget(DuplicatePage(db))
    window.show()
    sys.exit(app.exec())