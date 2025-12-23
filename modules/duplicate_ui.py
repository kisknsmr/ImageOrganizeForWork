import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QListWidgetItem, QScrollArea,
                             QFrame, QApplication, QGridLayout, QButtonGroup, QSizePolicy)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPalette, QColor

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager

logger = logging.getLogger(__name__)


class DuplicatePage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.view_mode = "grid"
        self.current_group_data = []
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

        # --- 右メインパネル ---
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(right_panel)
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

        right_layout.addLayout(header_layout)

        # エリア
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setStyleSheet("border: none; background-color: transparent;")

        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.area.setWidget(self.container)
        right_layout.addWidget(self.area)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

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
        except:
            pass

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

    def render_grid_view(self):
        cols = 5
        thumb_size = 120

        for i, data in enumerate(self.current_group_data):
            f = QFrame()
            f.setFixedSize(140, 180)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)

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
        if self.db.move_to_trash(fid): widget.hide()

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