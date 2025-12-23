import sys
import os
import logging
import traceback
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QFileDialog, QFrame,
                             QGridLayout, QApplication, QSplitter, QScrollArea,
                             QProgressBar, QListWidgetItem)  # ★QListWidgetItemを追加
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager

# インポート遅延
try:
    from modules.ai_classifier import AIWorker, AI_AVAILABLE
except ImportError:
    AI_AVAILABLE = False

logger = logging.getLogger(__name__)


class SorterPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.current_items = []
        self.selected_item = None
        self.target_folders = []

        self.ai_worker = None
        self.ai_model_loaded = False
        self.ai_loading_started = False

        print(f"SorterPage Init: AI_AVAILABLE={AI_AVAILABLE}", flush=True)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QLabel { font-size: 13px; }
            QPushButton {
                background-color: #2d2d30; border: 1px solid #3e3e42; color: #e0e0e0;
                padding: 8px; border-radius: 4px; text-align: left;
            }
            QPushButton:hover { background-color: #3e3e42; border-color: #007acc; }
            QListWidget { background-color: #252526; border: none; }
            QPushButton.ai-suggest {
                border: 1px solid #d83b01; background-color: #3a1e1e;
            }
            QPushButton.ai-suggest:hover {
                background-color: #d83b01; color: white;
            }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(10, 10, 10, 10)

        self.img_list = QListWidget()
        self.img_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.img_list.setIconSize(QSize(160, 160))
        self.img_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.img_list.setSpacing(8)
        self.img_list.itemClicked.connect(self.on_item_clicked)

        btn_load = QPushButton("未整理写真をロード")
        btn_load.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; text-align: center;")
        btn_load.clicked.connect(self.load_images)

        left_layout.addWidget(btn_load)
        left_layout.addWidget(self.img_list)

        right_panel = QFrame()
        right_panel.setFixedWidth(400)
        right_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(15)

        self.preview_lbl = QLabel("写真を選択してください")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setFixedSize(360, 360)
        self.preview_lbl.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333; border-radius: 4px;")
        self.preview_lbl.setScaledContents(True)

        self.info_lbl = QLabel("")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet("color: #aaa;")

        self.ai_status_lbl = QLabel("AI: 未ロード (画面表示時にロード)")
        self.ai_status_lbl.setStyleSheet("font-size: 11px; color: #666;")

        self.folder_area = QScrollArea()
        self.folder_area.setWidgetResizable(True)
        self.folder_container = QWidget()
        self.folder_layout = QVBoxLayout(self.folder_container)
        self.folder_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.folder_area.setWidget(self.folder_container)

        btn_add = QPushButton("＋ フォルダを追加 (AI学習対象)")
        btn_add.clicked.connect(self.add_target_folder)
        btn_add.setStyleSheet("text-align: center; border: 1px dashed #777;")

        right_layout.addWidget(QLabel("プレビュー"))
        right_layout.addWidget(self.preview_lbl)
        right_layout.addWidget(self.info_lbl)
        right_layout.addWidget(self.ai_status_lbl)
        right_layout.addWidget(QLabel("移動先フォルダ"))
        right_layout.addWidget(self.folder_area)
        right_layout.addWidget(btn_add)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)

        main_layout.addWidget(splitter)

    def showEvent(self, event):
        super().showEvent(event)
        print("SorterPage: showEvent triggered", flush=True)
        if AI_AVAILABLE and not self.ai_loading_started:
            self.start_ai_loading()

    def start_ai_loading(self):
        print("SorterPage: calling start_ai_loading...", flush=True)
        self.ai_loading_started = True
        self.ai_status_lbl.setText("AI: モデル読み込み中... (数秒かかります)")
        self.ai_status_lbl.setStyleSheet("font-size: 11px; color: #ffa500;")

        QApplication.processEvents()

        try:
            print("SorterPage: Importing AIWorker NOW...", flush=True)
            from modules.ai_classifier import AIWorker

            print("SorterPage: Creating AIWorker instance...", flush=True)
            self.ai_worker = AIWorker()
            self.ai_worker.model_loaded.connect(self.on_ai_loaded)
            self.ai_worker.suggestion_ready.connect(self.on_ai_suggestion)

            print("SorterPage: Starting AIWorker Thread...", flush=True)
            self.ai_worker.start()

        except ImportError as e:
            print(f"SorterPage: AI Import Error: {e}", flush=True)
            self.ai_status_lbl.setText("AI: ライブラリ未インストール")
        except Exception as e:
            print(f"SorterPage: AIWorker creation failed: {e}", flush=True)
            self.ai_status_lbl.setText("AI: 初期化失敗")

    def on_ai_loaded(self, success):
        self.ai_model_loaded = success
        if success:
            print("SorterPage: AI Loaded Successfully!", flush=True)
            self.ai_status_lbl.setText("AI: 稼働中 (CLIP Model)")
            self.ai_status_lbl.setStyleSheet("font-size: 11px; color: #00ff00;")
            if self.target_folders:
                self.ai_worker.set_target_folders(self.target_folders)
        else:
            self.ai_status_lbl.setText("AI: ロード失敗")
            self.ai_status_lbl.setStyleSheet("font-size: 11px; color: #ff0000;")

    def on_ai_suggestion(self, suggestions):
        self.refresh_folder_buttons(suggestions)

    # ★ここをデバッグ出力付きに変更
    def load_images(self):
        print("SorterPage: load_images START", flush=True)
        try:
            self.img_list.clear()
            print("SorterPage: List cleared", flush=True)

            self.current_items = []
            print("SorterPage: Getting DB rows...", flush=True)

            rows = self.db.get_analyzed_files_unsorted(limit=200)
            print(f"SorterPage: Got {len(rows) if rows else 0} rows", flush=True)

            if not rows:
                self.info_lbl.setText("未整理の写真はありません")
                return

            for i, (fid, path, phash) in enumerate(rows):
                if i % 10 == 0:
                    print(f"SorterPage: Processing {i}/{len(rows)}", flush=True)

                pix = get_db_thumbnail(self.db, fid, path, 160)
                icon = QIcon(pix)
                item = QListWidgetItem(icon, os.path.basename(path))
                item.setData(Qt.ItemDataRole.UserRole, {'id': fid, 'path': path})
                self.img_list.addItem(item)

            print("SorterPage: load_images COMPLETE", flush=True)
        except Exception as e:
            print(f"SorterPage: load_images ERROR: {e}", flush=True)
            traceback.print_exc()

    def on_item_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.selected_item = item
        pix = get_db_thumbnail(self.db, data['id'], data['path'], 360)
        self.preview_lbl.setPixmap(pix)
        self.info_lbl.setText(f"{os.path.basename(data['path'])}")

        if self.ai_worker and self.ai_model_loaded and self.target_folders:
            self.ai_worker.predict(data['path'])

    def add_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder and folder not in self.target_folders:
            self.target_folders.append(folder)
            if self.ai_worker and self.ai_model_loaded:
                self.ai_worker.set_target_folders(self.target_folders)
            self.refresh_folder_buttons()

    def refresh_folder_buttons(self, ai_suggestions=None):
        while self.folder_layout.count():
            child = self.folder_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        display_order = []
        if ai_suggestions:
            suggested_paths = [s[1] for s in ai_suggestions]
            for score, path in ai_suggestions:
                display_order.append({'path': path, 'score': score})
            for path in self.target_folders:
                if path not in suggested_paths:
                    display_order.append({'path': path, 'score': 0})
        else:
            for path in self.target_folders:
                display_order.append({'path': path, 'score': 0})

        for item in display_order:
            path = item['path']
            score = item['score']
            name = os.path.basename(path)

            if score > 0.3:
                text = f"🤖 {name} ({int(score * 100)}%)"
                is_suggest = True
            else:
                text = f"📂 {name}"
                is_suggest = False

            btn = QPushButton(text)
            btn.setToolTip(path)
            btn.clicked.connect(lambda _, f=path: self.move_file(f))

            if is_suggest:
                btn.setProperty("class", "ai-suggest")
                btn.setStyleSheet("""
                    QPushButton { border: 1px solid #d83b01; background-color: #3a1e1e; font-weight: bold; color: white; padding: 10px;}
                    QPushButton:hover { background-color: #d83b01; }
                """)

            self.folder_layout.addWidget(btn)

    def move_file(self, dest_folder):
        if not self.selected_item: return
        data = self.selected_item.data(Qt.ItemDataRole.UserRole)

        if self.db.move_file_to_folder(data['id'], data['path'], dest_folder):
            row = self.img_list.row(self.selected_item)
            self.img_list.takeItem(row)

            if self.img_list.count() > row:
                next_item = self.img_list.item(row)
                self.img_list.setCurrentItem(next_item)
                self.on_item_clicked(next_item)
            elif self.img_list.count() > 0:
                last = self.img_list.item(self.img_list.count() - 1)
                self.img_list.setCurrentItem(last)
                self.on_item_clicked(last)
            else:
                self.preview_lbl.clear()
                self.info_lbl.setText("完了")
                while self.folder_layout.count():
                    c = self.folder_layout.takeAt(0)
                    if c.widget(): c.widget().deleteLater()