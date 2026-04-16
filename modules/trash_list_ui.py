"""
削除済みファイル一覧UI
ゴミ箱に隔離されたファイルの一覧表示・復元・完全削除
"""
import os
import logging
import platform
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QAbstractItemView, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt

from src.database import DatabaseManager
from src.config import config

logger = logging.getLogger(__name__)


class TrashListPage(QWidget):
    """削除済みファイル一覧ページ"""

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; }
            QTableWidget { background-color: #252526; border: 1px solid #3e3e42; gridline-color: #3e3e42; }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:selected { background-color: #007acc; color: white; }
            QHeaderView::section { background-color: #2d2d30; color: #ccc; padding: 8px; border: none; }
            QPushButton { background-color: #2d2d30; border: 1px solid #3e3e42; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #3e3e42; border-color: #007acc; }
            QPushButton:disabled { color: #666; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("🗑️ 削除済みファイル一覧")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #fff; margin-bottom: 10px;")
        layout.addWidget(header)

        retention_note = ""
        if config.ENFORCE_TRASH_RETENTION_BEFORE_PERMANENT_DELETE:
            retention_note = (
                f"\n\n完全削除は、ゴミ箱に移してから {config.TRASH_RETENTION_DAYS} 日経過後にのみ可能です。"
                f"（日数・無効化は src/config.py の TRASH_RETENTION_DAYS 等で変更できます）"
            )
        desc = QLabel(
            "ゴミ箱フォルダに隔離されたファイルです。復元するか、DBから削除するか、期間経過後に完全削除できます。"
            + retention_note
        )
        desc.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 一覧を更新")
        self.btn_refresh.clicked.connect(self.load_list)
        btn_row.addWidget(self.btn_refresh)
        self.btn_open_trash = QPushButton("📂 ゴミ箱フォルダを開く")
        self.btn_open_trash.clicked.connect(self._open_trash_folder)
        btn_row.addWidget(self.btn_open_trash)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ファイル名", "保存場所", "削除日時", "復元", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def load_list(self):
        """削除済み一覧を再取得して表示"""
        rows = self.db.get_trash_files()
        self.table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            fid, path, mtime, filename = row[0], row[1], row[2], row[3]
            self.table.setItem(i, 0, QTableWidgetItem(filename))
            self.table.setItem(i, 1, QTableWidgetItem(path))
            try:
                dt = datetime.fromtimestamp(mtime) if mtime else None
                date_str = dt.strftime("%Y-%m-%d %H:%M") if dt else "—"
            except (OSError, ValueError):
                date_str = "—"
            self.table.setItem(i, 2, QTableWidgetItem(date_str))

            # 復元ボタン
            btn_restore = QPushButton("復元")
            btn_restore.setProperty("fid", fid)
            btn_restore.setProperty("path", path)
            btn_restore.clicked.connect(self._on_restore)
            self.table.setCellWidget(i, 3, btn_restore)

            # 操作ボタン（DBから削除 / 完全削除）
            op_widget = QWidget()
            op_layout = QHBoxLayout(op_widget)
            op_layout.setContentsMargins(2, 2, 2, 2)
            op_layout.setSpacing(4)

            btn_db_only = QPushButton("DBから削除")
            btn_db_only.setProperty("fid", fid)
            btn_db_only.setProperty("path", path)
            btn_db_only.setToolTip("DBのレコードのみ削除します。ファイルはゴミ箱に残ります。")
            btn_db_only.clicked.connect(self._on_remove_from_db)
            op_layout.addWidget(btn_db_only)

            btn_permanent = QPushButton("完全に削除")
            btn_permanent.setProperty("fid", fid)
            btn_permanent.setStyleSheet("background-color: #5a1e1e; color: #ff8888;")
            block_reason = self.db.permanent_delete_blocked_reason(fid)
            if block_reason:
                btn_permanent.setEnabled(False)
                btn_permanent.setToolTip(block_reason)
            else:
                btn_permanent.setToolTip(
                    "ファイルをディスクから削除し、DBからも削除します。取り消せません。"
                )
            btn_permanent.clicked.connect(self._on_permanent_delete)
            op_layout.addWidget(btn_permanent)

            self.table.setCellWidget(i, 4, op_widget)

        if not rows:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("削除済みファイルはありません"))
            self.table.setSpan(0, 0, 1, 5)

    def _open_trash_folder(self):
        """ゴミ箱フォルダをエクスプローラーで開く"""
        trash_dir = self.db.get_trash_folder()
        if not trash_dir:
            root = self.db.get_setting("root_path")
            if root and os.path.exists(root):
                trash_dir = os.path.join(root, config.TRASH_FOLDER_NAME)
            else:
                trash_dir = config.get_default_trash_folder()
        if not os.path.exists(trash_dir):
            QMessageBox.information(self, "情報", f"ゴミ箱フォルダがまだありません:\n{trash_dir}")
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", os.path.normpath(trash_dir)], check=False)
            elif platform.system() == "Darwin":
                subprocess.run(["open", trash_dir], check=False)
            else:
                subprocess.run(["xdg-open", trash_dir], check=False)
        except Exception as e:
            logger.error(f"Failed to open trash folder: {e}")
            QMessageBox.warning(self, "エラー", f"フォルダを開けませんでした:\n{e}")

    def _on_restore(self):
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        fid = sender.property("fid")
        path = sender.property("path")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "復元", "ファイルが見つかりません。")
            return
        dest = QFileDialog.getExistingDirectory(self, "復元先フォルダを選択", os.path.dirname(path))
        if not dest:
            return
        if not config.validate_path(dest):
            QMessageBox.warning(self, "エラー", "無効なフォルダです。")
            return
        if self.db.move_file_to_folder(fid, path, dest):
            QMessageBox.information(self, "復元", "ファイルを復元しました。")
            self.load_list()
        else:
            QMessageBox.warning(self, "復元失敗", "復元に失敗しました。")

    def _on_remove_from_db(self):
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        fid = sender.property("fid")
        if QMessageBox.question(
            self, "確認",
            "DBからこのレコードを削除します。\nファイルはゴミ箱フォルダに残ります。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.db.delete_file_record(fid):
            QMessageBox.information(self, "完了", "DBから削除しました。")
            self.load_list()
        else:
            QMessageBox.warning(self, "エラー", "削除に失敗しました。")

    def _on_permanent_delete(self):
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        fid = sender.property("fid")
        block = self.db.permanent_delete_blocked_reason(fid)
        if block:
            QMessageBox.information(self, "完全削除", block)
            return
        if QMessageBox.critical(
            self, "完全削除の確認",
            "ファイルをディスクから削除し、DBからも削除します。\nこの操作は取り消せません。よろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.db.permanently_delete_file(fid):
            QMessageBox.information(self, "完了", "完全に削除しました。")
            self.load_list()
        else:
            QMessageBox.warning(
                self,
                "エラー",
                "削除に失敗しました。退避期間中の可能性があります。一覧を更新して再度お試しください。",
            )
