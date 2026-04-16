import sys
import os
import shutil
import logging
import traceback
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QFrame, QScrollArea, 
                             QProgressBar, QListWidgetItem, QLineEdit, QSplitter,
                             QMessageBox, QInputDialog, QAbstractItemView, QGridLayout,
                             QFileDialog, QApplication, QSizePolicy)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QColor, QWheelEvent


from src.core import get_file_info, format_file_size
from src.database import DatabaseManager
from gui.thumbnail_preview import (
    get_thumbnail,
    get_preview,
    apply_thumbnail_to_label,
    apply_preview_to_label,
    open_file_in_viewer,
    DEFAULT_PREVIEW_MAX_HEIGHT,
    DEFAULT_PREVIEW_MAX_WIDTH,
)
from modules.event_grouper import EventGrouper
from src.config import config


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
    candidates_found = pyqtSignal(int, list) # index, [(label, score), ...]
    finished_all = pyqtSignal()
    
    def __init__(self, ai_worker, events):
        super().__init__()
        self.ai_worker = ai_worker
        self.events = events
        self.running = True
        
    def run(self):
        logger.info("EventLabeler: Started")
        for i, event in enumerate(self.events):
            if not self.running: 
                break
            
            # Skip if already has label or too small
            if event.get('ai_label'): 
                continue
            
            paths = [f['path'] for f in event['files']]
            
            # Use top 5 images for speed, get top 3 candidates
            result = self.ai_worker.predict_event(paths, top_k=5, return_top_n=3)
            
            if result:
                if isinstance(result, list):
                    # 複数候補が返された場合
                    self.candidates_found.emit(i, result)
                    # 最上位候補もlabel_foundとして送信（後方互換性のため）
                    if result:
                        self.label_found.emit(i, result[0][0])
                elif isinstance(result, str):
                    # 単一ラベルが返された場合
                    self.label_found.emit(i, result)
            
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
        self.thumbnail_size = max(config.DEFAULT_GRID_THUMBNAIL_SIZE, 80)
        
        self.init_ui()
        
    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
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

        wf = QLabel(
            "<b>別フェーズ（AI）</b>　メインの整理フロー（①〜⑤）とは切り離した機能です。"
            "手動仕分けがひと区切りついたあとに使う想定です。"
        )
        wf.setTextFormat(Qt.TextFormat.RichText)
        wf.setWordWrap(True)
        wf.setStyleSheet("color: #9cdcfe; font-size: 11px; margin-bottom: 6px;")
        left_layout.addWidget(wf)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("📅 タイムライン (イベント)"))

        # AI起動ボタン
        self.btn_init_ai = QPushButton("🚀 AIエンジン起動")
        self.btn_init_ai.setToolTip("AIモデルを読み込み、イベントの自動分類を開始します（初回は時間がかかります）")
        self.btn_init_ai.setStyleSheet("background-color: #d83b01; color: white; font-weight: bold;")
        self.btn_init_ai.clicked.connect(self.init_ai)
        header_layout.addWidget(self.btn_init_ai)
        
        self.btn_load = QPushButton("🔄 AIクラスタリング実行")
        self.btn_load.setToolTip("AIによる内容ベースのクラスタリングを実行します（日付は無視されます）")
        self.btn_load.clicked.connect(self.load_events)
        self.btn_load.setEnabled(False) # AI未起動時は無効化
        header_layout.addWidget(self.btn_load)
        
        # カテゴリ設定ボタン
        self.btn_categories = QPushButton("⚙️ カテゴリ設定")
        self.btn_categories.setToolTip("AIが使用するカテゴリ（ラベル）をカスタマイズします")
        self.btn_categories.setStyleSheet("background-color: #555; color: white;")
        self.btn_categories.clicked.connect(self.show_category_settings)
        header_layout.addWidget(self.btn_categories)
        
        left_layout.addLayout(header_layout)
        
        self.event_list_widget = QListWidget()
        self.event_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.event_list_widget.currentRowChanged.connect(self.on_event_selected)
        # 信頼度スコアに応じた色分けスタイル
        self.event_list_widget.setStyleSheet("""
            QListWidget::item { padding: 8px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background-color: #007acc; }
            QListWidget::item:hover { background-color: #2d2d30; }
        """)
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

        # サムネイルサイズヒント
        self.size_hint_label = QLabel(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
        self.size_hint_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px 4px;")
        thumb_layout.addWidget(self.size_hint_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.thumbs_container = QWidget()
        self.thumbs_layout = QGridLayout()
        self.thumbs_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.thumbs_layout.setSpacing(8)
        self.thumbs_container.setLayout(self.thumbs_layout)
        self.scroll.setWidget(self.thumbs_container)
        thumb_layout.addWidget(self.scroll)

        # リサイズ対応
        self.scroll.viewport().installEventFilter(self)
        self._thumb_relayout_timer = QTimer(self)
        self._thumb_relayout_timer.setSingleShot(True)
        self._thumb_relayout_timer.setInterval(150)
        self._thumb_relayout_timer.timeout.connect(self._on_thumb_relayout)
        self._thumb_prev_cols = 0
        self._current_thumb_files = []
        # ホイールイベント（Ctrl+ホイールでサムネイルサイズ変更）
        self.scroll.wheelEvent = self._on_wheel_event
        
        right_splitter.addWidget(thumb_widget)
        
        # Bottom: Preview Panel
        self.preview_panel = preview_panel = QFrame()
        preview_panel.setStyleSheet("background-color: #2d2d30; border-top: 1px solid #444;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(8)
        
        self.preview_image = QLabel("画像を選択")
        self.preview_image.setMinimumSize(150, 150)
        self.preview_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42;")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_image)
        
        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #ccc; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        preview_layout.addStretch()
        
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
            logger.warning("SorterUI: AI not available")
            return
        if self.ai_worker:
            logger.info("SorterUI: AI worker already exists")
            return
            
        logger.info("SorterUI: Initializing AI...")
        from modules.ai_classifier import AIWorker
        self.ai_worker = AIWorker()
        self.ai_worker.model_loaded.connect(self.on_ai_loaded)
        self.ai_worker.start()
        
    def on_ai_loaded(self, success):
        self.ai_ready = success
        if success:
            logger.info("SorterUI: AI Ready. Scanning events...")
            self.btn_init_ai.setEnabled(False)
            self.btn_init_ai.setText("AI準備完了")
            self.btn_init_ai.setStyleSheet("background-color: #333; color: #888;")
            self.btn_load.setEnabled(True)
            self.load_events()
        else:
            logger.error("SorterUI: AI load failed")
            self.btn_init_ai.setEnabled(True)
            self.btn_init_ai.setText("❌ 起動失敗 (再試行)")
            QMessageBox.warning(self, "エラー", "AIエンジンの起動に失敗しました。")

    def load_events(self):
        self.event_list_widget.clear()
        self.right_layout.setEnabled(False)
        self.clear_thumbnails()
        
        logger.info("SorterUI: Fetching files from DB...")
        try:
            files_raw = self.db.get_all_files_with_info()
        except AttributeError:
            logger.critical("SorterUI: Critical Error - DatabaseManager missing 'get_all_files_with_info'. Please restart.")
            QMessageBox.critical(self, "エラー", "データベースエラーが発生しました。アプリケーションを再起動してください。")
            files_raw = []
        except Exception as e:
            logger.error(f"SorterUI: Fatal Error fetching files: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"ファイルの取得に失敗しました:\n{e}")
            files_raw = []

        if not files_raw:
            logger.warning("SorterUI: No files found or error occurred.")
            QMessageBox.information(self, "情報", "処理対象のファイルが見つかりませんでした。")
            self.right_layout.setEnabled(True)
            return

        logger.info(f"SorterUI: Grouping {len(files_raw)} files using AI content-based clustering...")
        
        if not self.ai_ready or not self.ai_worker:
            logger.warning("SorterUI: AI not ready, cannot perform content-based clustering")
            QMessageBox.warning(self, "エラー", "AIエンジンが準備できていません。\n先に「AIエンジン起動」ボタンを押してください。")
            self.right_layout.setEnabled(True)
            return
        
        try:
            grouper = EventGrouper(self.db)
            self.events = grouper.group_by_content(files_raw, self.ai_worker, eps=0.15, min_samples=2)
            
            if not self.events:
                logger.warning("SorterUI: No events created from content-based clustering")
                QMessageBox.information(self, "情報", "クラスタリングの結果、グループが見つかりませんでした。\n画像が少ないか、類似度が低い可能性があります。")
                self.right_layout.setEnabled(True)
                return
                
        except Exception as e:
            logger.error(f"SorterUI: Error grouping events: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"AIクラスタリングに失敗しました:\n{e}")
            self.events = []
            self.right_layout.setEnabled(True)
            return
        
        logger.info(f"SorterUI: Found {len(self.events)} events.")
        
        for i, ev in enumerate(self.events):
            item_text = self._format_event_text(ev)
            item = QListWidgetItem(item_text)
            # 信頼度スコアに応じた背景色を設定
            score = ev.get('ai_score')
            if score is not None:
                if score >= 0.5:
                    item.setBackground(QColor(0, 100, 0))  # 暗い緑
                elif score >= 0.3:
                    item.setBackground(QColor(100, 100, 0))  # 暗い黄
                else:
                    item.setBackground(QColor(100, 0, 0))  # 暗い赤
            self.event_list_widget.addItem(item)
            
        self.right_layout.setEnabled(True)
        
        # Start AI labeling in background
        if self.ai_ready and self.events:
            if self.labeler_thread and self.labeler_thread.isRunning():
                self.labeler_thread.stop()
                self.labeler_thread.wait()
                
            self.labeler_thread = EventLabelerThread(self.ai_worker, self.events)
            self.labeler_thread.label_found.connect(self.on_ai_label_found)
            self.labeler_thread.candidates_found.connect(self.on_ai_candidates_found)
            self.labeler_thread.start()
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0) # Infinite loop
            

    def _format_event_text(self, ev):
        count = ev['count']
        # AIラベルがある場合はそれを優先表示、ない場合はグループ番号
        if ev.get('ai_label'):
            score = ev.get('ai_score')
            if score is not None:
                # スコアに応じて色分け（後でスタイルシートで適用）
                if score >= 0.5:
                    score_icon = "🟢"
                elif score >= 0.3:
                    score_icon = "🟡"
                else:
                    score_icon = "🔴"
                ai_tag = f"🏷️ {ev['ai_label']} {score_icon}({score:.2f})"
            else:
                ai_tag = f"🏷️ {ev['ai_label']}"
            return f"{ai_tag} ({count}枚)"
        else:
            # AIラベルがない場合はグループ番号を表示
            group_name = ev.get('suggested_name', 'グループ')
            return f"{group_name} ({count}枚)"

    def on_ai_label_found(self, idx, label):
        if idx < len(self.events):
            self.events[idx]['ai_label'] = label
            self.events[idx]['ai_score'] = None  # スコアは候補から取得
            # Update List Item
            item = self.event_list_widget.item(idx)
            item.setText(self._format_event_text(self.events[idx]))
            
            # If currently selected, update the text box suggestion
            if idx == self.current_event_idx:
                # AIラベルを直接フォルダ名として使用
                self.txt_folder_name.setText(label)
    
    def on_ai_candidates_found(self, idx, candidates):
        """複数候補が返された場合の処理"""
        if idx < len(self.events) and candidates:
            # 最上位候補を保存
            best_label, best_score = candidates[0]
            self.events[idx]['ai_label'] = best_label
            self.events[idx]['ai_score'] = best_score
            self.events[idx]['ai_candidates'] = candidates
            
            # Update List Item
            item = self.event_list_widget.item(idx)
            item.setText(self._format_event_text(self.events[idx]))
            # 信頼度スコアに応じた背景色を設定
            if best_score >= 0.5:
                item.setBackground(QColor(0, 100, 0))  # 暗い緑
            elif best_score >= 0.3:
                item.setBackground(QColor(100, 100, 0))  # 暗い黄
            else:
                item.setBackground(QColor(100, 0, 0))  # 暗い赤
            
            # 現在選択中のイベントの場合、候補選択UIを表示
            if idx == self.current_event_idx:
                self.show_candidate_selector(idx, candidates)

    def on_event_selected(self, row):
        if row < 0 or row >= len(self.events): return
        
        self.current_event_idx = row
        ev = self.events[row]
        
        # タイトル: AIラベルがある場合はそれを表示、ない場合はグループ番号
        if ev.get('ai_label'):
            title = f"グループ #{row+1}: {ev['ai_label']}"
        else:
            title = f"グループ #{row+1}"
        self.lbl_event_title.setText(title)
        
        # 日付情報は表示しない（内容ベースのクラスタリングのため）
        self.lbl_event_date.setText("内容ベースのグループ")
        
        # フォルダ名の提案: AIラベルがある場合はそれを優先
        if ev.get('ai_label'):
            base_name = ev['ai_label']
        else:
            base_name = f"グループ_{row+1}"
        self.txt_folder_name.setText(base_name)
        
        # Load thumbnails (Async would be better but let's do sync for first 20)
        self.show_event_thumbnails(ev['files'])

    def _calc_thumb_cols(self):
        """サムネイルグリッドの列数をビューポート幅から計算"""
        thumb = max(self.thumbnail_size, 80)
        card_size = thumb + 10  # margin
        vw = self.scroll.viewport().width() - 10
        if vw < card_size:
            return 1
        return max(1, vw // card_size)

    def eventFilter(self, obj, event):
        if obj == self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._thumb_relayout_timer.start()
        return super().eventFilter(obj, event)

    def _on_wheel_event(self, event: QWheelEvent):
        """Ctrl + ホイールでサムネイルサイズ変更"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                new_size = min(self.thumbnail_size + config.GRID_THUMBNAIL_STEP,
                              config.MAX_GRID_THUMBNAIL_SIZE)
            else:
                new_size = max(self.thumbnail_size - config.GRID_THUMBNAIL_STEP,
                              config.MIN_GRID_THUMBNAIL_SIZE)
            if new_size != self.thumbnail_size:
                self.thumbnail_size = new_size
                self.size_hint_label.setText(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
                if self._current_thumb_files:
                    self._relayout_thumbnails()
        else:
            QScrollArea.wheelEvent(self.scroll, event)

    def _on_thumb_relayout(self):
        if not self._current_thumb_files:
            return
        new_cols = self._calc_thumb_cols()
        if new_cols != self._thumb_prev_cols:
            self._thumb_prev_cols = new_cols
            self._relayout_thumbnails()

    def _create_thumb_label(self, f):
        """サムネイル用ラベルを生成（共通ヘルパー）"""
        thumb = max(self.thumbnail_size, 80)
        lbl = QLabel()
        lbl.setFixedSize(thumb, thumb)
        lbl.setStyleSheet("border: 1px solid #444; border-radius: 4px;")

        def make_callback(d):
            return lambda event: self.update_preview(d)
        lbl.mousePressEvent = make_callback(f)

        def make_dbl(d):
            return lambda event: open_file_in_viewer(d.get('path', ''))
        lbl.mouseDoubleClickEvent = make_dbl(f)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)

        pix = get_thumbnail(self.db, f.get('id'), f.get('path'), thumb)
        if pix:
            lbl.setPixmap(pix.scaled(thumb, thumb, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    def _relayout_thumbnails(self):
        """現在のファイルリストでサムネイルを再描画"""
        self.clear_thumbnails()
        cols = self._calc_thumb_cols()
        self._thumb_prev_cols = cols
        for i, f in enumerate(self._current_thumb_files):
            lbl = self._create_thumb_label(f)
            self.thumbs_layout.addWidget(lbl, i // cols, i % cols)

    def show_event_thumbnails(self, files):
        self.clear_thumbnails()
        max_show = 30
        self._current_thumb_files = files[:max_show]
        cols = self._calc_thumb_cols()
        self._thumb_prev_cols = cols
        for i, f in enumerate(self._current_thumb_files):
            lbl = self._create_thumb_label(f)
            self.thumbs_layout.addWidget(lbl, i // cols, i % cols)

    def clear_thumbnails(self):
        while self.thumbs_layout.count():
            child = self.thumbs_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        
        # Clear preview too
        self.preview_image.clear()
        self.preview_image.setText("画像を選択")
        self.preview_info.setText("")

    def update_preview(self, file_data):
        if not file_data:
            return
        path = file_data.get('path')
        pix = get_preview(path)
        panel_w = self.preview_panel.width() - 30
        if panel_w < 100:
            panel_w = DEFAULT_PREVIEW_MAX_WIDTH
        apply_preview_to_label(
            self.preview_image, pix,
            max_width=panel_w,
            max_height=DEFAULT_PREVIEW_MAX_HEIGHT,
            style_sheet="background-color: #1e1e1e; border: 1px solid #3e3e42;",
        )
        if pix.isNull():
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
        if self.current_event_idx < 0: 
            QMessageBox.warning(self, "エラー", "イベントが選択されていません")
            return
        
        if self.current_event_idx >= len(self.events):
            logger.error(f"SorterUI: Invalid event index {self.current_event_idx}")
            QMessageBox.critical(self, "エラー", "無効なイベントインデックスです")
            return
        
        ev = self.events[self.current_event_idx]
        
        # 1. Get destination name (AI推論結果を優先的に使用)
        folder_name = self.txt_folder_name.text().strip()
        if not folder_name:
            # AI推論結果がある場合はそれを使用
            if ev.get('ai_label'):
                folder_name = ev['ai_label']
                self.txt_folder_name.setText(folder_name)
            else:
                # AIラベルがない場合はグループ番号を使用
                folder_name = f"グループ_{self.current_event_idx+1}"
                self.txt_folder_name.setText(folder_name)
        
        # 2. Ask for parent directory (or use a default Library root)
        base_path = self.db.get_setting("root_path")  # ライブラリのルートパスを使用
        if not base_path or not os.path.exists(base_path):
            base_path = QFileDialog.getExistingDirectory(self, "保存先の親フォルダを選択してください")
            if not base_path: 
                return
            # 設定に保存
            self.db.set_setting("root_path", base_path)
        
        dest_dir = os.path.join(base_path, folder_name)
        
        # 3. Move files
        files = ev.get('files', [])
        if not files:
            QMessageBox.warning(self, "エラー", "移動するファイルがありません")
            return
        
        try:
            os.makedirs(dest_dir, exist_ok=True)
            
            success_count = 0
            failed_count = 0
            failed_files = []
            
            for f in files:
                try:
                    # Use safe move method from core
                    success = self.db.move_file_to_folder(f['id'], f['path'], dest_dir)
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_files.append(os.path.basename(f['path']))
                        logger.error(f"Failed to move {f['path']}")
                except Exception as e:
                    failed_count += 1
                    failed_files.append(os.path.basename(f.get('path', 'unknown')))
                    logger.error(f"Exception moving file {f.get('path', 'unknown')}: {e}", exc_info=True)

            if failed_count > 0:
                msg = f"{success_count} 枚を移動しました\n{failed_count} 枚の移動に失敗しました"
                if len(failed_files) <= 5:
                    msg += f"\n\n失敗したファイル:\n" + "\n".join(failed_files)
                QMessageBox.warning(self, "部分完了", msg)
            else:
                QMessageBox.information(self, "完了", f"{success_count} 枚を移動しました\n\nフォルダ: {dest_dir}")
            
            # カスタムカテゴリを記録（フォルダ名からAI推論結果以外の部分を抽出）
            # フォルダ名が "日付_カテゴリ" 形式の場合、カテゴリ部分を記録
            if folder_name and '_' in folder_name:
                parts = folder_name.split('_')
                if len(parts) >= 2:
                    # 最後の部分がカテゴリ名の可能性が高い
                    potential_category = parts[-1]
                    # AI推論結果と異なる場合はカスタムカテゴリとして記録
                    if ev.get('ai_label') and potential_category != ev['ai_label']:
                        try:
                            self.db.record_custom_category(potential_category)
                        except Exception as e:
                            logger.warning(f"Failed to record custom category: {e}")
                    elif not ev.get('ai_label'):
                        # AI推論結果がない場合も記録
                        try:
                            self.db.record_custom_category(potential_category)
                        except Exception as e:
                            logger.warning(f"Failed to record custom category: {e}")
            
            # Remove from list
            if self.current_event_idx < self.event_list_widget.count():
                self.event_list_widget.takeItem(self.current_event_idx)
            if self.current_event_idx < len(self.events):
                del self.events[self.current_event_idx]
            self.current_event_idx = -1
            self.clear_thumbnails()
            
        except OSError as e:
            logger.error(f"OSError during file move: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"ファイルシステムエラーが発生しました:\n{e}")
        except Exception as e:
            logger.error(f"Unexpected error during file move: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"移動に失敗しました:\n{e}")

    def show_category_settings(self):
        """カテゴリ設定ダイアログを表示"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel, QMessageBox
        from src.config import config
        
        dialog = QDialog(self)
        dialog.setWindowTitle("AIカテゴリ設定")
        dialog.setMinimumSize(500, 400)
        dialog.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #e0e0e0; }
            QTextEdit { background-color: #252526; border: 1px solid #3e3e42; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
        """)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel("AIが使用するカテゴリ（ラベル）を1行に1つずつ入力してください。\n変更後、AIエンジンを再起動してください。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        text_edit = QTextEdit()
        # プリセットカテゴリ + カスタムカテゴリを表示
        all_categories = list(config.AI_EVENT_LABELS)
        custom_categories = self.db.get_all_custom_categories()
        # カスタムカテゴリでプリセットにないものだけ追加
        for cat in custom_categories:
            if cat not in all_categories:
                all_categories.append(cat)
        text_edit.setPlainText("\n".join(all_categories))
        layout.addWidget(text_edit)
        
        # 人気のカスタムカテゴリを表示
        popular = self.db.get_popular_custom_categories(5)
        if popular:
            popular_label = QLabel("よく使われるカスタムカテゴリ:\n" + "\n".join([f"  • {name} ({count}回)" for name, count in popular]))
            popular_label.setWordWrap(True)
            popular_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")
            layout.addWidget(popular_label)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_save.setStyleSheet("background-color: #007acc; color: white; padding: 8px;")
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet("background-color: #555; color: white; padding: 8px;")
        
        def save_categories():
            new_labels = [line.strip() for line in text_edit.toPlainText().split("\n") if line.strip()]
            if not new_labels:
                QMessageBox.warning(dialog, "エラー", "少なくとも1つのカテゴリを入力してください")
                return
            
            config.AI_EVENT_LABELS = new_labels
            # 新しく追加されたカテゴリをカスタムカテゴリとして記録
            existing_custom = set(self.db.get_all_custom_categories())
            preset_categories = set(config.AI_EVENT_LABELS)
            for new_label in new_labels:
                if new_label not in preset_categories and new_label not in existing_custom:
                    self.db.add_custom_category(new_label)
            QMessageBox.information(dialog, "保存完了", f"{len(new_labels)} 個のカテゴリを保存しました。\nAIエンジンを再起動すると反映されます。")
            dialog.accept()
        
        btn_save.clicked.connect(save_categories)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def show_candidate_selector(self, idx, candidates):
        """候補選択ダイアログを表示"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel
        
        
        if idx < 0 or idx >= len(self.events):
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("AI候補選択")
        dialog.setMinimumSize(400, 300)
        dialog.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #e0e0e0; }
            QLabel { color: #e0e0e0; padding: 5px; }
            QPushButton { background-color: #2d2d30; border: 1px solid #3e3e42; padding: 8px; border-radius: 4px; color: #e0e0e0; }
            QPushButton:hover { background-color: #3e3e42; border-color: #007acc; }
        """)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel("AIが推論した候補から選択してください：")
        layout.addWidget(info_label)
        
        selected_label = [None]  # リストでラップしてクロージャで変更可能に
        
        for i, (label, score) in enumerate(candidates):
            btn = QPushButton(f"{label} (信頼度: {score:.2f})")
            if i == 0:
                btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
            
            def make_callback(l):
                def callback():
                    selected_label[0] = l
                    dialog.accept()
                return callback
            
            btn.clicked.connect(make_callback(label))
            layout.addWidget(btn)
        
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancel)
        
        
        if dialog.exec() == QDialog.DialogCode.Accepted and selected_label[0]:
            # 選択されたラベルを適用
            self.events[idx]['ai_label'] = selected_label[0]
            # スコアを更新（選択された候補のスコアを取得）
            for label, score in candidates:
                if label == selected_label[0]:
                    self.events[idx]['ai_score'] = score
                    break
            
            # UIを更新
            item = self.event_list_widget.item(idx)
            item.setText(self._format_event_text(self.events[idx]))
            # 背景色も更新
            score = self.events[idx]['ai_score']
            if score >= 0.5:
                item.setBackground(QColor(0, 100, 0))
            elif score >= 0.3:
                item.setBackground(QColor(100, 100, 0))
            else:
                item.setBackground(QColor(100, 0, 0))
            
            # フォルダ名を更新
            if idx == self.current_event_idx:
                self.txt_folder_name.setText(selected_label[0])

    def skip_event(self):
        # Just remove from list without doing anything
        if self.current_event_idx < 0: return
        self.event_list_widget.takeItem(self.current_event_idx)
        del self.events[self.current_event_idx]
        self.current_event_idx = -1
        self.clear_thumbnails()
