import time
import traceback
import logging
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class AppLoader(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object) # Return loaded modules/objects if needed

    def run(self):
        loaded_objects: dict = {}
        try:
            # --- コアシステム読み込み（PyTorch は AI 使用時に遅延ロードするため起動時は読まない）---
            self.progress.emit("コアシステム読み込み中...", 15)
            from src.core import ScannerThread, AnalyzerThread, ImageLoader, setup_logging
            from src.database import DatabaseManager
            from src.config import config
            
            loaded_objects['DatabaseManager'] = DatabaseManager
            loaded_objects['ScannerThread'] = ScannerThread
            loaded_objects['AnalyzerThread'] = AnalyzerThread
            loaded_objects['ImageLoader'] = ImageLoader
            loaded_objects['setup_logging'] = setup_logging
            loaded_objects['config'] = config
            
            setup_logging()
            
            # --- UI モジュール読み込み ---
            self.progress.emit("UIモジュール読み込み中...", 40)
            from modules.duplicate_ui import DuplicatePage
            loaded_objects['DuplicatePage'] = DuplicatePage
            
            self.progress.emit("UIモジュール読み込み中...", 55)
            from modules.blur_ui import BlurPage
            loaded_objects['BlurPage'] = BlurPage
            
            from modules.similarity_ui import SimilarityPage
            loaded_objects['SimilarityPage'] = SimilarityPage
            
            self.progress.emit("UIモジュール読み込み中...", 70)
            from modules.sorter_ui import SorterPage
            loaded_objects['SorterPage'] = SorterPage
            
            self.progress.emit("UIモジュール読み込み中...", 85)
            from modules.manual_sorter_ui import ManualSorterPage
            loaded_objects['ManualSorterPage'] = ManualSorterPage
            
            from modules.small_file_cleaner_ui import SmallFileCleanerPage
            loaded_objects['SmallFileCleanerPage'] = SmallFileCleanerPage

            from modules.trash_list_ui import TrashListPage
            loaded_objects['TrashListPage'] = TrashListPage

            self.progress.emit("起動完了", 100)
            self.finished.emit(loaded_objects)

        except Exception as e:
            logger.error(f"Loading Error: {e}", exc_info=True)
            self.finished.emit(None)  # 起動停止を防ぐため必ず finished を発行

class DBResetWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, db, scanner, analyzer):
        super().__init__()
        self.db = db
        self.scanner = scanner
        self.analyzer = analyzer

    def run(self):
        logger.info("DBResetWorker: Start resetting sequence...")
        if self.scanner and self.scanner.isRunning():
            self.scanner.stop()
            self.scanner.wait()
        if self.analyzer and self.analyzer.isRunning():
            self.analyzer.stop()
            self.analyzer.wait()

        logger.info("DBResetWorker: Rebuilding DB...")
        try:
            self.db.rebuild_db()
            logger.info("DBResetWorker: Database rebuild completed successfully")
            msg = "DB初期化完了"
        except Exception as e:
            logger.error(f"DBResetWorker: Database rebuild failed: {e}", exc_info=True)
            msg = f"初期化エラー: {e}"
        self.finished.emit(msg)
