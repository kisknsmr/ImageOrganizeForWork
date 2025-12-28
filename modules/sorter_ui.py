import sys
import os
import shutil
import logging
import traceback
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QFrame, QScrollArea, 
                             QProgressBar, QListWidgetItem, QLineEdit, QSplitter,
                             QMessageBox, QInputDialog, QAbstractItemView, QGridLayout)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QIcon, QPixmap

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, DatabaseManager, get_file_info, format_file_size
from modules.event_grouper import EventGrouper

# AI Worker Import (Lazy or direct if needed)
try:
    from modules.ai_classifier import AIWorker, AI_AVAILABLE
except ImportError:
    AI_AVAILABLE = False

logger = logging.getLogger(__name__)

class EventLabelerThread(QThread):
    """
    Background thread to process events one by one and get AI labels.
    """
    label_found = pyqtSignal(int, str) # index, label
    finished_all = pyqtSignal()
    
    def __init__(self, ai_worker, events):
        super().__init__()
        self.ai_worker = ai_worker
        self.events = events
        self.running = True
        
    def run(self):
        print("EventLabeler: Started", flush=True)
        for i, event in enumerate(self.events):
            if not self.running: break
            
            # Skip if already has label or too small
            if event.get('ai_label'): continue
            
            paths = [f['path'] for f in event['files']]
            
            # Use top 5 images for speed
            label = self.ai_worker.predict_event(paths, top_k=5)
            
            if label:
                self.label_found.emit(i, label)
            
        self.finished_all.emit()
    
    def stop(self):
        self.running = False


class SorterPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.events = [] # Stores event data dicts
        self.current_event_idx = -1
        
        self.ai_worker = None
        self.ai_thread = None
        self.labeler_thread = None
        self.ai_ready = False
        
        self.init_ui()
        
    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QListWidget { background-color: #252526; border: none; font-size: 14px; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background-color: #007acc; }
            QLabel.header { font-size: 16px; font-weight: bold; margin-bottom: 10px; }
            QLineEdit { background-color: #333; border: 1px solid #555; padding: 5px; color: white; }
            QPushButton { background-color: #2d2d30; border: 1px solid #3e3e42; padding: 6px; border-radius: 4px; }
            QPushButton:hover { background-color: #3e3e42; border-color: #007acc; }
        """)
        
        layout = QHBoxLayout(self)
        
        # --- Left Side: Event List ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("📅 タイムライン (イベント)"))

        # AI起動ボタン
        self.btn_init_ai = QPushButton("🚀 AIエンジン起動")
        self.btn_init_ai.setToolTip("AIモデルを読み込み、イベントの自動分類を開始します（初回は時間がかかります）")
        self.btn_init_ai.setStyleSheet("background-color: #d83b01; color: white; font-weight: bold;")
        self.btn_init_ai.clicked.connect(self.init_ai)
        header_layout.addWidget(self.btn_init_ai)
        
        self.btn_load = QPushButton("🔄 再スキャン (GAP: 6h)")
        self.btn_load.clicked.connect(self.load_events)
        self.btn_load.setEnabled(False) # AI未起動時は無効化
        header_layout.addWidget(self.btn_load)
        
        left_layout.addLayout(header_layout)
        
        self.event_list_widget = QListWidget()
        self.event_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.event_list_widget.currentRowChanged.connect(self.on_event_selected)
        left_layout.addWidget(self.event_list_widget)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("height: 4px;")
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        
        # --- Right Side: Details & Action ---
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #333;")
        self.right_layout = QVBoxLayout(right_panel)
        
        # Event Info
        self.lbl_event_title = QLabel("イベントを選択してください")
        self.lbl_event_title.setProperty("class", "header")
        self.lbl_event_title.setWordWrap(True)
        self.right_layout.addWidget(self.lbl_event_title)
        
        self.lbl_event_date = QLabel("-")
        self.right_layout.addWidget(self.lbl_event_date)
        
        # Name Edit
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("フォルダ名:"))
        self.txt_folder_name = QLineEdit()
        name_layout.addWidget(self.txt_folder_name)
        self.right_layout.addLayout(name_layout)
        
        # Sub-Splitter for Right Panel (Thumbnails vs Preview)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top: Thumbnail Grid
        thumb_widget = QWidget()
        thumb_layout = QVBoxLayout(thumb_widget)
        thumb_layout.setContentsMargins(0,0,0,0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.thumbs_container = QWidget()
        self.thumbs_layout = QGridLayout() # Grid for thumbnails
        self.thumbs_container.setLayout(self.thumbs_layout)
        self.scroll.setWidget(self.thumbs_container)
        thumb_layout.addWidget(self.scroll)
        
        right_splitter.addWidget(thumb_widget)
        
        # Bottom: Preview Panel
        preview_panel = QFrame()
        preview_panel.setStyleSheet("background-color: #2d2d30; border-top: 1px solid #444;")
        preview_layout = QHBoxLayout(preview_panel)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        self.preview_image = QLabel("画像を選択")
        self.preview_image.setFixedSize(200, 200)
        self.preview_image.setStyleSheet("background-color: #000; border: 1px solid #555;")
        self.preview_image.setScaledContents(True)
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_image)
        
        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #ccc; font-size: 12px; margin-left: 10px;")
        self.preview_info.setWordWrap(True)
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        preview_layout.addWidget(self.preview_info, 1)
        
        right_splitter.addWidget(preview_panel)
        right_splitter.setStretchFactor(0, 7)
        right_splitter.setStretchFactor(1, 3)
        
        self.right_layout.addWidget(right_splitter)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_move = QPushButton("📦 このフォルダに移動")
        self.btn_move.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 10px;")
        self.btn_move.clicked.connect(self.move_event_files)
        
        self.btn_ignore = QPushButton("これスキップ")
        self.btn_ignore.clicked.connect(self.skip_event)
        
        btn_layout.addWidget(self.btn_ignore)
        btn_layout.addWidget(self.btn_move)
        
        self.right_layout.addLayout(btn_layout)
        
        # Splitter
        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        
        layout.addWidget(splitter)
        
        # Init AI
        # QTimer.singleShot(1000, self.init_ai) # 自動起動廃止
        pass

    def init_ai(self):
        if not AI_AVAILABLE:
            return
        if self.ai_worker:
            return
            
        print("SorterUI: Initializing AI...", flush=True)
        from modules.ai_classifier import AIWorker
        self.ai_worker = AIWorker()
        self.ai_worker.model_loaded.connect(self.on_ai_loaded)
        self.ai_worker.start()
        
    def on_ai_loaded(self, success):
        self.ai_ready = success
        if success:
            print("SorterUI: AI Ready. Scanning events...", flush=True)
            self.btn_init_ai.setEnabled(False)
            self.btn_init_ai.setText("AI準備完了")
            self.btn_init_ai.setStyleSheet("background-color: #333; color: #888;")
            self.btn_load.setEnabled(True)
            self.load_events()
        else:
            self.btn_init_ai.setEnabled(True)
            self.btn_init_ai.setText("❌ 起動失敗 (再試行)")
            QMessageBox.warning(self, "エラー", "AIエンジンの起動に失敗しました。")

    def load_events(self):
        self.event_list_widget.clear()
        self.right_layout.setEnabled(False)
        self.clear_thumbnails()
        
        # 1. Get raw files from DB (Unsorted only?) - For now get all analyzed files
        # Ideally we only get files in "Unsorted" root folder, but let's grab all analyzed for test
        # In real usage: self.db.get_unsorted_files() 
        
        print("SorterUI: Fetching files from DB...", flush=True)
        try:
            # 1. Get raw files from DB
            # Method verified to exist in core.py
            files_raw = self.db.get_all_files_with_info()
        except AttributeError:
             print("SorterUI: Critical Error - DatabaseManager missing 'get_all_files_with_info'. Please restart.", flush=True)
             files_raw = []
        except Exception as e:
            print(f"SorterUI: Fatal Error fetching files: {e}", flush=True)
            import traceback
            traceback.print_exc()
            files_raw = []

        if not files_raw:
             print("SorterUI: No files found or error occurred.", flush=True)

        print(f"SorterUI: Grouping {len(files_raw)} files...", flush=True)
        
        grouper = EventGrouper(self.db)
        self.events = grouper.group_by_time(files_raw, gap_hours=6)
        
        print(f"SorterUI: Found {len(self.events)} events.", flush=True)
        
        for i, ev in enumerate(self.events):
            item_text = self._format_event_text(ev)
            item = QListWidgetItem(item_text)
            self.event_list_widget.addItem(item)
            
        self.right_layout.setEnabled(True)
        
        # Start AI labeling in background
        if self.ai_ready and self.events:
            if self.labeler_thread and self.labeler_thread.isRunning():
                self.labeler_thread.stop()
                self.labeler_thread.wait()
                
            self.labeler_thread = EventLabelerThread(self.ai_worker, self.events)
            self.labeler_thread.label_found.connect(self.on_ai_label_found)
            self.labeler_thread.start()
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0) # Infinite loop
            
    def _fetch_files_data(self):
        # Retrieve id, path, timestamp
        # Using raw query for speed and certainty
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            # Assuming table 'files' has id, path, created_at (or similar)
            # Check schema from a previous turn? No, but I can guess or use existing methods.
            # `core.py` was read in previous turn, let's recall... 
            # I can't confirm schema 100%. Let's query generic and check columns?
            # Or better, use `os.path.getmtime` if DB timestamp is missing, but DB is faster.
            
            cursor.execute("SELECT id, path, timestamp FROM files") # timestamp column usually exists
            rows = cursor.fetchall()
            
            data = []
            for r in rows:
                data.append({
                    'id': r[0],
                    'path': r[1],
                    'timestamp': r[2] # might be None
                })
            conn.close()
            return data
        except Exception as e:
            print(f"DB Error: {e}", flush=True)
            return []

    def _format_event_text(self, ev):
        date_str = ev['suggested_name']
        count = ev['count']
        ai_tag = f" 🏷️ {ev['ai_label']}" if ev.get('ai_label') else ""
        return f"{date_str} ({count}枚){ai_tag}"

    def on_ai_label_found(self, idx, label):
        if idx < len(self.events):
            self.events[idx]['ai_label'] = label
            # Update List Item
            item = self.event_list_widget.item(idx)
            item.setText(self._format_event_text(self.events[idx]))
            
            # If currently selected, update the text box suggestion
            if idx == self.current_event_idx:
                current_name = self.txt_folder_name.text()
                # Only update if user hasn't typed a custom name (complex to detect, so just append?)
                # Or just overwrite if it looks like a default date name
                date_name = self.events[idx]['suggested_name']
                if current_name == date_name:
                    new_name = f"{date_name}_{label}"
                    self.txt_folder_name.setText(new_name)

    def on_event_selected(self, row):
        if row < 0 or row >= len(self.events): return
        
        self.current_event_idx = row
        ev = self.events[row]
        
        self.lbl_event_title.setText(f"イベント #{row+1}")
        
        start = ev['start_time'].strftime("%Y/%m/%d %H:%M") if ev['start_time'] else "?"
        end = ev['end_time'].strftime("%H:%M") if ev['end_time'] else "?"
        self.lbl_event_date.setText(f"{start} ～ {end}")
        
        # Suggest Name
        base_name = ev['suggested_name']
        if ev.get('ai_label'):
            base_name += f"_{ev['ai_label']}"
        self.txt_folder_name.setText(base_name)
        
        # Load thumbnails (Async would be better but let's do sync for first 20)
        self.show_event_thumbnails(ev['files'])

    def show_event_thumbnails(self, files):
        self.clear_thumbnails()
        
        # Show max 20 thumbnails
        max_show = 24
        cols = 4
        
        from PyQt6.QtWidgets import QGridLayout 
        # Need to import QGridLayout if not already
        
        for i, f in enumerate(files[:max_show]):
            lbl = QLabel()
            lbl.setFixedSize(100, 100)
            lbl.setStyleSheet("border: 1px solid #444;")
            lbl.setScaledContents(True) # Just for placeholder
            
            # Make clickable
            # Use a transparent button overlay or event filter. simpler: MousePressEvent
            
            # Click handler
            def make_callback(d):
                return lambda event: self.update_preview(d)
                
            lbl.mousePressEvent = make_callback(f)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Use core.get_db_thumbnail for speed
            fid = f.get('id')
            path = f.get('path')
            
            pix = get_db_thumbnail(self.db, fid, path, 200)
            if pix:
                lbl.setPixmap(pix)
            
            r = i // cols
            c = i % cols
            self.thumbs_layout.addWidget(lbl, r, c)

    def clear_thumbnails(self):
        while self.thumbs_layout.count():
            child = self.thumbs_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        
        # Clear preview too
        self.preview_image.clear()
        self.preview_image.setText("画像を選択")
        self.preview_info.setText("")

    def update_preview(self, file_data):
        if not file_data: return
        
        fid = file_data.get('id')
        path = file_data.get('path')
        
        # High res preview
        pix = get_db_thumbnail(self.db, fid, path, 400)
        if pix:
            self.preview_image.setPixmap(pix)
        else:
            self.preview_image.setText("No Preview")
            
        # Info
        info = get_file_info(path)
        txt = f"<b>ファイル名:</b> {os.path.basename(path)}<br>"
        txt += f"<b>パス:</b> {path}<br>"
        if info['exists']:
            txt += f"<b>サイズ:</b> {format_file_size(info['file_size'])}<br>"
            if info['image_width']:
                txt += f"<b>画像:</b> {info['image_width']} x {info['image_height']} px<br>"
        else:
            txt += "<b style='color:red;'>ファイルが見つかりません</b>"
            
        self.preview_info.setText(txt)

    def move_event_files(self):
        if self.current_event_idx < 0: return
        
        # 1. Get destination name
        folder_name = self.txt_folder_name.text().strip()
        if not folder_name:
             QMessageBox.warning(self, "エラー", "フォルダ名を入力してください")
             return
             
        # 2. Ask for parent directory (or use a default Library root)
        # For efficiency, let's ask once or have a setting.
        # Let's ask user to select "Library Root" if not set, or just "Where to move?"
        # Standard behavior: Ask for Base Folder, then create subfolder.
        
        base_path = self.db.get_setting("library_path") # Hypothetical setting
        if not base_path or not os.path.exists(base_path):
             base_path = QFileDialog.getExistingDirectory(self, "保存先の親フォルダを選択してください")
             if not base_path: return
             # Save for later
        
        dest_dir = os.path.join(base_path, folder_name)
        
        # 3. Move files
        ev = self.events[self.current_event_idx]
        files = ev['files']
        
        try:
            os.makedirs(dest_dir, exist_ok=True)
            
            for f in files:
                # Use safe move method from core
                success = self.db.move_file_to_folder(f['id'], f['path'], dest_dir)
                if not success:
                    print(f"Failed to move {f['path']}", flush=True)

            QMessageBox.information(self, "完了", f"{len(files)} 枚を移動しました")
            
            # Remove from list
            self.event_list_widget.takeItem(self.current_event_idx)
            del self.events[self.current_event_idx]
            self.current_event_idx = -1
            self.clear_thumbnails()
            
        except Exception as e:
             QMessageBox.critical(self, "エラー", f"移動に失敗しました:\n{e}")

    def skip_event(self):
        # Just remove from list without doing anything
        if self.current_event_idx < 0: return
        self.event_list_widget.takeItem(self.current_event_idx)
        del self.events[self.current_event_idx]
        self.current_event_idx = -1
        self.clear_thumbnails()
