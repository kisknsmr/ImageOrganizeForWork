import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QListWidgetItem, QScrollArea,
                             QFrame, QApplication, QGridLayout, QButtonGroup, QSizePolicy, QSplitter,
                             QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, QSize, QTimer, QEvent
from PyQt6.QtGui import QIcon, QPalette, QColor, QWheelEvent


from src.core import setup_logging, get_file_info, format_file_size, format_file_size_kb, FullHashThread
from src.database import DatabaseManager
from gui.thumbnail_preview import (
    get_thumbnail,
    get_preview,
    apply_thumbnail_to_label,
    apply_preview_to_label,
    open_file_in_viewer,
    DEFAULT_PREVIEW_MAX_WIDTH,
    DEFAULT_PREVIEW_MAX_HEIGHT,
)
from src.config import config

logger = logging.getLogger(__name__)


class DuplicatePage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.view_mode = "grid"
        self.current_group_data = []
        self.thumbnail_size = max(config.DEFAULT_GRID_THUMBNAIL_SIZE, 200)  # 最小200px
        self.selected_item_data = None  # 選択中のアイテムデータ
        self.use_full_hash = False       # 完全ハッシュモード
        self._full_hash_thread = None    # 完全ハッシュ計算スレッド
        self.init_ui()

    def init_ui(self):
        # 共通スタイル
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QListWidget { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #3e3e42; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
            QLabel { font-size: 13px; }
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
        left_layout.setSpacing(10)

        wf = QLabel(
            "<b>ステップ①</b>　完全に同じ画像のコピーを減らします。"
            "（先にサイドバー「ステップ0」で取込・解析を済ませてください）次は「② ピンボケチェック」です。"
        )
        wf.setTextFormat(Qt.TextFormat.RichText)
        wf.setWordWrap(True)
        wf.setStyleSheet("color: #9cdcfe; font-size: 11px; border: none; padding-bottom: 6px;")
        left_layout.addWidget(wf)

        left_layout.addWidget(QLabel("重複グループ一覧"))

        self.list = QListWidget()
        self.list.setStyleSheet("border: none; background-color: transparent;")
        self.list.itemClicked.connect(self.on_group_selected)
        self.list.currentItemChanged.connect(self.on_group_selected)  # キーボード選択にも対応
        left_layout.addWidget(self.list)

        # --- 完全ハッシュオプション ---
        hash_option_frame = QFrame()
        hash_option_frame.setStyleSheet(
            "QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }")
        hash_opt_layout = QVBoxLayout(hash_option_frame)
        hash_opt_layout.setContentsMargins(10, 8, 10, 8)
        hash_opt_layout.setSpacing(6)

        hash_label = QLabel("比較モード")
        hash_label.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
        hash_opt_layout.addWidget(hash_label)

        btn_row = QHBoxLayout()
        self.btn_quick_hash = QPushButton("簡易 (高速)")
        self.btn_full_hash = QPushButton("完全 (精密)")
        for btn in [self.btn_quick_hash, self.btn_full_hash]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton { background-color: #252526; border: 1px solid #3e3e42; color: #aaa;
                              border-radius: 4px; font-size: 11px; padding: 0 8px; }
                QPushButton:checked { background-color: #007acc; color: white; border: none; }
                QPushButton:hover:!checked { background-color: #3e3e42; }
            """)
        self.btn_quick_hash.setChecked(True)
        self.hash_mode_group = QButtonGroup(self)
        self.hash_mode_group.addButton(self.btn_quick_hash)
        self.hash_mode_group.addButton(self.btn_full_hash)
        self.hash_mode_group.buttonClicked.connect(self._on_hash_mode_changed)
        btn_row.addWidget(self.btn_quick_hash)
        btn_row.addWidget(self.btn_full_hash)
        hash_opt_layout.addLayout(btn_row)

        self.hash_status_label = QLabel("")
        self.hash_status_label.setStyleSheet("color: #888; font-size: 11px; border: none;")
        self.hash_status_label.setWordWrap(True)
        hash_opt_layout.addWidget(self.hash_status_label)

        self.hash_progress = QProgressBar()
        self.hash_progress.setFixedHeight(6)
        self.hash_progress.setTextVisible(False)
        self.hash_progress.setStyleSheet("""
            QProgressBar { background-color: #3e3e42; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
        """)
        self.hash_progress.hide()
        hash_opt_layout.addWidget(self.hash_progress)

        left_layout.addWidget(hash_option_frame)

        # --- 右メインパネル（スプリッターで分割） ---
        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.setStyleSheet("background-color: #1e1e1e;")
        
        # 左側: グリッドビュー
        grid_panel = QWidget()
        grid_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(grid_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)

        # ヘッダー
        header_layout = QHBoxLayout()
        header_lbl = QLabel("詳細確認")
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
        self.container = QWidget()
        self.container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # キーボード操作に対応
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setStyleSheet("border: none; background-color: transparent;")
        self.area.setWidget(self.container)
        # ホイールイベントをインストール
        self.area.wheelEvent = self.on_wheel_event
        # キーイベントをインストール
        self.container.keyPressEvent = self.on_key_press

        # リサイズ対応: ビューポート幅変更時にグリッド再描画
        self.area.viewport().installEventFilter(self)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(150)
        self._relayout_timer.timeout.connect(self._on_relayout)
        self._prev_cols = 0

        right_layout.addWidget(self.area)

        # 右側: プレビューパネル
        self.preview_panel = preview_panel = QFrame()
        preview_panel.setMinimumWidth(200)
        preview_panel.setMaximumWidth(400)
        preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(15)
        
        preview_title = QLabel("プレビュー")
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        preview_layout.addWidget(preview_title)
        
        self.preview_image = QLabel("画像を選択してください")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumSize(150, 150)
        self.preview_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        preview_layout.addWidget(self.preview_image)
        
        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #aaa; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        
        preview_layout.addStretch()
        
        right_splitter.addWidget(grid_panel)
        right_splitter.addWidget(preview_panel)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 0)
        right_splitter.splitterMoved.connect(lambda: self._relayout_timer.start())

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_splitter, 1)

    # --- Resize handling ---
    def eventFilter(self, obj, event):
        if obj == self.area.viewport() and event.type() == QEvent.Type.Resize:
            self._relayout_timer.start()
        return super().eventFilter(obj, event)

    def _on_relayout(self):
        if self.view_mode != "grid" or not self.current_group_data:
            return
        new_cols = self._calc_cols()
        if new_cols != self._prev_cols:
            self._prev_cols = new_cols
            self.render_items()

    def _calc_cols(self):
        thumb_size = max(self.thumbnail_size, 200)
        frame_width = thumb_size + 40
        viewport_w = self.area.viewport().width() - 20
        if viewport_w < frame_width:
            return 1
        return max(1, viewport_w // (frame_width + 10))

    def load_data(self):
        self.list.clear()
        self.clear_grid()
        try:
            hashes = self.db.get_duplicate_hashes(use_full_hash=self.use_full_hash)
            if not hashes:
                mode_text = "完全ハッシュ" if self.use_full_hash else "簡易ハッシュ"
                self.list.addItem(f"重複なし（{mode_text}）")
                return
            for h, cnt in hashes:
                item = QListWidgetItem(f"重複 {cnt}枚")
                item.setData(Qt.ItemDataRole.UserRole, h)
                self.list.addItem(item)
        except Exception as e:
            logger.error(f"Load error: {e}")

    def on_group_selected(self, item):
        if not item:  # currentItemChangedはNoneを送ることがある
            return
        h = item.data(Qt.ItemDataRole.UserRole)
        if not h: return

        try:
            # データ取得
            files = self.db.get_files_by_hash(h, use_full_hash=self.use_full_hash)
            # 辞書形式に変換して保持
            self.current_group_data = [{'id': f[0], 'path': f[1], 'size': f[2], 'mtime': f[3]} for f in files]
            # ファイルサイズの大きい順にソート
            self.current_group_data.sort(key=lambda x: x['size'], reverse=True)
            self.render_items()
        except Exception as e:
            logger.error(f"Failed to load duplicate group: {e}", exc_info=True)
            QMessageBox.warning(self, "エラー", "データの読み込みに失敗しました")

    # ---------- 完全ハッシュオプション ----------

    def _on_hash_mode_changed(self, btn):
        """比較モード切り替えハンドラ"""
        want_full = (btn == self.btn_full_hash)
        if want_full == self.use_full_hash:
            return  # 変化なし

        if want_full:
            # 完全ハッシュが未計算のファイルがあるか確認
            need = self.db.get_files_needing_full_hash(limit=1)
            if need:
                reply = QMessageBox.question(
                    self, "完全ハッシュ計算",
                    "重複候補ファイルの完全ハッシュを計算します。\n"
                    "ファイル数によっては時間がかかります。\n\n実行しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)
                if reply != QMessageBox.StandardButton.Yes:
                    self.btn_quick_hash.setChecked(True)
                    return
                self._start_full_hash_calculation()
                return  # 完了後に自動で load_data される
            else:
                # 既に計算済み — そのまま切り替え
                self.use_full_hash = True
                self.hash_status_label.setText("完全ハッシュモード")
                self.load_data()
        else:
            self.use_full_hash = False
            self.hash_status_label.setText("")
            self.load_data()

    def _start_full_hash_calculation(self):
        """完全ハッシュ計算スレッドを開始"""
        if self._full_hash_thread and self._full_hash_thread.isRunning():
            return  # 既に実行中

        self.btn_full_hash.setEnabled(False)
        self.btn_quick_hash.setEnabled(False)
        self.hash_progress.setValue(0)
        self.hash_progress.show()

        self._full_hash_thread = FullHashThread(self.db)
        self._full_hash_thread.status.connect(self._on_full_hash_status)
        self._full_hash_thread.progress.connect(self._on_full_hash_progress)
        self._full_hash_thread.finished.connect(self._on_full_hash_finished)
        self._full_hash_thread.start()

    def _on_full_hash_status(self, msg: str):
        self.hash_status_label.setText(msg)

    def _on_full_hash_progress(self, done: int, total: int):
        self.hash_progress.setMaximum(total)
        self.hash_progress.setValue(done)

    def _on_full_hash_finished(self):
        self.hash_progress.hide()
        self.btn_full_hash.setEnabled(True)
        self.btn_quick_hash.setEnabled(True)
        self.use_full_hash = True
        self.btn_full_hash.setChecked(True)
        self.hash_status_label.setText("完全ハッシュモード")
        self.load_data()

    def toggle_view(self, btn):
        self.view_mode = "grid" if btn == self.btn_view_grid else "list"
        if self.current_group_data:
            self.render_items()
    
    def render_items(self):
        self.clear_grid()
        if self.view_mode == "grid":
            self.render_grid_view()
        else:
            self.render_list_view()
        # サイズラベルを更新
        self.size_hint_label.setText(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")

    def render_grid_view(self):
        thumb_size = max(self.thumbnail_size, 200)
        cols = self._calc_cols()
        self._prev_cols = cols
        frame_width = thumb_size + 40
        frame_height = thumb_size + 80  # ファイル名とサイズ表示のため高さを増やす

        for i, data in enumerate(self.current_group_data):
            f = QFrame()
            f.setFixedSize(frame_width, frame_height)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)
            
            # クリックイベントを追加（ラムダのクロージャ問題を回避）
            def make_click_handler(d):
                return lambda event: self.on_item_clicked(d)
            f.mousePressEvent = make_click_handler(data)
            
            # ダブルクリックでビューアで開く
            def make_double_click_handler(d):
                return lambda event: self._open_in_viewer(d)
            f.mouseDoubleClickEvent = make_double_click_handler(data)
            
            # キーボード操作に対応（フォーカス可能にする）
            f.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            # データをフレームに保存（キーイベントで使用）
            f.setProperty("item_data", data)
            f.setProperty("item_index", i)
            
            # キーイベントハンドラーを追加
            def make_key_handler(d, idx):
                def key_handler(event):
                    if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
                        # 削除キーが押された場合
                        self.trash(d['id'], f)
                    elif event.key() == Qt.Key.Key_Down:
                        # 下矢印キー: 次のアイテムにフォーカス
                        self.focus_next_item(idx)
                    elif event.key() == Qt.Key.Key_Up:
                        # 上矢印キー: 前のアイテムにフォーカス
                        self.focus_prev_item(idx)
                    elif event.key() == Qt.Key.Key_Right:
                        # 右矢印キー: 次のアイテムにフォーカス
                        self.focus_next_item(idx)
                    elif event.key() == Qt.Key.Key_Left:
                        # 左矢印キー: 前のアイテムにフォーカス
                        self.focus_prev_item(idx)
                    else:
                        event.ignore()
                return key_handler
            f.keyPressEvent = make_key_handler(data, i)

            l = QVBoxLayout(f)
            l.setContentsMargins(8, 8, 8, 8)
            l.setSpacing(5)

            lbl = QLabel()
            pix = get_thumbnail(self.db, data['id'], data['path'], thumb_size)
            apply_thumbnail_to_label(lbl, pix, thumb_size, style_sheet="border: none; border-radius: 4px; background: #000;")

            # ファイル名とサイズを表示（KB表示、小数点なし）
            file_name = os.path.basename(data['path'])
            file_size = format_file_size_kb(data['size'])
            name_lbl = QLabel(f"{file_name}\n{file_size}")
            name_lbl.setStyleSheet("border: none; font-size: 12px; color: #ccc; font-weight: bold;")
            name_lbl.setWordWrap(True)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setFixedHeight(50)

            btn = QPushButton("削除")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet(self.get_del_btn_style())
            btn.clicked.connect(lambda _, fid=data['id'], w=f: self.trash(fid, w))

            l.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            l.addWidget(name_lbl)
            l.addWidget(btn)

            self.grid.addWidget(f, i // cols, i % cols)
    
    def on_item_clicked(self, data):
        """アイテムがクリックされたときの処理"""
        self.selected_item_data = data
        self.update_preview(data)
    
    def _open_in_viewer(self, data):
        """デフォルトビューアで画像を開く"""
        if not open_file_in_viewer(data['path']):
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{data['path']}")
    
    def update_preview(self, data):
        """プレビューを更新（共通API・縦横比保持）"""
        if not data:
            self.preview_image.clear()
            self.preview_image.setText("画像を選択してください")
            self.preview_info.setText("")
            return

        pix = get_preview(data['path'])
        panel_w = self.preview_panel.width() - 30
        if panel_w < 100:
            panel_w = DEFAULT_PREVIEW_MAX_WIDTH
        apply_preview_to_label(
            self.preview_image, pix,
            max_width=panel_w,
            max_height=DEFAULT_PREVIEW_MAX_HEIGHT,
            style_sheet="background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;",
        )
        if pix.isNull():
            self.preview_image.setText("No Preview")

        # ファイル情報を取得して表示
        file_info = get_file_info(data['path'])
        info_lines = []
        info_lines.append(f"<b>ファイル名:</b> {os.path.basename(data['path'])}")
        info_lines.append(f"<b>パス:</b> {data['path']}")
        
        if file_info['exists']:
            info_lines.append(f"<b>ファイルサイズ:</b> {format_file_size(file_info['file_size'])}")
            if file_info['image_width'] and file_info['image_height']:
                info_lines.append(f"<b>画像サイズ:</b> {file_info['image_width']} × {file_info['image_height']} px")
        else:
            info_lines.append("<b style='color: #d83b01;'>ファイルが見つかりません</b>")
        
        self.preview_info.setText("<br>".join(info_lines))
    
    def on_wheel_event(self, event: QWheelEvent):
        """ホイールイベント処理（Ctrl + ホイールでサムネイルサイズ変更）"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            # Ctrl + ホイールでサムネイルサイズを変更
            delta = event.angleDelta().y()
            if delta > 0:
                # 拡大
                new_size = min(self.thumbnail_size + config.GRID_THUMBNAIL_STEP, 
                              config.MAX_GRID_THUMBNAIL_SIZE)
            else:
                # 縮小
                new_size = max(self.thumbnail_size - config.GRID_THUMBNAIL_STEP, 
                              config.MIN_GRID_THUMBNAIL_SIZE)
            
            if new_size != self.thumbnail_size:
                self.thumbnail_size = new_size
                if self.view_mode == "grid" and self.current_group_data:
                    self.render_items()
        else:
            # 通常のスクロール
            QScrollArea.wheelEvent(self.area, event)

    def render_list_view(self):
        thumb_size = 80
        for i, data in enumerate(self.current_group_data):
            f = QFrame()
            f.setFixedHeight(100)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)

            # クリックとダブルクリックイベント
            def make_click_handler(d):
                return lambda event: self.on_item_clicked(d)
            f.mousePressEvent = make_click_handler(data)
            
            def make_double_click_handler(d):
                return lambda event: self._open_in_viewer(d)
            f.mouseDoubleClickEvent = make_double_click_handler(data)
            f.setCursor(Qt.CursorShape.PointingHandCursor)

            l = QHBoxLayout(f)
            l.setContentsMargins(10, 10, 10, 10)
            l.setSpacing(15)

            lbl = QLabel()
            pix = get_thumbnail(self.db, data['id'], data['path'], thumb_size)
            apply_thumbnail_to_label(lbl, pix, thumb_size, style_sheet="border: none; border-radius: 4px; background: #000;")

            info_layout = QVBoxLayout()
            file_name = os.path.basename(data['path'])
            file_size = format_file_size(data['size'])
            name_lbl = QLabel(f"{file_name}\n{file_size}")
            name_lbl.setStyleSheet("border: none; font-size: 14px; font-weight: bold; color: #fff;")
            path_lbl = QLabel(data['path'])
            path_lbl.setStyleSheet("border: none; font-size: 11px; color: #888;")
            path_lbl.setWordWrap(True)

            info_layout.addWidget(name_lbl)
            info_layout.addWidget(path_lbl)
            info_layout.addStretch()

            btn = QPushButton("ゴミ箱へ")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet(self.get_del_btn_style())
            btn.clicked.connect(lambda _, fid=data['id'], w=f: self.trash(fid, w))

            l.addWidget(lbl)
            l.addLayout(info_layout, stretch=1)
            l.addWidget(btn)

            self.grid.addWidget(f, i, 0)

    def get_del_btn_style(self):
        return """
            QPushButton { background-color: #d83b01; color: white; border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #ff5522; }
            QPushButton:pressed { background-color: #b33000; }
        """

    def trash(self, fid, widget):
        if self.db.move_to_trash(fid):
            # 削除前にインデックスを取得
            deleted_index = next((i for i, d in enumerate(self.current_group_data) if d['id'] == fid), -1)

            # current_group_dataからも削除
            self.current_group_data = [d for d in self.current_group_data if d['id'] != fid]

            current_item = self.list.currentItem()

            if not self.current_group_data:
                self.clear_grid()
                if current_item:
                    current_item.setText("重複 0枚（全て削除済み）")
            else:
                self.render_items()

                # 次のアイテムにフォーカス
                if deleted_index >= 0 and deleted_index < len(self.current_group_data):
                    self.focus_item_by_index(deleted_index)
                elif self.current_group_data:
                    self.focus_item_by_index(len(self.current_group_data) - 1)

                if current_item:
                    current_item.setText(f"重複 {len(self.current_group_data)}枚")
        else:
            QMessageBox.warning(self, "削除失敗", "ファイルの削除に失敗しました。\nログを確認してください。")

    def on_key_press(self, event):
        """コンテナのキーイベントハンドラー"""
        # フォーカスされている子ウィジェットにイベントを転送
        focused = self.container.focusWidget()
        if focused and hasattr(focused, 'keyPressEvent'):
            focused.keyPressEvent(event)
        else:
            event.ignore()
    
    def focus_item_by_index(self, index):
        """指定されたインデックスのアイテムにフォーカスを設定"""
        if index < 0 or index >= len(self.current_group_data):
            return
        
        # グリッドから該当するフレームを取得
        for i in range(self.grid.count()):
            item = self.grid.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                widget_index = widget.property("item_index")
                if widget_index is not None and widget_index == index:
                    widget.setFocus()
                    # スクロールして表示範囲内に
                    self.area.ensureWidgetVisible(widget)
                    break
    
    def focus_next_item(self, current_index):
        """次のアイテムにフォーカスを移動"""
        if current_index < len(self.current_group_data) - 1:
            self.focus_item_by_index(current_index + 1)
        elif len(self.current_group_data) > 0:
            # 最後のアイテムの場合は最初に戻る
            self.focus_item_by_index(0)
    
    def focus_prev_item(self, current_index):
        """前のアイテムにフォーカスを移動"""
        if current_index > 0:
            self.focus_item_by_index(current_index - 1)
        elif len(self.current_group_data) > 0:
            # 最初のアイテムの場合は最後に移動
            self.focus_item_by_index(len(self.current_group_data) - 1)

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
    window.setWindowTitle("重複整理 - デザイン統一版")
    window.resize(1100, 750)
    layout = QVBoxLayout(window)
    layout.addWidget(DuplicatePage(db))
    window.show()
    sys.exit(app.exec())