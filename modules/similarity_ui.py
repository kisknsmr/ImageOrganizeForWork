import sys
import os
import logging
import random
import statistics
from collections import deque
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QSlider, QListWidgetItem,
                             QScrollArea, QFrame, QGridLayout, QApplication,
                             QProgressBar, QSizePolicy, QButtonGroup, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent
from PyQt6.QtGui import QIcon, QPalette, QColor, QWheelEvent


from src.core import setup_logging, get_file_info, format_file_size, format_file_size_kb
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


# =========================================================
#  Logic Utilities & Worker
# =========================================================
def hamming_dist(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


class VPNode:
    __slots__ = ['vp', 'items', 'threshold', 'left', 'right']

    def __init__(self, vp, items):
        self.vp = vp
        self.items = items
        self.threshold = 0.0
        self.left = None
        self.right = None


class VPTree:
    def __init__(self, items):
        self.root = self._build_recursive(items)

    def _build_recursive(self, items):
        if not items: return None
        vp_item = items[random.randint(0, len(items) - 1)]
        vp_hash = vp_item['hash']
        same_vp = [item for item in items if item['hash'] == vp_hash]
        others = [item for item in items if item['hash'] != vp_hash]
        node = VPNode(vp_hash, same_vp)
        if not others: return node
        distances = [(item, hamming_dist(vp_hash, item['hash'])) for item in others]
        dists = [d for _, d in distances]
        median = statistics.median(dists)
        node.threshold = median
        left_items = [item for item, d in distances if d <= median]
        right_items = [item for item, d in distances if d > median]
        node.left = self._build_recursive(left_items)
        node.right = self._build_recursive(right_items)
        return node

    def search(self, query_hash, max_dist):
        results = []
        if not self.root: return results
        stack = deque([self.root])
        while stack:
            node = stack.pop()
            dist = hamming_dist(query_hash, node.vp)
            if dist <= max_dist: results.extend(node.items)
            if node.left and dist - max_dist <= node.threshold: stack.append(node.left)
            if node.right and dist + max_dist > node.threshold: stack.append(node.right)
        return results


class GroupingWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    result_ready = pyqtSignal(list)

    def __init__(self, db, threshold):
        super().__init__()
        self.db = db
        self.threshold = threshold

    def run(self):
        self.status.emit("データをロード中...")
        rows = self.db.get_files_with_phash()
        if not rows:
            self.result_ready.emit([])
            return

        self.status.emit("インデックス構築中...")
        items = []
        for i, row in enumerate(rows):
            # rowの形式を確認: (fid, path, phash, mtime) または (fid, path, phash, mtime, size)
            if len(row) >= 4:
                fid, path, phash, mtime = row[0], row[1], row[2], row[3]
                size = row[4] if len(row) > 4 else 0
            else:
                continue
            if not phash: continue
            try:
                items.append({'id': fid, 'path': path, 'hash': int(phash, 16), 'size': size})
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse phash for file_id {fid}: {e}")
                continue
            if i % 2000 == 0: self.progress.emit(10, 100)

        tree = VPTree(items)
        self.progress.emit(40, 100)

        self.status.emit("類似画像を検索中...")
        groups = []
        visited = set()
        total = len(items)
        for i, item in enumerate(items):
            if item['id'] in visited: continue
            neighbors = tree.search(item['hash'], self.threshold)
            if len(neighbors) > 1:
                valid = [n for n in neighbors if n['id'] not in visited]
                current = []
                for m in valid:
                    current.append(m)
                    visited.add(m['id'])
                if len(current) > 1: groups.append(current)
            if i % 100 == 0: self.progress.emit(40 + int((i / total) * 60), 100)

        self.status.emit("完了")
        self.progress.emit(100, 100)
        self.result_ready.emit(groups)


# =========================================================
#  UI Class (Commercial Grade)
# =========================================================
class SimilarityPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.worker = None
        self.view_mode = "grid"  # grid or list
        self.current_group_data = []  # 現在表示中のデータを保持
        self.thumbnail_size = max(config.DEFAULT_GRID_THUMBNAIL_SIZE, 120)
        self.init_ui()

    def init_ui(self):
        # 共通スタイル
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QListWidget { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; outline: none; }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #3e3e42; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
            QLabel { font-size: 13px; }
            /* スライダー */
            QSlider::groove:horizontal { border: 1px solid #3e3e42; background: #2d2d30; height: 6px; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #007acc; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e0e0e0; border: 1px solid #777; width: 14px; margin: -5px 0; border-radius: 7px; }
            /* プログレスバー */
            QProgressBar { border: none; background-color: #2d2d30; height: 4px; border-radius: 2px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 2px; }
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)  # パネル間の隙間をゼロにしてボーダーで管理

        # --- 左サイドパネル (固定幅) ---
        left_panel = QWidget()
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(400)
        left_panel.setStyleSheet("border-right: 1px solid #3e3e42; background-color: #252526;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)

        wf = QLabel(
            "<b>ステップ④</b>　激似・連写をまとめて仕分けます。「③ 極小ファイル削除」の次です。"
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

        conf_layout.addWidget(QLabel("VP-Tree 類似検索設定"))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 25)
        self.slider.setValue(5)
        self.slider.valueChanged.connect(self.on_change)
        conf_layout.addWidget(self.slider)

        self.lbl_val = QLabel("距離: 5 (値が小さいほど激似)")
        self.lbl_val.setStyleSheet("color: #aaa; font-size: 11px;")
        conf_layout.addWidget(self.lbl_val)

        self.btn_run = QPushButton("全期間グルーピング実行")
        self.btn_run.setFixedHeight(36)
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; border: none; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #008cff; }
            QPushButton:pressed { background-color: #006bb3; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_run.clicked.connect(self.start_processing)
        conf_layout.addWidget(self.btn_run)

        # プログレス & ステータス (常に表示してレイアウト崩れを防ぐ)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        conf_layout.addWidget(self.progress)

        self.lbl_status = QLabel("待機中")
        self.lbl_status.setStyleSheet("color: #888; font-size: 11px;")
        conf_layout.addWidget(self.lbl_status)

        left_layout.addWidget(conf_box)

        # グループリスト
        left_layout.addWidget(QLabel("検出グループ一覧"))
        self.list = QListWidget()
        self.list.setStyleSheet("border: none; background-color: transparent;")
        self.list.itemClicked.connect(self.on_group_selected)
        self.list.currentItemChanged.connect(self.on_group_selected)  # キーボード選択にも対応
        left_layout.addWidget(self.list)

        # --- 右メインパネル ---
        right_splitter = QSplitter(Qt.Orientation.Horizontal)
        right_splitter.setStyleSheet("background-color: #1e1e1e;")

        # Grid Panel
        grid_panel = QWidget()
        right_layout = QVBoxLayout(grid_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)

        # ヘッダー (タイトル + ビュー切り替え)
        header_layout = QHBoxLayout()
        header_lbl = QLabel("詳細比較")
        header_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")

        # ビュー切り替えボタン
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

        # ボタングループ (排他制御)
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

        # スクロールエリア
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setStyleSheet("border: none; background-color: transparent;")

        self.container = QWidget()
        self.container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # キーボード操作に対応
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.area.setWidget(self.container)
        # キーイベントをインストール
        self.container.keyPressEvent = self.on_key_press
        # ホイールイベント（Ctrl+ホイールでサムネイルサイズ変更）
        self.area.wheelEvent = self._on_wheel_event

        # リサイズ対応: ビューポート幅変更時にグリッド再描画
        self.area.viewport().installEventFilter(self)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(150)
        self._relayout_timer.timeout.connect(self._on_relayout)
        self._prev_cols = 0

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
        right_splitter.setStretchFactor(0, 1)  # Grid flexible
        right_splitter.setStretchFactor(1, 0)  # Preview fixed
        right_splitter.splitterMoved.connect(lambda: self._relayout_timer.start())

        # 結合
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_splitter, 1)

    # --- Resize handling ---
    def eventFilter(self, obj, event):
        if obj == self.area.viewport() and event.type() == QEvent.Type.Resize:
            self._relayout_timer.start()
        return super().eventFilter(obj, event)

    def _on_relayout(self):
        """ビューポートリサイズ時にグリッドの列数を再計算し、必要なら再描画"""
        if self.view_mode != "grid" or not self.current_group_data:
            return
        new_cols = self._calc_cols()
        if new_cols != self._prev_cols:
            self._prev_cols = new_cols
            self.render_items(self.current_group_data)

    def _calc_cols(self):
        """スクロールエリアのビューポート幅からグリッド列数を計算"""
        thumb_size = max(self.thumbnail_size, 120)
        frame_width = thumb_size + 40
        viewport_w = self.area.viewport().width() - 20  # マージン分
        if viewport_w < frame_width:
            return 1
        return max(1, viewport_w // (frame_width + 10))  # 10 = spacing

    # --- Actions ---
    def on_change(self):
        val = self.slider.value()
        self.lbl_val.setText(f"距離: {val} (値が小さいほど激似)")
        self.lbl_status.setText("設定変更: 実行ボタンを押してください")
        # リセット処理 (プログレスバー等は0に戻すが、レイアウトは維持)
        self.progress.setValue(0)
        self.list.clear()
        self.clear_grid()
        self.current_group_data = []

    def toggle_view(self, btn):
        if btn == self.btn_view_grid:
            self.view_mode = "grid"
        else:
            self.view_mode = "list"

        # データがあれば再描画
        if self.current_group_data:
            self.render_items(self.current_group_data)

    def start_processing(self):
        self.btn_run.setEnabled(False)
        self.list.clear()
        self.clear_grid()
        self.current_group_data = []
        self.progress.setValue(0)

        threshold = self.slider.value()
        self.worker = GroupingWorker(self.db, threshold)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.lbl_status.setText)
        self.worker.result_ready.connect(self.display_results)
        self.worker.start()

    def display_results(self, groups):
        self.lbl_status.setText(f"完了: {len(groups)} グループ発見")
        self.btn_run.setEnabled(True)
        self.progress.setValue(100)

        if not groups:
            self.list.addItem("類似画像なし")
            return

        for grp in groups:
            rep = grp[0]
            pix = get_thumbnail(self.db, rep['id'], rep['path'], 40)
            icon = QIcon(pix)
            item = QListWidgetItem(icon, f"類似 {len(grp)}枚: {os.path.basename(rep['path'])}")
            item.setData(Qt.ItemDataRole.UserRole, grp)
            self.list.addItem(item)

    def on_group_selected(self, item):
        if not item:  # currentItemChangedはNoneを送ることがある
            return
        grp = item.data(Qt.ItemDataRole.UserRole)
        if not grp: return
        
        # 削除されたファイルを除外（データベースから再確認）
        valid_grp = []
        for data in grp:
            status = self.db.get_file_status(data['id'])
            if status and status != 'trash':
                valid_grp.append(data)
        
        # グループが空でもリストからは削除しない（仕様変更）
        if not valid_grp or len(valid_grp) < 2:
            # グループが空になった場合でも、リストは残す
            self.clear_grid()
            # リストアイテムのカウントを更新
            remaining_count = len(valid_grp) if valid_grp else 0
            item.setText(f"類似 {remaining_count}枚（全て削除済み）")
            return
        
        # ファイルサイズの大きい順にソート（sizeキーがある場合）
        if valid_grp and len(valid_grp) > 0 and 'size' in valid_grp[0]:
            valid_grp.sort(key=lambda x: x.get('size', 0), reverse=True)
        self.current_group_data = valid_grp  # データを保持
        self.render_items(valid_grp)
        
        # リストアイテムのカウントを更新
        remaining_count = len(valid_grp)
        rep = valid_grp[0] if valid_grp else None
        if rep:
            item.setText(f"類似 {remaining_count}枚: {os.path.basename(rep['path'])}")

    def render_items(self, grp):
        self.clear_grid()

        if self.view_mode == "grid":
            self.render_grid_view(grp)
        else:
            self.render_list_view(grp)
        # サイズラベルを更新
        self.size_hint_label.setText(f"サムネイル: {self.thumbnail_size}px (Ctrl+ホイールで変更)")

    # --- Wheel Event ---
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
                if self.view_mode == "grid" and self.current_group_data:
                    self.render_items(self.current_group_data)
        else:
            QScrollArea.wheelEvent(self.area, event)

    # --- Renderers ---
    def render_grid_view(self, grp):
        thumb_size = max(self.thumbnail_size, 120)
        cols = self._calc_cols()
        self._prev_cols = cols

        for i, data in enumerate(grp):
            f = QFrame()
            frame_width = thumb_size + 40
            frame_height = thumb_size + 80  # ファイル名とサイズ表示のため高さを増やす
            f.setFixedSize(frame_width, frame_height)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)
            
            def make_cb(d):
                return lambda ev: self.update_preview(d)
            f.mousePressEvent = make_cb(data)
            
            # ダブルクリックでビューアで開く
            def make_double_click_handler(d):
                return lambda event: self._open_in_viewer(d)
            f.mouseDoubleClickEvent = make_double_click_handler(data)
            f.setCursor(Qt.CursorShape.PointingHandCursor)
            
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
            file_size = format_file_size_kb(data.get('size', 0))
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

    def render_list_view(self, grp):
        thumb_size = 80

        for i, data in enumerate(grp):
            f = QFrame()
            f.setFixedHeight(100)  # リストの高さ固定
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)

            l = QHBoxLayout(f)
            l.setContentsMargins(10, 10, 10, 10)
            l.setSpacing(15)

            # 画像 (左)
            lbl = QLabel()
            pix = get_thumbnail(self.db, data['id'], data['path'], thumb_size)
            apply_thumbnail_to_label(lbl, pix, thumb_size)
            lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

            # クリックとダブルクリックイベント
            def make_click_handler(d):
                return lambda event: self.update_preview(d)
            f.mousePressEvent = make_click_handler(data)
            
            def make_double_click_handler(d):
                return lambda event: self._open_in_viewer(d)
            f.mouseDoubleClickEvent = make_double_click_handler(data)
            f.setCursor(Qt.CursorShape.PointingHandCursor)

            # 情報 (中央)
            info_layout = QVBoxLayout()
            file_name = os.path.basename(data['path'])
            file_size = format_file_size_kb(data.get('size', 0))
            name_lbl = QLabel(f"{file_name}\n{file_size}")
            name_lbl.setStyleSheet("border: none; font-size: 14px; font-weight: bold; color: #fff;")
            path_lbl = QLabel(data['path'])
            path_lbl.setStyleSheet("border: none; font-size: 11px; color: #888;")
            path_lbl.setWordWrap(True)

            info_layout.addWidget(name_lbl)
            info_layout.addWidget(path_lbl)
            info_layout.addStretch()

            # ボタン (右)
            btn = QPushButton("ゴミ箱へ")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet(self.get_del_btn_style())
            btn.clicked.connect(lambda _, fid=data['id'], w=f: self.trash(fid, w))

            l.addWidget(lbl)
            l.addLayout(info_layout, stretch=1)
            l.addWidget(btn)

            self.grid.addWidget(f, i, 0)  # 1列に積む

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

            self.current_group_data = [d for d in self.current_group_data if d['id'] != fid]
            current_item = self.list.currentItem()

            if not self.current_group_data or len(self.current_group_data) < 2:
                self.clear_grid()
                if current_item:
                    remaining = len(self.current_group_data) if self.current_group_data else 0
                    current_item.setText(f"類似 {remaining}枚（全て削除済み）")
            else:
                self.render_items(self.current_group_data)

                if deleted_index >= 0 and deleted_index < len(self.current_group_data):
                    self.focus_item_by_index(deleted_index)
                elif self.current_group_data:
                    self.focus_item_by_index(len(self.current_group_data) - 1)

                if current_item:
                    rep = self.current_group_data[0]
                    current_item.setText(f"類似 {len(self.current_group_data)}枚: {os.path.basename(rep['path'])}")
        else:
            QMessageBox.warning(self, "削除失敗", "ファイルの削除に失敗しました。\nログを確認してください。")

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()

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
    
    def _open_in_viewer(self, item):
        """デフォルトビューアで画像を開く"""
        if not open_file_in_viewer(item['path']):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "エラー", f"ファイルを開けませんでした:\n{item['path']}")
    
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
        if not self.current_group_data or index < 0 or index >= len(self.current_group_data):
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
        if not self.current_group_data:
            return
        if current_index < len(self.current_group_data) - 1:
            self.focus_item_by_index(current_index + 1)
        elif len(self.current_group_data) > 0:
            # 最後のアイテムの場合は最初に戻る
            self.focus_item_by_index(0)
    
    def focus_prev_item(self, current_index):
        """前のアイテムにフォーカスを移動"""
        if not self.current_group_data:
            return
        if current_index > 0:
            self.focus_item_by_index(current_index - 1)
        elif len(self.current_group_data) > 0:
            # 最初のアイテムの場合は最後に移動
            self.focus_item_by_index(len(self.current_group_data) - 1)


if __name__ == "__main__":
    setup_logging()
    app = QApplication(sys.argv)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
    app.setPalette(palette)

    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "photos.db")
    db = DatabaseManager(db_path)
    window = QWidget()
    window.setWindowTitle("類似整理 - 商用UI版")
    window.resize(1100, 750)
    layout = QVBoxLayout(window)
    layout.addWidget(SimilarityPage(db))
    window.show()
    sys.exit(app.exec())