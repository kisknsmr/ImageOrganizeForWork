import sys
import os
import logging
import imagehash
import random
import statistics
from collections import deque
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QLabel, QPushButton, QSlider, QListWidgetItem,
                             QScrollArea, QFrame, QGridLayout, QApplication,
                             QProgressBar, QSizePolicy, QButtonGroup)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPalette, QColor

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager

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
        for i, (fid, path, phash, mtime) in enumerate(rows):
            if not phash: continue
            try:
                items.append({'id': fid, 'path': path, 'hash': int(phash, 16)})
            except:
                pass
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
        self.init_ui()

    def init_ui(self):
        # 共通スタイル
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
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
        left_panel.setFixedWidth(320)  # ★幅固定でガタつき防止
        left_panel.setStyleSheet("border-right: 1px solid #3e3e42; background-color: #252526;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)

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
        left_layout.addWidget(self.list)

        # --- 右メインパネル ---
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(right_panel)
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

        header_layout.addWidget(header_lbl)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_view_grid)
        header_layout.addWidget(self.btn_view_list)

        right_layout.addLayout(header_layout)

        # スクロールエリア
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setStyleSheet("border: none; background-color: transparent;")

        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.area.setWidget(self.container)
        right_layout.addWidget(self.area)

        # 結合
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

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
            pix = get_db_thumbnail(self.db, rep['id'], rep['path'], 40)
            icon = QIcon(pix)
            item = QListWidgetItem(icon, f"類似 {len(grp)}枚: {os.path.basename(rep['path'])}")
            item.setData(Qt.ItemDataRole.UserRole, grp)
            self.list.addItem(item)

    def on_group_selected(self, item):
        grp = item.data(Qt.ItemDataRole.UserRole)
        if not grp: return
        self.current_group_data = grp  # データを保持
        self.render_items(grp)

    def render_items(self, grp):
        self.clear_grid()

        if self.view_mode == "grid":
            self.render_grid_view(grp)
        else:
            self.render_list_view(grp)

    # --- Renderers ---
    def render_grid_view(self, grp):
        cols = 5
        thumb_size = 120

        for i, data in enumerate(grp):
            f = QFrame()
            f.setFixedSize(140, 180)
            f.setStyleSheet("""
                QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 6px; }
                QFrame:hover { border-color: #007acc; background-color: #353538; }
            """)

            l = QVBoxLayout(f)
            l.setContentsMargins(8, 8, 8, 8)
            l.setSpacing(5)

            lbl = QLabel()
            pix = get_db_thumbnail(self.db, data['id'], data['path'], thumb_size)
            lbl.setPixmap(pix)
            lbl.setScaledContents(True)
            lbl.setFixedSize(thumb_size, thumb_size)
            lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

            name_lbl = QLabel(os.path.basename(data['path']))
            name_lbl.setStyleSheet("border: none; font-size: 10px; color: #ccc;")
            name_lbl.setWordWrap(True)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setFixedHeight(25)

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
            pix = get_db_thumbnail(self.db, data['id'], data['path'], thumb_size)
            lbl.setPixmap(pix)
            lbl.setScaledContents(True)
            lbl.setFixedSize(thumb_size, thumb_size)
            lbl.setStyleSheet("border: none; border-radius: 4px; background: #000;")

            # 情報 (中央)
            info_layout = QVBoxLayout()
            name_lbl = QLabel(os.path.basename(data['path']))
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
        if self.db.move_to_trash(fid): widget.hide()

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()


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