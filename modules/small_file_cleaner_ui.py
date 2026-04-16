"""
小さいファイル削除UIモジュール
極端に小さいファイル（サムネイルなど）を検出して削除
"""
import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFileDialog, QFrame, QScrollArea, QProgressBar,
                             QMessageBox, QCheckBox, QSpinBox, QSplitter, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap


from src.core import setup_logging, get_file_info, format_file_size
from src.database import DatabaseManager
from gui.thumbnail_preview import (
    get_preview,
    apply_preview_to_label,
    open_file_in_viewer,
    DEFAULT_PREVIEW_MAX_WIDTH,
    DEFAULT_PREVIEW_MAX_HEIGHT,
)
from src.config import config

logger = logging.getLogger(__name__)


class SmallFileScanner(QThread):
    """小さいファイルをスキャンするワーカースレッド"""
    progress = pyqtSignal(int, int)  # current, total
    status = pyqtSignal(str)
    file_found = pyqtSignal(dict)  # ファイル情報辞書
    finished = pyqtSignal(list)  # 見つかったファイルのリスト

    def __init__(self, db_manager, min_file_size, min_image_width, min_image_height):
        super().__init__()
        self.db = db_manager
        self.min_file_size = min_file_size
        self.min_image_width = min_image_width
        self.min_image_height = min_image_height
        self.stop_flag = False

    def stop(self):
        """スキャンを停止"""
        self.stop_flag = True

    def run(self):
        """スキャンを実行"""
        self.status.emit("データベースからファイルを取得中...")
        
        try:
            # データベースから全ファイルを取得
            rows = self.db.get_non_trash_files_raw()
            
            total = len(rows)
            if total == 0:
                self.finished.emit([])
                return

            found_files = []
            
            for i, (file_id, path, db_size) in enumerate(rows):
                if self.stop_flag:
                    self.status.emit("スキャンが停止されました")
                    break
                
                if i % 100 == 0:
                    self.progress.emit(i, total)
                    self.status.emit(f"スキャン中... {i}/{total}")
                
                # ファイルサイズチェック
                if db_size < self.min_file_size:
                    file_info = get_file_info(path)
                    if file_info['exists']:
                        # 画像サイズもチェック
                        is_small_image = False
                        if file_info['image_width'] and file_info['image_height']:
                            if (file_info['image_width'] < self.min_image_width or 
                                file_info['image_height'] < self.min_image_height):
                                is_small_image = True
                        
                        found_files.append({
                            'id': file_id,
                            'path': path,
                            'file_size': file_info['file_size'],
                            'image_width': file_info['image_width'],
                            'image_height': file_info['image_height'],
                            'is_small_image': is_small_image
                        })
                        self.file_found.emit(found_files[-1])
            
            self.progress.emit(total, total)
            self.status.emit("スキャン完了")
            self.finished.emit(found_files)
            
        except Exception as e:
            logger.error(f"Small file scanner error: {e}", exc_info=True)
            self.status.emit(f"エラー: {e}")
            self.finished.emit([])


