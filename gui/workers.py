import time
import traceback
from PyQt6.QtCore import QThread, pyqtSignal

class AppLoader(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(object) # Return loaded modules/objects if needed
    
    # Store loaded objects to pass back to main
    loaded_objects = {}

    def run(self):
        try:
            self.progress.emit("Loading PyTorch...", 10)
            import torch
            self.loaded_objects['torch'] = torch
            
            self.progress.emit("Loading Core System...", 30)
            from core import ScannerThread, AnalyzerThread, ImageLoader, setup_logging
            from database import DatabaseManager
            from config import config
            
            self.loaded_objects['DatabaseManager'] = DatabaseManager
            self.loaded_objects['ScannerThread'] = ScannerThread
            self.loaded_objects['AnalyzerThread'] = AnalyzerThread
            self.loaded_objects['ImageLoader'] = ImageLoader
            self.loaded_objects['setup_logging'] = setup_logging
            self.loaded_objects['config'] = config
            
            setup_logging()
            
            self.progress.emit("Loading UI Modules (1/5)...", 50)
            from modules.duplicate_ui import DuplicatePage
            self.loaded_objects['DuplicatePage'] = DuplicatePage
            
            self.progress.emit("Loading UI Modules (2/5)...", 60)
            from modules.blur_ui import BlurPage
            self.loaded_objects['BlurPage'] = BlurPage
            
            from modules.similarity_ui import SimilarityPage
            self.loaded_objects['SimilarityPage'] = SimilarityPage
            
            self.progress.emit("Loading UI Modules (3/5)...", 70)
            from modules.sorter_ui import SorterPage
            self.loaded_objects['SorterPage'] = SorterPage
            
            self.progress.emit("Loading UI Modules (4/5)...", 80)
            from modules.clustering_ui import ClusteringPage
            self.loaded_objects['ClusteringPage'] = ClusteringPage
            
            self.progress.emit("Loading UI Modules (5/5)...", 90)
            from modules.manual_sorter_ui import ManualSorterPage
            self.loaded_objects['ManualSorterPage'] = ManualSorterPage
            
            from modules.small_file_cleaner_ui import SmallFileCleanerPage
            self.loaded_objects['SmallFileCleanerPage'] = SmallFileCleanerPage
            
            self.progress.emit("Starting...", 100)
            time.sleep(0.5) # Slight delay to show 100%
            self.finished.emit(self.loaded_objects)
            
        except Exception as e:
            print(f"Loading Error: {e}")
            traceback.print_exc()

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
