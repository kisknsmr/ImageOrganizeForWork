import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                             QTreeView, QAbstractItemView, QPushButton,
                             QLabel, QMessageBox, QMenu, QInputDialog, QFrame,
                             QListWidget, QListWidgetItem, QProgressBar, QSizePolicy,
                             QFileDialog)
from PyQt6.QtCore import Qt, QSize, QDir, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFileSystemModel, QPixmap


from src.core import get_file_info, format_file_size
from src.database import DatabaseManager
from gui.thumbnail_preview import (
    get_thumbnail,
    get_preview,
    apply_preview_to_label,
    DEFAULT_PREVIEW_MAX_WIDTH,
    DEFAULT_PREVIEW_MAX_HEIGHT,
)

logger = logging.getLogger(__name__)


# --- パンくずリスト ---
class BreadcrumbNav(QWidget):
    path_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.current_path = ""

    def set_path(self, path):
        self.current_path = path
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        path = os.path.normpath(path)
        if os.name == 'nt':
            parts = path.split('\\')
        else:
            parts = path.split('/')
            if path.startswith('/'):
                parts[0] = '/'

        accumulated_path = ""
        for i, part in enumerate(parts):
            if not part: continue

            if i == 0:
                accumulated_path = part
                if os.name == 'nt' and ':' in part:
                    accumulated_path += '\\'
            else:
                accumulated_path = os.path.join(accumulated_path, part)

            btn = QPushButton(part)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { 
                    color: #e0e0e0; font-weight: bold; border: none; 
                    padding: 4px 8px; background-color: transparent; font-size: 13px;
                }
                QPushButton:hover { background-color: #444; border-radius: 4px; color: #fff; }
            """)
            btn.clicked.connect(lambda checked, p=accumulated_path: self.path_clicked.emit(p))
            self.layout.addWidget(btn)

            if i < len(parts) - 1:
                arrow = QLabel(" › ")
                arrow.setStyleSheet("color: #888; font-weight: bold; font-size: 14px;")
                self.layout.addWidget(arrow)

        self.layout.addStretch()


# --- Worker ---
class MoveFilesWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(int, list)

    def __init__(self, db, file_list, dest_folder):
        super().__init__()
        self.db = db
        self.file_list = file_list
        self.dest_folder = dest_folder
        self.is_running = True

    def run(self):
        total = len(self.file_list)
        success_count = 0
        errors = []

        for i, item in enumerate(self.file_list):
            if not self.is_running: break
            fid = item['id']
            src_path = item['path']
            if self.db.move_file_to_folder(fid, src_path, self.dest_folder):
                success_count += 1
            else:
                errors.append(os.path.basename(src_path))
            self.progress.emit(i + 1, total)

        self.finished.emit(success_count, errors)

    def stop(self):
        self.is_running = False


# --- Main UI ---
class ManualSorterPage(QWidget):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.current_source_folder = None
        self.all_source_folders = []
        self.worker = None
        self.is_select_mode = False
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QSplitter::handle { background-color: #3e3e42; }
            QSplitter::handle:horizontal { width: 3px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header
        header_frame = QFrame()
        header_frame.setMinimumHeight(48)
        header_frame.setStyleSheet("background-color: #2d2d30; border-bottom: 1px solid #3e3e42;")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 6, 15, 6)
        header_layout.setSpacing(2)
        title_row = QHBoxLayout()
        title_lbl = QLabel("🗂 手動仕分け（ステップ⑤）")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        header_layout.addLayout(title_row)
        sub_lbl = QLabel("メイン整理フローの最終段階。残す／捨てる・フォルダ分けに使います")
        sub_lbl.setStyleSheet("font-size: 11px; color: #888; font-weight: normal;")
        header_layout.addWidget(sub_lbl)
        main_layout.addWidget(header_frame)

        # 2. Splitter（メインコンテンツ）
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # =========================================
        # 左ペイン: ソース画像一覧
        # =========================================
        left_widget = QWidget()
        left_widget.setMinimumWidth(300)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 4, 8)
        left_layout.setSpacing(6)

        # パンくずナビ
        nav_bar = QFrame()
        nav_bar.setStyleSheet("background-color: #252526; border-radius: 4px; border: 1px solid #3e3e42;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(5, 2, 5, 2)

        self.breadcrumb = BreadcrumbNav()
        self.breadcrumb.path_clicked.connect(self.load_images)

        self.btn_folder_menu = QPushButton("▼")
        self.btn_folder_menu.setFixedSize(28, 28)
        self.btn_folder_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder_menu.setStyleSheet(
            "QPushButton { border: none; color: #aaa; border-radius: 4px; } "
            "QPushButton:hover { color: white; background-color: #444; }")
        self.btn_folder_menu.clicked.connect(self.show_source_folder_menu)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedSize(28, 28)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(
            "QPushButton { border: none; color: #aaa; border-radius: 4px; } "
            "QPushButton:hover { color: white; background-color: #444; }")
        btn_refresh.clicked.connect(self.refresh_source_list)

        nav_layout.addWidget(self.breadcrumb, 1)
        nav_layout.addWidget(self.btn_folder_menu)
        nav_layout.addWidget(btn_refresh)
        left_layout.addWidget(nav_bar)

        # モード切替
        self.btn_mode_toggle = QPushButton("🔍 プレビューモード（クリックで切替）")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setFixedHeight(30)
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.setStyleSheet("""
            QPushButton { background-color: #333; color: #ddd; border: 1px solid #555;
                          padding: 4px 10px; border-radius: 4px; font-size: 12px; }
            QPushButton:checked { background-color: #d83b01; color: white; border-color: #d83b01; }
        """)
        self.btn_mode_toggle.toggled.connect(self.toggle_selection_mode)
        left_layout.addWidget(self.btn_mode_toggle)

        # サムネイル一覧
        self.list_source = QListWidget()
        self.list_source.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_source.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_source.setIconSize(QSize(140, 140))
        self.list_source.setSpacing(6)
        self.list_source.setStyleSheet(
            "QListWidget { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px; outline: none; }"
            "QListWidget::item:selected { background-color: #007acc; border-radius: 4px; }")
        self.list_source.itemClicked.connect(self.on_item_clicked)
        left_layout.addWidget(self.list_source, 1)

        # フッター（選択数 + 全選択ボタン）
        sel_layout = QHBoxLayout()
        sel_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_selection_count = QLabel("0 枚選択中")
        self.lbl_selection_count.setStyleSheet("color: #888; font-size: 11px;")
        self.list_source.itemSelectionChanged.connect(self.update_selection_count)

        btn_sel_all = QPushButton("全選択")
        btn_sel_all.setFixedHeight(26)
        btn_sel_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sel_all.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: 1px solid #555; "
            "border-radius: 4px; padding: 2px 12px; font-size: 11px; }"
            "QPushButton:hover { background-color: #444; }")
        btn_sel_all.clicked.connect(self.list_source.selectAll)

        sel_layout.addWidget(self.lbl_selection_count)
        sel_layout.addStretch()
        sel_layout.addWidget(btn_sel_all)
        left_layout.addLayout(sel_layout)

        self.splitter.addWidget(left_widget)

        # =========================================
        # 中央ペイン: 移動先フォルダツリー
        # =========================================
        mid_widget = QWidget()
        mid_widget.setMinimumWidth(220)
        mid_layout = QVBoxLayout(mid_widget)
        mid_layout.setContentsMargins(4, 8, 4, 8)
        mid_layout.setSpacing(6)

        tree_header_layout = QHBoxLayout()
        tree_label = QLabel("移動先フォルダ")
        tree_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        tree_header_layout.addWidget(tree_label)
        tree_header_layout.addStretch()

        btn_change_root = QPushButton("📂 ルート変更")
        btn_change_root.setFixedHeight(26)
        btn_change_root.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change_root.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; background-color: #333; "
            "color: #ccc; border: 1px solid #555; border-radius: 4px; }"
            "QPushButton:hover { background-color: #444; }")
        btn_change_root.clicked.connect(self.change_tree_root)
        tree_header_layout.addWidget(btn_change_root)
        mid_layout.addLayout(tree_header_layout)

        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)

        self.tree_target = QTreeView()
        self.tree_target.setModel(self.fs_model)
        self.tree_target.setStyleSheet(
            "QTreeView { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px; outline: none; }"
            "QTreeView::item { padding: 3px 0; }"
            "QTreeView::item:selected { background-color: #007acc; }")
        self.tree_target.setHeaderHidden(True)
        for i in range(1, 4):
            self.tree_target.hideColumn(i)
        self.tree_target.setRootIndex(self.fs_model.index(QDir.homePath()))
        self.tree_target.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_target.customContextMenuRequested.connect(self.show_tree_context_menu)
        mid_layout.addWidget(self.tree_target, 1)

        btn_mkdir = QPushButton("📂 新規フォルダ作成")
        btn_mkdir.setFixedHeight(30)
        btn_mkdir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_mkdir.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: 1px solid #555; "
            "border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background-color: #444; }")
        btn_mkdir.clicked.connect(self.create_new_folder_action)
        mid_layout.addWidget(btn_mkdir)

        self.splitter.addWidget(mid_widget)

        # =========================================
        # 右ペイン: プレビュー
        # =========================================
        self.preview_panel = preview_panel = QFrame()
        preview_panel.setMinimumWidth(200)
        preview_panel.setMaximumWidth(450)
        preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)

        preview_title = QLabel("プレビュー")
        preview_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
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

        self.splitter.addWidget(preview_panel)

        # スプリッター設定
        self.splitter.setStretchFactor(0, 3)   # ソース一覧: 伸縮大
        self.splitter.setStretchFactor(1, 2)   # フォルダツリー: 伸縮中
        self.splitter.setStretchFactor(2, 0)   # プレビュー: 固定寄り
        self.splitter.setSizes([450, 350, 300])
        main_layout.addWidget(self.splitter, 1)

        # 3. アクションバー
        action_frame = QFrame()
        action_frame.setFixedHeight(56)
        action_frame.setStyleSheet("background-color: #2d2d30; border-top: 1px solid #3e3e42;")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(15, 8, 15, 8)
        action_layout.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #1e1e1e; border-radius: 4px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 4px; }
        """)

        self.btn_move = QPushButton("➡ 選択したファイルを移動")
        self.btn_move.setFixedHeight(36)
        self.btn_move.setMinimumWidth(220)
        self.btn_move.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold;
                          font-size: 13px; border-radius: 4px; padding: 0 20px; }
            QPushButton:hover { background-color: #0099ff; }
            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:disabled { background-color: #444; color: #888; }
        """)
        self.btn_move.clicked.connect(self.start_move_process)

        action_layout.addWidget(self.progress_bar, 1)
        action_layout.addWidget(self.btn_move)
        main_layout.addWidget(action_frame)

        self.refresh_source_list()

    # --- Methods ---
    def change_tree_root(self):
        folder = QFileDialog.getExistingDirectory(self, "ツリーのルートを選択")
        if folder:
            idx = self.fs_model.index(folder)
            if idx.isValid():
                self.tree_target.setRootIndex(idx)

    def refresh_source_list(self):
        files = self.db.get_all_files()
        if not files:
            self.list_source.clear()
            self.breadcrumb.set_path("ファイルなし")
            return

        self.all_source_folders = sorted(list(set(os.path.dirname(f) for f in files)))

        if self.current_source_folder and self.current_source_folder in self.all_source_folders:
            self.load_images(self.current_source_folder)
        elif self.all_source_folders:
            self.load_images(self.all_source_folders[0])
        else:
            # ファイルがなくなった場合
            self.list_source.clear()
            self.breadcrumb.set_path("ファイルなし")

    def show_source_folder_menu(self):
        if not self.all_source_folders: return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #2d2d30; color: white; } QMenu::item:selected { background-color: #007acc; }")

        for path in self.all_source_folders:
            folder_name = os.path.basename(path)
            action = QAction(f"{folder_name}   ({os.path.dirname(path)})", self)
            action.triggered.connect(lambda checked, p=path: self.load_images(p))
            menu.addAction(action)

        menu.exec(self.btn_folder_menu.mapToGlobal(self.btn_folder_menu.rect().bottomLeft()))

    def load_images(self, folder):
        self.current_source_folder = folder
        self.breadcrumb.set_path(folder)

        self.list_source.clear()
        self.update_selection_count()

        all_files = self.db.get_all_files()
        target_files = [f for f in all_files if os.path.dirname(f) == folder]

        for path in target_files:
            if not os.path.exists(path): continue

            fid = self.get_file_id(path)
            item = QListWidgetItem()
            item.setText(os.path.basename(path))
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, {'id': fid, 'path': path})

            pix = get_thumbnail(self.db, fid, path, 140)
            item.setIcon(QIcon(pix))

            self.list_source.addItem(item)

    def get_file_id(self, path):
        return self.db.get_file_id_by_path(path)

    def update_selection_count(self):
        count = len(self.list_source.selectedItems())
        self.lbl_selection_count.setText(f"{count} 枚選択中")

    def toggle_selection_mode(self, checked):
        self.is_select_mode = checked
        if checked:
            self.btn_mode_toggle.setText("現在: ✅ 選択モード")
            self.list_source.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        else:
            self.btn_mode_toggle.setText("現在: 🔍 プレビューモード")
            self.list_source.clearSelection()
            self.list_source.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

    def on_item_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        # Update preview regardless of mode
        self.update_preview(data)
        
        if not self.is_select_mode:
            # In preview mode, maybe clicking just shows preview (already done above)
            # Old dialog logic removed
            pass

    def update_preview(self, data):
        if not data:
            self.preview_image.clear()
            self.preview_image.setText("画像を選択してください")
            self.preview_info.setText("")
            return
        path = data['path']
        pix = get_preview(path)
        # プレビューパネルの幅に合わせる（親パネルを参照し縮小ループを防止）
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
            self.preview_image.setText("プレビュー不可")

        # Info
        file_info = get_file_info(path)
        info_lines = []
        info_lines.append(f"<b>ファイル名:</b> {os.path.basename(path)}")
        info_lines.append(f"<b>パス:</b> {path}")
        
        if file_info['exists']:
            info_lines.append(f"<b>ファイルサイズ:</b> {format_file_size(file_info['file_size'])}")
            if file_info['image_width'] and file_info['image_height']:
                info_lines.append(f"<b>画像サイズ:</b> {file_info['image_width']} × {file_info['image_height']} px")
        else:
            info_lines.append("<b style='color: #d83b01;'>ファイルが見つかりません</b>")
        
        self.preview_info.setText("<br>".join(info_lines))

    def show_tree_context_menu(self, pos):
        idx = self.tree_target.indexAt(pos)
        menu = QMenu()
        action_new = QAction("📂 新規フォルダ作成", self)
        action_new.triggered.connect(lambda: self.create_new_folder_action(idx))
        menu.addAction(action_new)
        menu.exec(self.tree_target.mapToGlobal(pos))

    def create_new_folder_action(self, index=None):
        if index is None or not isinstance(index, type(self.tree_target.currentIndex())):
            index = self.tree_target.currentIndex()
        if not index.isValid():
            base_dir = self.fs_model.rootPath()
        else:
            if self.fs_model.isDir(index):
                base_dir = self.fs_model.filePath(index)
            else:
                base_dir = os.path.dirname(self.fs_model.filePath(index))
        name, ok = QInputDialog.getText(self, "新規フォルダ", "フォルダ名:", text="")
        if ok and name:
            new_path = os.path.join(base_dir, name)
            try:
                os.makedirs(new_path, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"作成失敗: {e}")

    def start_move_process(self):
        items = self.list_source.selectedItems()
        if not self.is_select_mode and not items:
            QMessageBox.information(self, "ガイド", "「選択モード」に切り替えて写真を選択してください。")
            return
        if not items:
            QMessageBox.information(self, "情報", "移動するファイルを選択してください。")
            return
        idx = self.tree_target.currentIndex()
        if not idx.isValid():
            QMessageBox.warning(self, "注意", "移動先のフォルダを選択してください。")
            return
        dest_folder = self.fs_model.filePath(idx)
        if not self.fs_model.isDir(idx):
            dest_folder = os.path.dirname(dest_folder)
        if os.path.abspath(self.current_source_folder) == os.path.abspath(dest_folder):
            QMessageBox.information(self, "スキップ", "移動元と移動先が同じです。")
            return
        ans = QMessageBox.question(self, "移動確認",
                                   f"{len(items)} 枚のファイルを以下へ移動しますか？\n\n{dest_folder}",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes: return
        file_list = []
        for item in items:
            file_list.append(item.data(Qt.ItemDataRole.UserRole))
        self.btn_move.setEnabled(False)
        self.list_source.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, len(items))
        self.worker = MoveFilesWorker(self.db, file_list, dest_folder)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_move_finished)
        self.worker.start()

    def on_move_finished(self, success_count, errors):
        self.btn_move.setEnabled(True)
        self.list_source.setEnabled(True)
        # ★修正: ライブラリ全体（フォルダ一覧）をリフレッシュする
        self.refresh_source_list()

        msg = f"移動完了: {success_count} 件"
        if errors:
            msg += f"\n\n⚠️ エラーまたはスキップ ({len(errors)}件):\n" + "\n".join(errors[:5])
            QMessageBox.warning(self, "完了 (一部エラー)", msg)
        else:
            QMessageBox.information(self, "完了", msg)