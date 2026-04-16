import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QSlider, QListWidgetItem,
                             QApplication, QFrame, QScrollArea, QGridLayout,
                             QSizePolicy, QProgressBar, QButtonGroup, QSplitter,
                             QMessageBox)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QPalette, QColor, QWheelEvent


from src.core import setup_logging, get_file_info, format_file_size
from src.database import DatabaseManager
from src.config import config
from gui.thumbnail_preview import (
    get_thumbnail,
    get_preview,
    apply_thumbnail_to_label,
    apply_preview_to_label,
    open_file_in_viewer,
    DEFAULT_PREVIEW_MAX_WIDTH,
    DEFAULT_PREVIEW_MAX_HEIGHT,
)

logger = logging.getLogger(__name__)



# --- Worker ---
class BlurLoadWorker(QThread):
    """DB からピンボケ候補を取得するワーカー（データ取得のみ）"""
    status = pyqtSignal(str)
    all_loaded = pyqtSignal(list)   # 全件を一括で返す

    def __init__(self, db, threshold):
        super().__init__()
        self.db = db
        self.threshold = threshold

    def run(self):
        try:
            self.status.emit("データベースを検索中…")
            rows = self.db.get_blurry_files(self.threshold)
            items = [{'id': fid, 'path': path} for fid, path in rows]
            self.all_loaded.emit(items)
        except Exception as e:
            logger.error(f"Error in BlurLoadWorker.run: {e}", exc_info=True)
            self.all_loaded.emit([])


