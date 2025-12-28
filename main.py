import sys
import os
import traceback
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QStackedWidget, QProgressBar, QListView, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, QSize, QTimer

# --- クラッシュ対策 ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

sys.stdout.reconfigure(encoding='utf-8')

# GUI Components
from gui.splash import SplashScreen
from gui.workers import AppLoader, DBResetWorker
from gui.models import PhotoModel

# Global placeholders for lazy loaded modules
# These will be populated by AppLoader
DatabaseManager = None
ScannerThread = None
AnalyzerThread = None
ImageLoader = None
setup_logging = None
config = None
DuplicatePage = None
BlurPage = None
SimilarityPage = None
SorterPage = None
ClusteringPage = None
ManualSorterPage = None
SmallFileCleanerPage = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoSortX - AI Edition (v2.2)")
        width, height = config.DEFAULT_WINDOW_SIZE
        self.resize(width, height)
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
        sidebar.setFixedWidth(config.SIDEBAR_WIDTH)
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

        btn_small_cleaner = QPushButton("🗑️  小さいファイル削除")
        btn_small_cleaner.setStyleSheet(btn_style)
        btn_small_cleaner.clicked.connect(self.show_small_file_cleaner_page)
        side_layout.addWidget(btn_small_cleaner)

        side_layout.addStretch()

        # D. SYSTEM
        lbl_sys = QLabel("⚙️ SYSTEM")
        lbl_sys.setProperty("class", "sidebar-header")
        side_layout.addWidget(lbl_sys)

        self.lbl_lib_info = QLabel("ライブラリ: 未作成")
        self.lbl_lib_info.setStyleSheet("font-size: 11px; color: #888; padding-left: 10px;")
        self.lbl_lib_info.setWordWrap(True)
        side_layout.addWidget(self.lbl_lib_info)

        # 削除フォルダ設定
        self.btn_trash_setting = QPushButton("🗑️ 削除フォルダ設定")
        self.btn_trash_setting.setStyleSheet(btn_style)
        self.btn_trash_setting.clicked.connect(self.setup_trash_folder)
        side_layout.addWidget(self.btn_trash_setting)

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
        grid_w, grid_h = config.GALLERY_GRID_SIZE
        icon_w, icon_h = config.GALLERY_ICON_SIZE
        self.gallery_view.setGridSize(QSize(grid_w, grid_h))
        self.gallery_view.setIconSize(QSize(icon_w, icon_h))
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
        self.small_file_cleaner_page = SmallFileCleanerPage(self.db)

        self.stack.addWidget(self.duplicate_page)
        self.stack.addWidget(self.blur_page)
        self.stack.addWidget(self.sim_page)
        self.stack.addWidget(self.manual_sorter_page)
        self.stack.addWidget(self.sorter_page)
        self.stack.addWidget(self.clustering_page)
        self.stack.addWidget(self.small_file_cleaner_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)

        self.update_library_info()
        QTimer.singleShot(500, self.check_startup_sync)
        QTimer.singleShot(1000, self.check_trash_folder_setup)

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

    def show_manual_sorter_page(self):
        self.manual_sorter_page.refresh_source_list()
        self.stack.setCurrentWidget(self.manual_sorter_page)

    def show_sorter_page(self):
        self.sorter_page.load_images()
        self.stack.setCurrentWidget(self.sorter_page)

    def show_clustering_page(self):
        self.stack.setCurrentWidget(self.clustering_page)

    def show_small_file_cleaner_page(self):
        self.stack.setCurrentWidget(self.small_file_cleaner_page)

    def check_trash_folder_setup(self):
        """
        起動時に削除フォルダが設定されているか確認
        設定されていない場合は、デフォルトフォルダの作成を提案
        """
        trash_folder = self.db.get_trash_folder()
        if not trash_folder:
            default_trash = config.get_default_trash_folder()
            
            ans = QMessageBox.question(
                self, 
                "削除フォルダ設定",
                "削除フォルダが設定されていません。\n\n"
                f"デフォルト削除フォルダを作成しますか？\n\n"
                f"場所: {default_trash}\n\n"
                "後で「削除フォルダ設定」から変更できます。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(default_trash, exist_ok=True)
                    self.db.set_trash_folder(default_trash)
                    QMessageBox.information(
                        self, 
                        "設定完了",
                        f"削除フォルダを設定しました:\n{default_trash}"
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "エラー",
                        f"削除フォルダの作成に失敗しました:\n{e}"
                    )

    def setup_trash_folder(self):
        """
        削除フォルダの設定ダイアログ
        """
        current_trash = self.db.get_trash_folder()
        default_trash = config.get_default_trash_folder()
        
        msg = "削除フォルダを設定してください。\n\n"
        if current_trash:
            msg += f"現在の設定: {current_trash}\n\n"
        else:
            msg += "現在の設定: 未設定（デフォルトを使用）\n\n"
        msg += f"デフォルト: {default_trash}\n\n"
        msg += "フォルダを選択するか、「デフォルトを使用」を選択してください。"
        
        reply = QMessageBox.question(
            self,
            "削除フォルダ設定",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        
        if reply == QMessageBox.StandardButton.Ok:
            # フォルダ選択ダイアログ
            folder = QFileDialog.getExistingDirectory(
                self,
                "削除フォルダを選択",
                current_trash if current_trash else default_trash
            )
            
            if folder:
                # パス検証
                if not config.validate_path(folder):
                    QMessageBox.warning(
                        self,
                        "エラー",
                        "無効なパスです。別のフォルダを選択してください。"
                    )
                    return
                
                # フォルダが存在しない場合は作成
                if not os.path.exists(folder):
                    try:
                        os.makedirs(folder, exist_ok=True)
                    except Exception as e:
                        QMessageBox.critical(
                            self,
                            "エラー",
                            f"フォルダの作成に失敗しました:\n{e}"
                        )
                        return
                
                # 設定を保存
                self.db.set_trash_folder(folder)
                QMessageBox.information(
                    self,
                    "設定完了",
                    f"削除フォルダを設定しました:\n{folder}"
                )
            else:
                # キャンセルされた場合、デフォルトを使用するか確認
                if not current_trash:
                    reply2 = QMessageBox.question(
                        self,
                        "デフォルト使用",
                        f"デフォルト削除フォルダを使用しますか？\n\n{default_trash}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply2 == QMessageBox.StandardButton.Yes:
                        try:
                            os.makedirs(default_trash, exist_ok=True)
                            self.db.set_trash_folder(default_trash)
                            QMessageBox.information(
                                self,
                                "設定完了",
                                f"デフォルト削除フォルダを設定しました:\n{default_trash}"
                            )
                        except Exception as e:
                            QMessageBox.critical(
                                self,
                                "エラー",
                                f"削除フォルダの作成に失敗しました:\n{e}"
                            )

    def closeEvent(self, event):
        self.db.close()
        event.accept()


# --- Main Entry Point ---
def main():
    app = QApplication(sys.argv)
    
    # 1. Show Splash
    splash = SplashScreen()
    splash.show()
    
    # 2. Start Loading Thread
    loader = AppLoader()
    loader.progress.connect(splash.show_message)
    
    def on_loaded(loaded_objects):
        # Unpack loaded modules to global scope
        global DatabaseManager, ScannerThread, AnalyzerThread, ImageLoader
        global setup_logging, config
        global DuplicatePage, BlurPage, SimilarityPage, SorterPage
        global ClusteringPage, ManualSorterPage, SmallFileCleanerPage
        
        DatabaseManager = loaded_objects.get('DatabaseManager')
        ScannerThread = loaded_objects.get('ScannerThread')
        AnalyzerThread = loaded_objects.get('AnalyzerThread')
        ImageLoader = loaded_objects.get('ImageLoader')
        setup_logging = loaded_objects.get('setup_logging')
        config = loaded_objects.get('config')
        
        DuplicatePage = loaded_objects.get('DuplicatePage')
        BlurPage = loaded_objects.get('BlurPage')
        SimilarityPage = loaded_objects.get('SimilarityPage')
        SorterPage = loaded_objects.get('SorterPage')
        ClusteringPage = loaded_objects.get('ClusteringPage')
        ManualSorterPage = loaded_objects.get('ManualSorterPage')
        SmallFileCleanerPage = loaded_objects.get('SmallFileCleanerPage')
    
        # 3. Show Main Window
        global window
        window = MainWindow()
        window.show()
        splash.finish(window)
        
    loader.finished.connect(on_loaded)
    loader.start()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()