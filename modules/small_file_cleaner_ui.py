"""
小さいファイル削除UIモジュール
極端に小さいファイル（サムネイルなど）を検出して削除
"""
import sys
import os
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFileDialog, QFrame, QScrollArea, QProgressBar,
                             QMessageBox, QCheckBox, QSpinBox, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import get_db_thumbnail, setup_logging, DatabaseManager, get_file_info, format_file_size
from config import config

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
            with self.db.lock:
                rows = self.db.conn.execute(
                    "SELECT id, path, size FROM files WHERE status != 'trash'"
                ).fetchall()
            
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
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QLabel { font-size: 13px; }
            QPushButton {
                background-color: #2d2d30; border: 1px solid #3e3e42; color: #e0e0e0;
                padding: 8px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #3e3e42; border-color: #007acc; }
            QPushButton:disabled { background-color: #1a1a1a; color: #666; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # ヘッダー
        header = QHBoxLayout()
        title = QLabel("🗑️ 小さいファイル削除")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff;")
        header.addWidget(title)
        header.addStretch()
        main_layout.addLayout(header)

        # 設定エリア
        settings_frame = QFrame()
        settings_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 15px;")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setSpacing(10)

        settings_layout.addWidget(QLabel("削除条件設定"))

        # ファイルサイズ設定
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("最小ファイルサイズ:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 10000)  # KB単位
        self.size_spin.setValue(config.MIN_FILE_SIZE_THRESHOLD // 1024)
        self.size_spin.setSuffix(" KB")
        size_layout.addWidget(self.size_spin)
        size_layout.addStretch()
        settings_layout.addLayout(size_layout)

        # 画像サイズ設定
        image_size_layout = QHBoxLayout()
        image_size_layout.addWidget(QLabel("最小画像サイズ:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 1000)
        self.width_spin.setValue(config.MIN_IMAGE_SIZE_THRESHOLD[0])
        self.width_spin.setSuffix(" px")
        image_size_layout.addWidget(self.width_spin)
        image_size_layout.addWidget(QLabel("×"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(10, 1000)
        self.height_spin.setValue(config.MIN_IMAGE_SIZE_THRESHOLD[1])
        self.height_spin.setSuffix(" px")
        image_size_layout.addWidget(self.height_spin)
        image_size_layout.addStretch()
        settings_layout.addLayout(image_size_layout)

        # スキャンボタン
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("🔍 スキャン開始")
        self.btn_scan.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 10px;")
        self.btn_scan.clicked.connect(self.start_scan)
        btn_layout.addWidget(self.btn_scan)
        
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setStyleSheet("background-color: #d83b01; color: white; padding: 10px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)
        btn_layout.addWidget(self.btn_stop)
        
        settings_layout.addLayout(btn_layout)

        # プログレスバー
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        settings_layout.addWidget(self.progress)

        # ステータスラベル
        self.status_label = QLabel("準備完了")
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        settings_layout.addWidget(self.status_label)

        main_layout.addWidget(settings_frame)

        # 結果エリア（スプリッター）
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左側: ファイルリスト
        list_panel = QFrame()
        list_panel.setStyleSheet("background-color: #252526; border-radius: 6px;")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(10)

        list_layout.addWidget(QLabel("検出されたファイル"))
        
        self.file_list_area = QScrollArea()
        self.file_list_area.setWidgetResizable(True)
        self.file_list_container = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_container)
        self.file_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.file_list_area.setWidget(self.file_list_container)
        list_layout.addWidget(self.file_list_area)

        # 選択操作ボタン
        select_layout = QHBoxLayout()
        btn_select_all = QPushButton("全選択")
        btn_select_all.clicked.connect(self.select_all)
        select_layout.addWidget(btn_select_all)
        
        btn_deselect_all = QPushButton("全解除")
        btn_deselect_all.clicked.connect(self.deselect_all)
        select_layout.addWidget(btn_deselect_all)
        
        select_layout.addStretch()
        
        self.btn_delete = QPushButton("🗑️ 選択したファイルを削除")
        self.btn_delete.setStyleSheet("background-color: #d83b01; color: white; font-weight: bold; padding: 10px;")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected)
        select_layout.addWidget(self.btn_delete)
        
        list_layout.addLayout(select_layout)

        # 右側: プレビュー
        preview_panel = QFrame()
        preview_panel.setFixedWidth(350)
        preview_panel.setStyleSheet("background-color: #252526; border-radius: 6px;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(15)

        preview_layout.addWidget(QLabel("プレビュー"))

        self.preview_image = QLabel("ファイルを選択してください")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setFixedSize(320, 320)
        self.preview_image.setStyleSheet("background-color: #1e1e1e; border: 1px solid #3e3e42; border-radius: 4px;")
        self.preview_image.setScaledContents(True)
        preview_layout.addWidget(self.preview_image)

        self.preview_info = QLabel("")
        self.preview_info.setStyleSheet("color: #aaa; font-size: 12px;")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)

        preview_layout.addStretch()

        splitter.addWidget(list_panel)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        main_layout.addWidget(splitter)

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

        # クリックでプレビュー
        def show_preview():
            self.show_file_preview(file_data)
        frame.mousePressEvent = lambda e: show_preview() if e.button() == Qt.MouseButton.LeftButton else None

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
        """ファイルプレビューを表示"""
        # 画像を表示
        pix = get_db_thumbnail(self.db, file_data['id'], file_data['path'], 300)
        self.preview_image.setPixmap(pix)

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