class SmallFileCleanerPage(QWidget):
    """小さいファイル削除ページ"""
    
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.scanner = None
        self.found_files = []
        self.selected_files = set()  # 選択されたファイルIDのセット
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

        # =========================================
        # ヘッダー
        # =========================================
        header_frame = QFrame()
        header_frame.setMinimumHeight(48)
        header_frame.setStyleSheet("background-color: #2d2d30; border-bottom: 1px solid #3e3e42;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 6, 15, 6)
        title = QLabel("🗑️ 極小ファイル削除（ステップ③）")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        header_layout.addWidget(title)
        hint = QLabel("②ピンボケの次。サムネ級の不要ファイルを除きます")
        hint.setStyleSheet("font-size: 11px; color: #888;")
        header_layout.addWidget(hint)
        header_layout.addStretch()
        main_layout.addWidget(header_frame)

        # =========================================
        # 設定エリア（コンパクト）
        # =========================================
        settings_frame = QFrame()
        settings_frame.setStyleSheet("background-color: #252526; border-bottom: 1px solid #3e3e42;")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(15, 10, 15, 10)
        settings_layout.setSpacing(8)

        # 条件設定行
        cond_row = QHBoxLayout()
        cond_row.setSpacing(15)

        lbl_size = QLabel("最小ファイルサイズ:")
        lbl_size.setStyleSheet("font-size: 12px;")
        cond_row.addWidget(lbl_size)
        spin_style = """
            QSpinBox {
                background-color: #1e1e1e; border: 1px solid #3e3e42;
                border-radius: 3px; padding: 2px 4px; color: #e0e0e0;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                subcontrol-origin: border; width: 18px;
                background-color: #2d2d30; border: 1px solid #3e3e42;
            }
            QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 3px; }
            QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 3px; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #444; }
            QSpinBox::up-arrow { image: none; border-left: 4px solid transparent;
                border-right: 4px solid transparent; border-bottom: 5px solid #ccc;
                width: 0; height: 0; }
            QSpinBox::down-arrow { image: none; border-left: 4px solid transparent;
                border-right: 4px solid transparent; border-top: 5px solid #ccc;
                width: 0; height: 0; }
        """

        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 10000)
        self.size_spin.setValue(config.MIN_FILE_SIZE_THRESHOLD // 1024)
        self.size_spin.setSuffix(" KB")
        self.size_spin.setFixedWidth(110)
        self.size_spin.setFixedHeight(28)
        self.size_spin.setStyleSheet(spin_style)
        cond_row.addWidget(self.size_spin)

        cond_row.addSpacing(20)

        lbl_img = QLabel("最小画像サイズ:")
        lbl_img.setStyleSheet("font-size: 12px;")
        cond_row.addWidget(lbl_img)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 1000)
        self.width_spin.setValue(config.MIN_IMAGE_SIZE_THRESHOLD[0])
        self.width_spin.setSuffix(" px")
        self.width_spin.setFixedWidth(100)
        self.width_spin.setFixedHeight(28)
        self.width_spin.setStyleSheet(spin_style)
        cond_row.addWidget(self.width_spin)
        lbl_x = QLabel("×")
        lbl_x.setStyleSheet("font-size: 12px;")
        cond_row.addWidget(lbl_x)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(10, 1000)
        self.height_spin.setValue(config.MIN_IMAGE_SIZE_THRESHOLD[1])
        self.height_spin.setSuffix(" px")
        self.height_spin.setFixedWidth(100)
        self.height_spin.setFixedHeight(28)
        self.height_spin.setStyleSheet(spin_style)
        cond_row.addWidget(self.height_spin)

        cond_row.addStretch()

        self.btn_scan = QPushButton("🔍 スキャン開始")
        self.btn_scan.setFixedHeight(30)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet(
            "QPushButton { background-color: #007acc; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 0 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #0099ff; }"
            "QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_scan.clicked.connect(self.start_scan)
        cond_row.addWidget(self.btn_scan)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setFixedHeight(30)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #d83b01; color: white; "
            "border-radius: 4px; padding: 0 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #e84c1a; }"
            "QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)
        cond_row.addWidget(self.btn_stop)

        settings_layout.addLayout(cond_row)

        # プログレス + ステータス行
        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #1e1e1e; border-radius: 4px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 4px; }
        """)
        prog_row.addWidget(self.progress, 1)

        self.status_label = QLabel("準備完了")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.status_label.setMinimumWidth(180)
        prog_row.addWidget(self.status_label)
        settings_layout.addLayout(prog_row)

        main_layout.addWidget(settings_frame)

        # =========================================
        # メインコンテンツ（スプリッター）
        # =========================================
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 左: ファイルリスト ---
        list_panel = QWidget()
        list_panel.setMinimumWidth(350)
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(8, 8, 4, 8)
        list_layout.setSpacing(6)

        list_header = QLabel("検出されたファイル")
        list_header.setStyleSheet("font-weight: bold; font-size: 13px;")
        list_layout.addWidget(list_header)

        self.file_list_area = QScrollArea()
        self.file_list_area.setWidgetResizable(True)
        self.file_list_area.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px; }")
        self.file_list_container = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_container)
        self.file_list_layout.setContentsMargins(4, 4, 4, 4)
        self.file_list_layout.setSpacing(4)
        self.file_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.file_list_area.setWidget(self.file_list_container)
        list_layout.addWidget(self.file_list_area, 1)

        # 選択操作バー
        select_layout = QHBoxLayout()
        select_layout.setContentsMargins(0, 0, 0, 0)

        btn_select_all = QPushButton("全選択")
        btn_select_all.setFixedHeight(28)
        btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_select_all.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: 1px solid #555; "
            "border-radius: 4px; padding: 2px 12px; font-size: 11px; }"
            "QPushButton:hover { background-color: #444; }")
        btn_select_all.clicked.connect(self.select_all)
        select_layout.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("全解除")
        btn_deselect_all.setFixedHeight(28)
        btn_deselect_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_deselect_all.setStyleSheet(
            "QPushButton { background-color: #333; color: #ccc; border: 1px solid #555; "
            "border-radius: 4px; padding: 2px 12px; font-size: 11px; }"
            "QPushButton:hover { background-color: #444; }")
        btn_deselect_all.clicked.connect(self.deselect_all)
        select_layout.addWidget(btn_deselect_all)

        select_layout.addStretch()

        self.btn_delete = QPushButton("🗑️ 選択したファイルを削除")
        self.btn_delete.setFixedHeight(32)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setStyleSheet(
            "QPushButton { background-color: #d83b01; color: white; font-weight: bold; "
            "border-radius: 4px; padding: 0 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #e84c1a; }"
            "QPushButton:disabled { background-color: #444; color: #888; }")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected)
        select_layout.addWidget(self.btn_delete)

        list_layout.addLayout(select_layout)

        self.splitter.addWidget(list_panel)

        # --- 右: プレビュー ---
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

        self.preview_image = QLabel("ファイルを選択してください")
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
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([600, 300])

        main_layout.addWidget(self.splitter, 1)

    def start_scan(self):
        """スキャンを開始"""
        if self.scanner and self.scanner.isRunning():
            return

        # 設定を取得
        min_file_size = self.size_spin.value() * 1024  # KB to bytes
        min_width = self.width_spin.value()
        min_height = self.height_spin.value()

        # UIをリセット
        self.found_files = []
        self.selected_files.clear()
        self.clear_file_list()
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_delete.setEnabled(False)
        self.progress.setValue(0)

        # スキャナーを開始
        self.scanner = SmallFileScanner(self.db, min_file_size, min_width, min_height)
        self.scanner.progress.connect(self.on_progress)
        self.scanner.status.connect(self.status_label.setText)
        self.scanner.file_found.connect(self.on_file_found)
        self.scanner.finished.connect(self.on_scan_finished)
        self.scanner.start()

    def stop_scan(self):
        """スキャンを停止"""
        if self.scanner and self.scanner.isRunning():
            self.scanner.stop()
            self.scanner.wait()
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def on_progress(self, current, total):
        """プログレス更新"""
        if total > 0:
            self.progress.setValue(int((current / total) * 100))

    def on_file_found(self, file_data):
        """ファイルが見つかったときの処理"""
        self.found_files.append(file_data)
        self.add_file_item(file_data)

    def on_scan_finished(self, files):
        """スキャン完了時の処理"""
        self.found_files = files
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status_label.setText(f"スキャン完了: {len(files)} ファイルが見つかりました")

    def add_file_item(self, file_data):
        """ファイルアイテムを追加"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: #2d2d30; border: 1px solid #3e3e42; border-radius: 4px; padding: 8px; }
            QFrame:hover { border-color: #007acc; }
        """)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        checkbox = QCheckBox()
        checkbox.setChecked(True)  # デフォルトで選択
        checkbox.stateChanged.connect(lambda state, fid=file_data['id']: self.on_checkbox_changed(fid, state))
        self.selected_files.add(file_data['id'])
        layout.addWidget(checkbox)

        info_layout = QVBoxLayout()
        name_label = QLabel(os.path.basename(file_data['path']))
        name_label.setStyleSheet("font-weight: bold; color: #fff;")
        info_layout.addWidget(name_label)

        size_text = f"ファイルサイズ: {format_file_size(file_data['file_size'])}"
        if file_data['image_width'] and file_data['image_height']:
            size_text += f" | 画像サイズ: {file_data['image_width']} × {file_data['image_height']} px"
        size_label = QLabel(size_text)
        size_label.setStyleSheet("color: #aaa; font-size: 11px;")
        info_layout.addWidget(size_label)

        layout.addLayout(info_layout, stretch=1)

        # クリックでプレビュー、ダブルクリックでビューアー
        def show_preview():
            self.show_file_preview(file_data)
        frame.mousePressEvent = lambda e: show_preview() if e.button() == Qt.MouseButton.LeftButton else None
        frame.mouseDoubleClickEvent = lambda e: open_file_in_viewer(file_data['path'])
        frame.setCursor(Qt.CursorShape.PointingHandCursor)

        self.file_list_layout.addWidget(frame)

    def on_checkbox_changed(self, file_id, state):
        """チェックボックスの状態変更"""
        if state == Qt.CheckState.Checked.value:
            self.selected_files.add(file_id)
        else:
            self.selected_files.discard(file_id)
        self.btn_delete.setEnabled(len(self.selected_files) > 0)

    def select_all(self):
        """全選択"""
        for i in range(self.file_list_layout.count()):
            item = self.file_list_layout.itemAt(i)
            if item and item.widget():
                checkbox = item.widget().findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(True)

    def deselect_all(self):
        """全解除"""
        for i in range(self.file_list_layout.count()):
            item = self.file_list_layout.itemAt(i)
            if item and item.widget():
                checkbox = item.widget().findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(False)

    def show_file_preview(self, file_data):
        """ファイルプレビューを表示（共通API・縦横比保持）"""
        pix = get_preview(file_data['path'])
        panel_w = self.preview_panel.width() - 30  # パネル幅からマージン分を引く
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

        # 情報を表示
        info_lines = []
        info_lines.append(f"<b>ファイル名:</b> {os.path.basename(file_data['path'])}")
        info_lines.append(f"<b>パス:</b> {file_data['path']}")
        info_lines.append(f"<b>ファイルサイズ:</b> {format_file_size(file_data['file_size'])}")
        if file_data['image_width'] and file_data['image_height']:
            info_lines.append(f"<b>画像サイズ:</b> {file_data['image_width']} × {file_data['image_height']} px")
        if file_data['is_small_image']:
            info_lines.append("<b style='color: #d83b01;'>⚠ 小さい画像</b>")

        self.preview_info.setText("<br>".join(info_lines))

    def delete_selected(self):
        """選択したファイルを削除"""
        if not self.selected_files:
            return

        reply = QMessageBox.question(
            self,
            "確認",
            f"{len(self.selected_files)} 個のファイルを削除しますか？\n\nこの操作は取り消せません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            failed_count = 0
            for file_data in self.found_files:
                if file_data['id'] in self.selected_files:
                    if self.db.move_to_trash(file_data['id']):
                        deleted_count += 1
                        # UIから削除
                        for i in range(self.file_list_layout.count()):
                            item = self.file_list_layout.itemAt(i)
                            if item and item.widget():
                                widget = item.widget()
                                checkbox = widget.findChild(QCheckBox)
                                if checkbox and file_data['id'] in [f['id'] for f in self.found_files if f['id'] == file_data['id']]:
                                    widget.deleteLater()
                                    break
                    else:
                        failed_count += 1

            if failed_count > 0:
                QMessageBox.warning(self, "削除失敗",
                                    f"{deleted_count} 個を削除しましたが、{failed_count} 個の削除に失敗しました。\nログを確認してください。")
            else:
                QMessageBox.information(self, "完了", f"{deleted_count} 個のファイルを削除しました")
            
            # リストを更新
            self.found_files = [f for f in self.found_files if f['id'] not in self.selected_files]
            self.selected_files.clear()
            self.clear_file_list()
            for file_data in self.found_files:
                self.add_file_item(file_data)

    def clear_file_list(self):
        """ファイルリストをクリア"""
        while self.file_list_layout.count():
            item = self.file_list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