# --- UI ---
class BlurPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.worker = None
        self.view_mode = "grid"
        self.loaded_items = []  # データを保持
        self.last_cols = 0  # 最後に計算した列数
        self.resize_timer = None  # リサイズデバウンス用タイマー
        self.thumbnail_size = max(config.DEFAULT_GRID_THUMBNAIL_SIZE, 100)
        self.init_ui()
    
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj == self.area.viewport() and event.type() == QEvent.Type.Resize:
            if self.loaded_items and self.view_mode == "grid":
                if self.resize_timer:
                    self.resize_timer.stop()
                self.resize_timer = QTimer()
                self.resize_timer.setSingleShot(True)
                self.resize_timer.timeout.connect(self._on_resize_timeout)
                self.resize_timer.start(150)
        return super().eventFilter(obj, event)

    def _on_resize_timeout(self):
        """リサイズデバウンスタイマーのコールバック"""
        if not self.loaded_items or self.view_mode != "grid":
            return
        current_cols = self._calc_cols()
        if current_cols != self.last_cols:
            self.last_cols = current_cols
            self.render_all_items()

    def _schedule_resize(self):
        """スプリッター移動時のリサイズスケジュール"""
        if not self.loaded_items or self.view_mode != "grid":
            return
        if self.resize_timer:
            self.resize_timer.stop()
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._on_resize_timeout)
        self.resize_timer.start(150)

    def _calc_cols(self):
        """ビューポート幅から列数を計算"""
        card_width = max(self.thumbnail_size, 100) + 40
        spacing = 10
        vw = self.area.viewport().width() - 20
        if vw < card_width:
            return 1
        return max(1, vw // (card_width + spacing))

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
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
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(400)
        left_panel.setStyleSheet("border-right: 1px solid #3e3e42; background-color: #252526;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)

        wf = QLabel(
            "<b>ステップ②</b>　ブレやピント外しなど「失敗駒」を減らします。「① 重複チェック」の次です。"
        )
        wf.setTextFormat(Qt.TextFormat.RichText)
        wf.setWordWrap(True)
        wf.setStyleSheet("color: #9cdcfe; font-size: 11px; border: none;")
        left_layout.addWidget(wf)

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
        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.setStyleSheet("background-color: #1e1e1e;")

        # Grid Panel
        grid_panel = QWidget()
        right_layout = QVBoxLayout(grid_panel)
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

        self.size_hint_label = QLabel(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
        self.size_hint_label.setStyleSheet("color: #888; font-size: 11px;")

        header_layout.addWidget(header_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.size_hint_label)
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

        # リサイズイベントを監視してグリッドを再描画（ビューポート監視）
        self.area.viewport().installEventFilter(self)
        # ホイールイベント（Ctrl+ホイールでサムネイルサイズ変更）
        self.area.wheelEvent = self._on_wheel_event

        right_layout.addWidget(self.area)

        right_splitter.addWidget(grid_panel)

        # Preview Panel
        self.preview_panel = preview_panel = QFrame()
        preview_panel.setMinimumWidth(200)
        preview_panel.setMaximumWidth(400)
        preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(15)
        
        lbl_p_title = QLabel("プレビュー")
        lbl_p_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        preview_layout.addWidget(lbl_p_title)
        
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
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)
        right_splitter.splitterMoved.connect(self._schedule_resize)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_splitter, 1)

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
        try:
            self.clear_grid()
            self.loaded_items = []
            self._render_queue = []
            self._render_index = 0
            self.btn_refresh.setEnabled(False)
            self.progress.setValue(0)
            self.progress.setMaximum(0)  # indeterminate（ぐるぐる）
            self.lbl_status.setText("データベースを検索中…")

            threshold = self.slider.value()
            self.worker = BlurLoadWorker(self.db, threshold)
            self.worker.status.connect(lambda msg: self.lbl_status.setText(msg))
            self.worker.all_loaded.connect(self._on_all_loaded)
            self.worker.start()
        except Exception as e:
            logger.error(f"Error in load_data: {e}", exc_info=True)
            self.btn_refresh.setEnabled(True)
            self.progress.setMaximum(100)
            self.lbl_status.setText(f"エラー: {e}")

    # ---- Phase 2: バッチ描画 ----

    RENDER_BATCH_SIZE = 20  # 1回のタイマーで描画するアイテム数

    def _on_all_loaded(self, items: list):
        """ワーカーから全件受け取り → バッチ描画を開始"""
        total = len(items)
        if total == 0:
            self.btn_refresh.setEnabled(True)
            self.progress.setMaximum(100)
            self.progress.setValue(100)
            self.lbl_status.setText("該当なし（閾値を変更してみてください）")
            return

        self.loaded_items = items
        self._render_queue = list(items)
        self._render_index = 0

        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.lbl_status.setText(f"描画中: 0 / {total} 枚")

        # QTimer でバッチ描画（UI をブロックしない）
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(0)  # イベントループに空きができたら即実行
        self._render_timer.timeout.connect(self._render_next_batch)
        self._render_timer.start()

    def _render_next_batch(self):
        """バッチ単位で描画を進め、進捗を更新する"""
        total = len(self._render_queue)
        end = min(self._render_index + self.RENDER_BATCH_SIZE, total)

        for i in range(self._render_index, end):
            self.add_single_item(self._render_queue[i], i)

        self._render_index = end
        self.progress.setValue(end)
        self.lbl_status.setText(f"描画中: {end} / {total} 枚")

        if self._render_index >= total:
            self._render_timer.stop()
            self.btn_refresh.setEnabled(True)
            self.progress.setValue(total)
            self.lbl_status.setText(f"完了: {total} 枚")

    def render_all_items(self):
        self.clear_grid()
        # last_colsをリセットして、列数を再計算
        self.last_cols = 0
        for i, item in enumerate(self.loaded_items):
            try:
                self.add_single_item(item, i)
            except Exception as e:
                import traceback
                logger.error(f"Error adding item {i}: {e}\n{traceback.format_exc()}")
        # サイズラベルを更新
        self.size_hint_label.setText(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")
        # レイアウトを更新
        QApplication.processEvents()

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
                if self.view_mode == "grid" and self.loaded_items:
                    self.render_all_items()
        else:
            QScrollArea.wheelEvent(self.area, event)

    def add_single_item(self, item, index):
        if self.view_mode == "grid":
            self.render_grid_item(item, index)
        else:
            self.render_list_item(item, index)

    def render_grid_item(self, item, index):
        if index == 0 or self.last_cols == 0:
            self.last_cols = self._calc_cols()
        cols = self.last_cols
        row, col = divmod(index, cols)
        thumb_size = max(self.thumbnail_size, 100)

        f = QFrame()
        frame_width = thumb_size + 40
        frame_height = thumb_size + 80
        f.setFixedSize(frame_width, frame_height)
        f.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
            QFrame:hover { border-color: #d83b01; background-color: #3e3e42; }
        """)
        
        def make_cb(d):
            return lambda ev: self.update_preview(d)
        f.mousePressEvent = make_cb(item)

        def make_dbl(d):
            return lambda ev: self._open_in_viewer(d)
        f.mouseDoubleClickEvent = make_dbl(item)
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        
        l = QVBoxLayout(f)
        l.setContentsMargins(5, 5, 5, 5)
        l.setSpacing(2)

        lbl = QLabel()
        pix = get_thumbnail(self.db, item['id'], item['path'], thumb_size)
        apply_thumbnail_to_label(lbl, pix, thumb_size, style_sheet="border: none; border-radius: 4px; background: #000;")

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
        f.setCursor(Qt.CursorShape.PointingHandCursor)

        def make_dbl(d):
            return lambda ev: self._open_in_viewer(d)
        f.mouseDoubleClickEvent = make_dbl(item)

        l = QHBoxLayout(f)
        l.setContentsMargins(10, 10, 10, 10)
        l.setSpacing(15)

        lbl = QLabel()
        pix = get_thumbnail(self.db, item['id'], item['path'], thumb_size)
        apply_thumbnail_to_label(lbl, pix, thumb_size, style_sheet="border: none; border-radius: 4px; background: #000;")

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

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _open_in_viewer(self, item):
        """デフォルトビューアで画像を開く"""
        if not open_file_in_viewer(item['path']):
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{item['path']}")

    def trash(self, fid, widget):
        result = self.db.move_to_trash(fid)
        if result:
            # loaded_itemsから削除
            self.loaded_items = [item for item in self.loaded_items if item.get('id') != fid]
            # ウィジェットを削除（グリッドから削除して非表示にする）
            self.grid.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
            # グリッドを再描画して、残りのアイテムを正しく配置する
            if self.view_mode == "grid":
                self.render_all_items()
        else:
            QMessageBox.warning(self, "削除失敗", "ファイルの削除に失敗しました。\nログを確認してください。")

            
    def update_preview(self, item):
        if not item:
            return
        path = item['path']
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
        txt = []
        txt.append(f"<b>ファイル名:</b> {os.path.basename(path)}")
        txt.append(f"<b>パス:</b> {path}")
        if info['exists']:
            txt.append(f"<b>サイズ:</b> {format_file_size(info['file_size'])}")
            if info['image_width']:
                txt.append(f"<b>画像:</b> {info['image_width']} x {info['image_height']} px")
        else:
            txt.append("<b style='color:red;'>ファイルが見つかりません</b>")
            
        self.preview_info.setText("<br>".join(txt))


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