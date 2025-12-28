import sys
import os
import shutil
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                             QTreeView, QAbstractItemView, QPushButton,
                             QLabel, QMessageBox, QMenu, QInputDialog, QFrame,
                             QListWidget, QListWidgetItem, QProgressBar, QSizePolicy,
                             QDialog, QScrollArea, QFileDialog)
from PyQt6.QtCore import Qt, QSize, QDir, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFileSystemModel, QPixmap, QImageReader

# core.py からサムネイル取得関数などを利用
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, DatabaseManager, get_file_info, format_file_size

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


# --- Preview Dialog ---
class ImagePreviewDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"プレビュー: {os.path.basename(path)}")
        self.resize(800, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        layout = QVBoxLayout(self)
        lbl = QLabel()

        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid() and (size.width() > 1600 or size.height() > 1600):
                size.scale(1600, 1600, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)

            img = reader.read()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                lbl.setPixmap(pix.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
            else:
                lbl.setText("プレビュー不可")
        except Exception:
            lbl.setText("プレビュー不可")

        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        btn_close = QPushButton("閉じる")
        btn_close.clicked.connect(self.close)
        btn_close.setStyleSheet("background-color: #444; color: white; padding: 8px;")
        layout.addWidget(btn_close)


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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # 1. Header
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 5)
        title_lbl = QLabel("🗂 手動仕分け (2ペインモード)")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        main_layout.addWidget(header_frame)

        # 2. Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")

        # --- Left Pane ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)

        # Breadcrumb
        nav_bar = QFrame()
        nav_bar.setStyleSheet("background-color: #252526; border-radius: 4px; border: 1px solid #3e3e42;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(5, 2, 5, 2)

        self.breadcrumb = BreadcrumbNav()
        self.breadcrumb.path_clicked.connect(self.load_images)

        self.btn_folder_menu = QPushButton("▼")
        self.btn_folder_menu.setFixedWidth(25)
        self.btn_folder_menu.setStyleSheet(
            "QPushButton { border: none; color: #aaa; } QPushButton:hover { color: white; background-color: #444; }")
        self.btn_folder_menu.clicked.connect(self.show_source_folder_menu)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedWidth(30)
        btn_refresh.setStyleSheet("QPushButton { border: none; color: #aaa; } QPushButton:hover { color: white; }")
        btn_refresh.clicked.connect(self.refresh_source_list)

        nav_layout.addWidget(self.breadcrumb, 1)
        nav_layout.addWidget(self.btn_folder_menu)
        nav_layout.addWidget(btn_refresh)

        left_layout.addWidget(nav_bar)

        # Mode Toggle
        mode_layout = QHBoxLayout()
        self.btn_mode_toggle = QPushButton("現在: 🔍 プレビューモード (クリックで拡大)")
        self.btn_mode_toggle.setCheckable(True)
        self.btn_mode_toggle.setStyleSheet("""
            QPushButton { background-color: #333; color: #ddd; border: 1px solid #555; padding: 6px; }
            QPushButton:checked { background-color: #d83b01; color: white; border-color: #d83b01; }
        """)
        self.btn_mode_toggle.toggled.connect(self.toggle_selection_mode)
        mode_layout.addWidget(self.btn_mode_toggle)
        left_layout.addLayout(mode_layout)

        # Thumbnails
        self.list_source = QListWidget()
        self.list_source.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_source.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_source.setIconSize(QSize(140, 140))  # サムネイルサイズ
        self.list_source.setSpacing(6)
        self.list_source.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42;")
        self.list_source.itemClicked.connect(self.on_item_clicked)
        left_layout.addWidget(self.list_source)

        # Footer
        sel_layout = QHBoxLayout()
        self.lbl_selection_count = QLabel("0 枚選択中")
        self.list_source.itemSelectionChanged.connect(self.update_selection_count)
        btn_sel_all = QPushButton("全選択")
        btn_sel_all.clicked.connect(self.list_source.selectAll)
        sel_layout.addWidget(self.lbl_selection_count)
        sel_layout.addStretch()
        sel_layout.addWidget(btn_sel_all)
        left_layout.addLayout(sel_layout)

        self.splitter.addWidget(left_widget)

        # --- Right Pane ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)

        # ルート変更ボタン
        tree_header_layout = QHBoxLayout()
        tree_header_layout.addWidget(QLabel("移動先フォルダ:"))
        tree_header_layout.addStretch()
        btn_change_root = QPushButton("📂 ルート変更")
        btn_change_root.setFixedHeight(24)
        btn_change_root.setStyleSheet("font-size: 11px; padding: 0 8px;")
        btn_change_root.clicked.connect(self.change_tree_root)
        tree_header_layout.addWidget(btn_change_root)
        right_layout.addLayout(tree_header_layout)

        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)

        self.tree_target = QTreeView()
        self.tree_target.setModel(self.fs_model)
        self.tree_target.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42;")
        self.tree_target.setColumnWidth(0, 250)
        for i in range(1, 4): self.tree_target.hideColumn(i)

        # 初期ルート: ホーム
        self.tree_target.setRootIndex(self.fs_model.index(QDir.homePath()))

        self.tree_target.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_target.customContextMenuRequested.connect(self.show_tree_context_menu)
        right_layout.addWidget(self.tree_target)

        btn_mkdir = QPushButton("📂 新規フォルダ作成")
        btn_mkdir.clicked.connect(self.create_new_folder_action)
        right_layout.addWidget(btn_mkdir)

        self.splitter.addWidget(right_widget)

        # --- Preview Pane (Far Right) ---
        preview_panel = QFrame()
        preview_panel.setFrameShape(QFrame.Shape.StyledPanel)
        preview_panel.setStyleSheet("background-color: #252526; border-left: 1px solid #3e3e42;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(15)
        
        preview_title = QLabel("プレビュー")
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        preview_layout.addWidget(preview_title)
        
        self.preview_image = QLabel("画像を選択してください")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumSize(200, 200)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        self.preview_image.setScaledContents(True)
        # 縦横比保持のためにPaintEventなどをいじるのは手間なので、setPixmap時にscaledする方針
        preview_layout.addWidget(self.preview_image, 1) # Stretch
        
        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #aaa; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        
        self.splitter.addWidget(preview_panel)


        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 3)
        main_layout.addWidget(self.splitter, 1)

        # 3. Action
        action_frame = QFrame()
        action_frame.setStyleSheet("background-color: #2d2d30; border-top: 1px solid #444;")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(10, 10, 10, 10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)

        self.btn_move = QPushButton("➡ 選択したファイルを移動")
        self.btn_move.setFixedHeight(40)
        self.btn_move.setFixedWidth(250)
        self.btn_move.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #0099ff; }
            QPushButton:pressed { background-color: #005a9e; }
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

            pix = get_db_thumbnail(self.db, fid, path, 140)
            item.setIcon(QIcon(pix))

            self.list_source.addItem(item)

    def get_file_id(self, path):
        try:
            import sqlite3
            with self.db.lock:
                row = self.db.conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
                return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Database error in get_file_id: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error in get_file_id: {e}", exc_info=True)
            return 0

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
        fid = data.get('id', 0)
        
        # Determine preview size based on widget size? Fixed 400px for now
        pix = get_db_thumbnail(self.db, fid, path, 400)
        if pix:
            self.preview_image.setPixmap(pix)
        else:
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