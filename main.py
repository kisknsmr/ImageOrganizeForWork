import sys
import os
import traceback
import time

# --- クラッシュ対策 ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.stdout.reconfigure(encoding='utf-8')
print("--- APP START ---", flush=True)

try:
    print("Pre-loading torch library...", flush=True)
    import torch

    print("Torch loaded.", flush=True)
except ImportError:
    print("Torch not found.", flush=True)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QStackedWidget, QProgressBar, QListView, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, QAbstractListModel, QSize, QThreadPool, QModelIndex, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor

print("Loading Core...", flush=True)
from core import DatabaseManager, ScannerThread, AnalyzerThread, ImageLoader, setup_logging

print("Loading Modules...", flush=True)
from modules.duplicate_ui import DuplicatePage
from modules.blur_ui import BlurPage
from modules.similarity_ui import SimilarityPage
from modules.sorter_ui import SorterPage
from modules.clustering_ui import ClusteringPage
from modules.manual_sorter_ui import ManualSorterPage

print("All Modules Loaded.", flush=True)
setup_logging()


# --- DBResetWorker ---
class DBResetWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, db, scanner, analyzer):
        super().__init__()
        self.db = db
        self.scanner = scanner
        self.analyzer = analyzer

    def run(self):
        print("DBResetWorker: Start resetting sequence...", flush=True)
        if self.scanner and self.scanner.isRunning():
            self.scanner.stop()
            self.scanner.wait()
        if self.analyzer and self.analyzer.isRunning():
            self.analyzer.stop()
            self.analyzer.wait()

        print("DBResetWorker: Rebuilding DB...", flush=True)
        try:
            self.db.rebuild_db()
            msg = "DB初期化完了"
        except Exception as e:
            msg = f"初期化エラー: {e}"
        self.finished.emit(msg)


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
        if row >= len(self.file_list): return
        self.image_cache[row] = image
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoSortX - AI Edition (v2.1)")
        self.resize(1300, 850)
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QWidget { color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 14px; }
            QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; background-color: #1e1e1e; }
            QProgressBar::chunk { background-color: #007acc; }
            QListView, QListWidget { background-color: #1e1e1e; border: none; }
            QLabel.sidebar-header {
                color: #888; font-weight: bold; font-size: 12px; margin-top: 15px; margin-bottom: 5px; padding-left: 10px;
            }
        """)

        self.db = DatabaseManager()
        self.scanner = None
        self.analyzer = None
        self.reset_worker = None

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background-color: #1e1e1e; border-right: 1px solid #333;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(5, 10, 5, 10)
        side_layout.setSpacing(2)

        btn_style = """
            QPushButton { background-color: transparent; border: none; padding: 10px 15px; text-align: left; font-size: 14px; border-radius: 5px; }
            QPushButton:hover { background-color: #333; }
            QPushButton:pressed { background-color: #007acc; color: white; }
        """

        # A. MAIN
        lbl_main = QLabel("📂 MAIN")
        lbl_main.setProperty("class", "sidebar-header")
        side_layout.addWidget(lbl_main)

        btn_home = QPushButton("🏠  ホーム / 取込")
        btn_home.setStyleSheet(btn_style)
        btn_home.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        side_layout.addWidget(btn_home)

        btn_view = QPushButton("🖼  ギャラリー")
        btn_view.setStyleSheet(btn_style)
        btn_view.clicked.connect(self.show_gallery)
        side_layout.addWidget(btn_view)

        # B. CLEANUP
        lbl_clean = QLabel("🗑️ CLEANUP")
        lbl_clean.setProperty("class", "sidebar-header")
        side_layout.addWidget(lbl_clean)

        btn_dup = QPushButton("👯  重複整理")
        btn_dup.setStyleSheet(btn_style)
        btn_dup.clicked.connect(self.show_duplicate_page)
        side_layout.addWidget(btn_dup)

        btn_blur = QPushButton("🌫  ピンボケ整理")
        btn_blur.setStyleSheet(btn_style)
        btn_blur.clicked.connect(self.show_blur_page)
        side_layout.addWidget(btn_blur)

        btn_sim = QPushButton("👥  類似整理")
        btn_sim.setStyleSheet(btn_style)
        btn_sim.clicked.connect(self.show_similarity_page)
        side_layout.addWidget(btn_sim)

        # C. ORGANIZE
        lbl_org = QLabel("📦 ORGANIZE")
        lbl_org.setProperty("class", "sidebar-header")
        side_layout.addWidget(lbl_org)

        btn_manual = QPushButton("🗂  手動仕分け")
        btn_manual.setStyleSheet(btn_style)
        btn_manual.clicked.connect(self.show_manual_sorter_page)
        side_layout.addWidget(btn_manual)

        btn_sort = QPushButton("📂  スマート整理 (AI)")
        btn_sort.setStyleSheet(btn_style)
        btn_sort.clicked.connect(self.show_sorter_page)
        side_layout.addWidget(btn_sort)

        btn_cluster = QPushButton("🧩  自動グルーピング")
        btn_cluster.setStyleSheet(btn_style)
        btn_cluster.clicked.connect(self.show_clustering_page)
        side_layout.addWidget(btn_cluster)

        side_layout.addStretch()

        # D. SYSTEM
        lbl_sys = QLabel("⚙️ SYSTEM")
        lbl_sys.setProperty("class", "sidebar-header")
        side_layout.addWidget(lbl_sys)

        self.lbl_lib_info = QLabel("ライブラリ: 未作成")
        self.lbl_lib_info.setStyleSheet("font-size: 11px; color: #888; padding-left: 10px;")
        self.lbl_lib_info.setWordWrap(True)
        side_layout.addWidget(self.lbl_lib_info)

        self.btn_reset = QPushButton("⚠️ DB全初期化")
        self.btn_reset.setStyleSheet("""
            QPushButton { background-color: #3a1e1e; color: #ff6666; border: 1px solid #552222; border-radius: 4px; padding: 8px; margin-top: 5px;}
            QPushButton:hover { background-color: #552222; }
        """)
        self.btn_reset.clicked.connect(self.reset_db)
        side_layout.addWidget(self.btn_reset)

        # --- Stack ---
        self.stack = QStackedWidget()

        # Home
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

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("height: 8px;")

        home_layout.addStretch()
        home_layout.addWidget(self.lbl_status)
        home_layout.addLayout(btn_area)
        home_layout.addSpacing(30)
        home_layout.addWidget(self.progress_bar)
        home_layout.addStretch()
        self.stack.addWidget(home_page)

        # Gallery
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

        # Modules
        self.duplicate_page = DuplicatePage(self.db)
        self.blur_page = BlurPage(self.db)
        self.sim_page = SimilarityPage(self.db)
        self.manual_sorter_page = ManualSorterPage(self.db)
        self.sorter_page = SorterPage(self.db)
        self.clustering_page = ClusteringPage()

        self.stack.addWidget(self.duplicate_page)
        self.stack.addWidget(self.blur_page)
        self.stack.addWidget(self.sim_page)
        self.stack.addWidget(self.manual_sorter_page)
        self.stack.addWidget(self.sorter_page)
        self.stack.addWidget(self.clustering_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)

        self.update_library_info()
        QTimer.singleShot(500, self.check_startup_sync)

    # --- Methods ---
    def update_library_info(self):
        count = self.db.get_file_count()
        path = self.db.get_setting("root_path")
        if count == 0:
            self.lbl_lib_info.setText("ライブラリ: 未作成\n(スキャンを実行してください)")
        else:
            folder_name = os.path.basename(path) if path else "不明"
            self.lbl_lib_info.setText(f"ライブラリ: 作成済み\n枚数: {count} 枚\n場所: .../{folder_name}")

    def check_startup_sync(self):
        root_path = self.db.get_setting("root_path")
        if root_path and os.path.exists(root_path):
            ans = QMessageBox.question(self, "同期確認",
                                       f"前回スキャンしたフォルダ:\n{root_path}\n\nライブラリと同期（差分更新）しますか？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans == QMessageBox.StandardButton.Yes:
                self.run_scanner(root_path)

    def start_scan(self):
        last_path = self.db.get_setting("root_path")
        folder = QFileDialog.getExistingDirectory(self, "スキャンフォルダ選択", last_path if last_path else "")
        if not folder: return

        if self.db.get_file_count() > 0:
            ans = QMessageBox.question(self, "更新確認",
                                       f"ライブラリは既に存在します。\n\n選択したフォルダ: {os.path.basename(folder)}\n\nこのフォルダに対してライブラリを更新（同期）しますか？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes: return

        self.run_scanner(folder)

    def run_scanner(self, folder):
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
        if QMessageBox.critical(self, '警告',
                                "【本当に初期化しますか？】\n\n全ての解析データ、サムネイル、設定が削除されます。\n実際の画像ファイルは消えませんが、分類作業はリセットされます。",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            print("Main: Reset requested.", flush=True)
            self.lbl_status.setText("初期化中... (応答なしになってもお待ちください)")
            self.lock_buttons(True)
            self.btn_reset.setEnabled(False)

            self.model.clear()
            self.reset_worker = DBResetWorker(self.db, self.scanner, self.analyzer)
            self.reset_worker.finished.connect(self.on_reset_finished)
            self.reset_worker.start()

    def on_reset_finished(self, msg):
        self.lbl_status.setText(msg)
        self.lock_buttons(False)
        self.update_library_info()
        QMessageBox.information(self, "完了", msg)

    def on_finished(self, msg):
        self.lbl_status.setText(msg)
        self.lock_buttons(False)
        self.progress_bar.setValue(100)
        self.update_library_info()

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

    # ★修正: 正しいメソッド名を呼び出し
    def show_manual_sorter_page(self):
        self.manual_sorter_page.refresh_source_list()
        self.stack.setCurrentWidget(self.manual_sorter_page)

    def show_sorter_page(self):
        self.sorter_page.load_images()
        self.stack.setCurrentWidget(self.sorter_page)

    def show_clustering_page(self):
        self.stack.setCurrentWidget(self.clustering_page)

    def closeEvent(self, event):
        self.db.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())