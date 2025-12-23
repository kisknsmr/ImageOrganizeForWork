import sys
import os
import traceback

# --- ★クラッシュ対策 (順序厳守) ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.stdout.reconfigure(encoding='utf-8')
print("--- APP START ---", flush=True)

# プレロード (PyQtより先にTorchを読む)
try:
    print("Pre-loading torch library...", flush=True)
    import torch

    print("Torch loaded successfully.", flush=True)
except ImportError:
    print("Torch not found.", flush=True)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QStackedWidget, QProgressBar, QListView, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, QAbstractListModel, QSize, QThreadPool, QModelIndex
from PyQt6.QtGui import QColor

print("Loading Core...", flush=True)
from core import DatabaseManager, ScannerThread, AnalyzerThread, ImageLoader, setup_logging

print("Loading Modules...", flush=True)
from modules.duplicate_ui import DuplicatePage
from modules.blur_ui import BlurPage
from modules.similarity_ui import SimilarityPage
from modules.sorter_ui import SorterPage
# ★追加: クラスタリング画面
from modules.clustering_ui import ClusteringPage

print("All Modules Loaded.", flush=True)
setup_logging()


class PhotoModel(QAbstractListModel):
    def __init__(self, db_manager, icon_size=QSize(180, 180)):
        super().__init__()
        self.db = db_manager
        self.file_list = []
        self.image_cache = {}
        self.icon_size = icon_size
        self.thread_pool = QThreadPool()

    def reload(self):
        self.beginResetModel()
        self.file_list = self.db.get_all_files()
        self.image_cache.clear()
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.file_list = []
        self.image_cache = {}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.file_list)

    def data(self, index, role):
        if not index.isValid(): return None
        row = index.row()
        if role == Qt.ItemDataRole.DecorationRole:
            if row in self.image_cache:
                return self.image_cache[row]
            else:
                self.load_image_async(row)
                return QColor("#2b2b2b")
        if role == Qt.ItemDataRole.ToolTipRole: return self.file_list[row]
        return None

    def load_image_async(self, row):
        if row in self.image_cache: return
        loader = ImageLoader(row, self.file_list[row], self.icon_size)
        loader.signals.finished.connect(self.on_loaded)
        self.thread_pool.start(loader)

    def on_loaded(self, row, image):
        self.image_cache[row] = image
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoSortX - AI Edition")
        self.resize(1200, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QWidget { color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
            QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; background-color: #1e1e1e; }
            QProgressBar::chunk { background-color: #007acc; }
            QListView, QListWidget { background-color: #1e1e1e; border: none; }
        """)

        self.db = DatabaseManager()

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background-color: #1e1e1e; border-right: 1px solid #333;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 10, 0, 10)

        # --- サイドバーボタン ---
        btn_home = QPushButton("🏠  ホーム / 取込")
        btn_home.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        btn_view = QPushButton("🖼  ギャラリー")
        btn_view.clicked.connect(self.show_gallery)

        btn_dup = QPushButton("👯  重複整理")
        btn_dup.clicked.connect(self.show_duplicate_page)

        btn_blur = QPushButton("🌫  ピンボケ整理")
        btn_blur.clicked.connect(self.show_blur_page)

        btn_sim = QPushButton("👥  類似整理")
        btn_sim.clicked.connect(self.show_similarity_page)

        btn_sort = QPushButton("📂  スマート整理")
        btn_sort.clicked.connect(self.show_sorter_page)

        # ★追加: クラスタリングボタン
        btn_cluster = QPushButton("🧩  自動グルーピング")
        btn_cluster.clicked.connect(self.show_clustering_page)

        # ボタンを配置
        buttons = [btn_home, btn_view, btn_dup, btn_blur, btn_sim, btn_sort, btn_cluster]
        for btn in buttons:
            btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; padding: 15px 20px; text-align: left; font-size: 15px; border-left: 4px solid transparent; }
                QPushButton:hover { background-color: #333; }
                QPushButton:pressed { background-color: #007acc; color: white; }
            """)
            side_layout.addWidget(btn)

        side_layout.addStretch()

        # --- メインコンテンツ ---
        self.stack = QStackedWidget()

        # 0. Home
        home_page = QWidget()
        home_layout = QVBoxLayout(home_page)
        self.lbl_status = QLabel("フォルダを選択して取込、または解析を行ってください")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("font-size: 16px; margin-bottom: 20px;")

        btn_area = QHBoxLayout()
        self.btn_scan = QPushButton("1. フォルダ同期 (Scan)")
        self.btn_scan.setFixedSize(220, 60)
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_scan.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 5px;")

        self.btn_analyze = QPushButton("2. 詳細解析 (Analyze)")
        self.btn_analyze.setFixedSize(220, 60)
        self.btn_analyze.clicked.connect(self.start_analyze)
        self.btn_analyze.setStyleSheet(
            "background-color: #d83b01; color: white; font-weight: bold; border-radius: 5px;")

        btn_area.addStretch()
        btn_area.addWidget(self.btn_scan)
        btn_area.addSpacing(20)
        btn_area.addWidget(self.btn_analyze)
        btn_area.addStretch()

        reset_area = QHBoxLayout()
        self.btn_reset = QPushButton("⚠️ DB全初期化")
        self.btn_reset.setFixedSize(150, 40)
        self.btn_reset.clicked.connect(self.reset_db)
        self.btn_reset.setStyleSheet(
            "QPushButton { background-color: #333; color: #888; border: 1px solid #555; border-radius: 5px; }")
        reset_area.addStretch()
        reset_area.addWidget(self.btn_reset)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("height: 8px;")

        home_layout.addStretch()
        home_layout.addWidget(self.lbl_status)
        home_layout.addLayout(btn_area)
        home_layout.addSpacing(30)
        home_layout.addWidget(self.progress_bar)
        home_layout.addStretch()
        home_layout.addLayout(reset_area)
        self.stack.addWidget(home_page)

        # 1. Gallery
        self.gallery_view = QListView()
        self.gallery_view.setViewMode(QListView.ViewMode.IconMode)
        self.gallery_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.gallery_view.setUniformItemSizes(True)
        self.gallery_view.setGridSize(QSize(200, 200))
        self.gallery_view.setIconSize(QSize(180, 180))
        self.gallery_view.setSpacing(10)
        self.model = PhotoModel(self.db)
        self.gallery_view.setModel(self.model)

        gallery_page = QWidget()
        gallery_layout = QVBoxLayout(gallery_page)
        gallery_layout.addWidget(self.gallery_view)
        self.stack.addWidget(gallery_page)

        # 各機能ページ
        self.duplicate_page = DuplicatePage(self.db)
        self.blur_page = BlurPage(self.db)
        self.sim_page = SimilarityPage(self.db)
        self.sorter_page = SorterPage(self.db)
        self.clustering_page = ClusteringPage()  # ★追加

        self.stack.addWidget(self.duplicate_page)
        self.stack.addWidget(self.blur_page)
        self.stack.addWidget(self.sim_page)
        self.stack.addWidget(self.sorter_page)
        self.stack.addWidget(self.clustering_page)  # ★追加

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)

    def start_scan(self):
        folder = QFileDialog.getExistingDirectory(self, "スキャンフォルダ選択")
        if folder:
            self.lock_buttons(True)
            self.scanner = ScannerThread(folder, self.db)
            self.scanner.progress.connect(self.progress_bar.setValue)
            self.scanner.status.connect(self.lbl_status.setText)
            self.scanner.finished.connect(lambda: self.on_finished("スキャン完了！解析を行ってください"))
            self.scanner.start()

    def start_analyze(self):
        self.lock_buttons(True)
        self.analyzer = AnalyzerThread(self.db)
        self.analyzer.progress.connect(lambda c, t: self.progress_bar.setValue(int(c / t * 100) if t else 0))
        self.analyzer.status.connect(self.lbl_status.setText)
        self.analyzer.finished.connect(lambda: self.on_finished("解析完了"))
        self.analyzer.start()

    def reset_db(self):
        if QMessageBox.question(self, '確認', "DBを初期化しますか？") == QMessageBox.StandardButton.Yes:
            self.db.rebuild_db()
            self.model.clear()
            self.lbl_status.setText("DB初期化完了")

    def on_finished(self, msg):
        self.lbl_status.setText(msg)
        self.lock_buttons(False)
        self.progress_bar.setValue(100)

    def lock_buttons(self, locked):
        self.btn_scan.setEnabled(not locked)
        self.btn_analyze.setEnabled(not locked)
        self.btn_reset.setEnabled(not locked)

    def show_gallery(self):
        self.model.reload()
        self.stack.setCurrentIndex(1)

    def show_duplicate_page(self):
        self.duplicate_page.load_data()
        self.stack.setCurrentWidget(self.duplicate_page)

    def show_blur_page(self):
        self.blur_page.load_data()
        self.stack.setCurrentWidget(self.blur_page)

    def show_similarity_page(self):
        self.stack.setCurrentWidget(self.sim_page)

    def show_sorter_page(self):
        print("Main: Switching to Sorter Page", flush=True)
        self.sorter_page.load_images()
        self.stack.setCurrentWidget(self.sorter_page)

    # ★追加: クラスタリングページ表示
    def show_clustering_page(self):
        print("Main: Switching to Clustering Page", flush=True)
        self.stack.setCurrentWidget(self.clustering_page)

    def closeEvent(self, event):
        self.db.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())