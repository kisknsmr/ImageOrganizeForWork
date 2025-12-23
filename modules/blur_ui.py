import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QSlider, QListWidgetItem,
                             QApplication, QFrame, QScrollArea, QGridLayout,
                             QSizePolicy, QProgressBar, QButtonGroup)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette, QColor

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager

logger = logging.getLogger(__name__)


# --- Worker ---
class BlurLoadWorker(QThread):
    progress = pyqtSignal(int, int)
    item_loaded = pyqtSignal(dict)  # 辞書ごと送る
    finished = pyqtSignal(int)

    def __init__(self, db, threshold):
        super().__init__()
        self.db = db
        self.threshold = threshold
        self.is_running = True

    def run(self):
        rows = self.db.get_blurry_files(self.threshold)
        total = len(rows)
        for i, (fid, path) in enumerate(rows):
            if not self.is_running: break
            # データパッケージング
            item = {'id': fid, 'path': path}
            self.item_loaded.emit(item)
            if i % 5 == 0: self.progress.emit(i + 1, total)
        self.finished.emit(total)

    def stop(self):
        self.is_running = False


# --- UI ---
class BlurPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.worker = None
        self.view_mode = "grid"
        self.loaded_items = []  # データを保持
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QLabel { font-size: 13px; }
            QSlider::groove:horizontal { border: 1px solid #3e3e42; background: #2d2d30; height: 6px; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #d83b01; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e0e0e0; border: 1px solid #777; width: 14px; margin: -5px 0; border-radius: 7px; }
            QProgressBar { border: none; background-color: #2d2d30; height: 4px; border-radius: 2px; }
            QProgressBar::chunk { background-color: #d83b01; border-radius: 2px; }
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
        left_layout.setSpacing(15)

        # 設定エリア
        conf_box = QFrame()
        conf_box.setStyleSheet("background-color: #2d2d30; border-radius: 6px; border: 1px solid #3e3e42;")
        conf_layout = QVBoxLayout(conf_box)
        conf_layout.setSpacing(12)

        conf_layout.addWidget(QLabel("ピンボケ判定設定"))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 50)
        self.slider.setValue(20)
        self.slider.valueChanged.connect(self.on_change)
        conf_layout.addWidget(self.slider)

        self.lbl_val = QLabel("閾値: 20")
        conf_layout.addWidget(self.lbl_val)

        self.btn_refresh = QPushButton("リスト更新")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: #d83b01; color: white; border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #ff5522; }
            QPushButton:pressed { background-color: #b33000; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_refresh.clicked.connect(self.load_data)
        conf_layout.addWidget(self.btn_refresh)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        conf_layout.addWidget(self.progress)

        self.lbl_status = QLabel("待機中")
        self.lbl_status.setStyleSheet("color: #888; font-size: 11px;")
        conf_layout.addWidget(self.lbl_status)

        left_layout.addWidget(conf_box)
        left_layout.addStretch()

        # --- 右メインパネル ---
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)

        # ヘッダー
        header_layout = QHBoxLayout()
        header_lbl = QLabel("検出結果")
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

    def on_change(self):
        val = self.slider.value()
        desc = " (廃棄レベル)" if val < 15 else " (かなりボケ)" if val < 30 else " (ソフトフォーカス?)"
        self.lbl_val.setText(f"閾値: {val}{desc}")
        # リセット
        self.clear_grid()
        self.loaded_items = []
        self.lbl_status.setText("設定変更: 更新ボタンを押してください")

    def toggle_view(self, btn):
        self.view_mode = "grid" if btn == self.btn_view_grid else "list"
        if self.loaded_items:
            self.render_all_items()

    def load_data(self):
        self.clear_grid()
        self.loaded_items = []
        self.btn_refresh.setEnabled(False)
        self.progress.setValue(0)
        self.lbl_status.setText("検索中...")

        threshold = self.slider.value()
        self.worker = BlurLoadWorker(self.db, threshold)
        self.worker.item_loaded.connect(self.on_item_loaded)
        self.worker.progress.connect(lambda c, t: self.progress.setValue(int(c / t * 100) if t else 0))
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_item_loaded(self, item):
        self.loaded_items.append(item)
        # 逐次描画
        self.add_single_item(item, len(self.loaded_items) - 1)

    def on_finished(self, total):
        self.btn_refresh.setEnabled(True)
        self.progress.setValue(100)
        if total == 0:
            self.lbl_status.setText("該当なし")
        else:
            self.lbl_status.setText(f"完了: {total}枚")

    def render_all_items(self):
        self.clear_grid()
        for i, item in enumerate(self.loaded_items):
            self.add_single_item(item, i)

    def add_single_item(self, item, index):
        if self.view_mode == "grid":
            self.render_grid_item(item, index)
        else:
            self.render_list_item(item, index)

    def render_grid_item(self, item, index):
        cols = 5
        row, col = divmod(index, cols)
        thumb_size = 120

        f = QFrame()
        f.setFixedSize(140, 180)
        f.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
            QFrame:hover { border-color: #d83b01; background-color: #3e3e42; }
        """)
        l = QVBoxLayout(f)
        l.setContentsMargins(5, 5, 5, 5)
        l.setSpacing(2)

        lbl = QLabel()
        pix = get_db_thumbnail(self.db, item['id'], item['path'], thumb_size)
        lbl.setPixmap(pix)
        lbl.setScaledContents(True)
        lbl.setFixedSize(thumb_size, thumb_size)
        lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

        name_lbl = QLabel(os.path.basename(item['path']))
        name_lbl.setStyleSheet("border: none; font-size: 10px; color: #ccc;")
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setFixedHeight(25)

        btn = QPushButton("削除")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(20)
        btn.setStyleSheet(self.get_del_btn_style())
        btn.clicked.connect(lambda _, fid=item['id'], w=f: self.trash(fid, w))

        l.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addWidget(name_lbl)
        l.addWidget(btn)

        self.grid.addWidget(f, row, col)

    def render_list_item(self, item, index):
        thumb_size = 80
        f = QFrame()
        f.setFixedHeight(100)
        f.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
            QFrame:hover { border-color: #d83b01; background-color: #353538; }
        """)
        l = QHBoxLayout(f)
        l.setContentsMargins(10, 10, 10, 10)
        l.setSpacing(15)

        lbl = QLabel()
        pix = get_db_thumbnail(self.db, item['id'], item['path'], thumb_size)
        lbl.setPixmap(pix)
        lbl.setScaledContents(True)
        lbl.setFixedSize(thumb_size, thumb_size)
        lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

        info_layout = QVBoxLayout()
        name_lbl = QLabel(os.path.basename(item['path']))
        name_lbl.setStyleSheet("border: none; font-size: 14px; font-weight: bold; color: #fff;")
        path_lbl = QLabel(item['path'])
        path_lbl.setStyleSheet("border: none; font-size: 11px; color: #888;")

        info_layout.addWidget(name_lbl)
        info_layout.addWidget(path_lbl)
        info_layout.addStretch()

        btn = QPushButton("ゴミ箱へ")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(80, 30)
        btn.setStyleSheet(self.get_del_btn_style())
        btn.clicked.connect(lambda _, fid=item['id'], w=f: self.trash(fid, w))

        l.addWidget(lbl)
        l.addLayout(info_layout, stretch=1)
        l.addWidget(btn)

        self.grid.addWidget(f, index, 0)

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
    window.setWindowTitle("ピンボケ整理 - デザイン統一版")
    window.resize(1100, 750)
    layout = QVBoxLayout(window)
    layout.addWidget(BlurPage(db))
    window.show()
    sys.exit(app.exec())