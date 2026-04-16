import sys
import os
import time
import traceback
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QStackedWidget, QProgressBar, QFrame, QMessageBox,
                             QDialog, QSizePolicy, QScrollArea)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QPixmap, QColor

# --- クラッシュ対策 ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["QT_LOGGING_RULES"] = "qt.gui.icc=false"

sys.stdout.reconfigure(encoding='utf-8')

# GUI Components
from gui.splash import SplashScreen
from gui.workers import AppLoader, DBResetWorker
from gui.models import PhotoModel
from gui.gallery_page import GalleryPage
from gui.icons import (get_icon, get_pixmap, icon_app_brand, icon_hero,
                       icon_clock)
from src.theme import Theme

# Global placeholders for lazy loaded modules
DatabaseManager = None
ScannerThread = None
AnalyzerThread = None
ImageLoader = None
setup_logging = None
config = None
DuplicatePage = None
BlurPage = None
SimilarityPage = None
SorterPage = None
ManualSorterPage = None
SmallFileCleanerPage = None
TrashListPage = None


def _canonical_folder_path(path: str) -> str:
    if not path or not path.strip():
        return ""
    try:
        resolved = Path(path).resolve()
        normalized = os.path.normpath(str(resolved))
    except (OSError, RuntimeError):
        normalized = os.path.normpath(path)
    return os.path.normcase(normalized)


# ── ClickableCard ────────────────────────────────────────────────────────────

class ClickableCard(QFrame):
    """クリック可能なカードウィジェット（シグナル付き QFrame）"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


# ── MainWindow ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhotoSortX")
        width, height = config.DEFAULT_WINDOW_SIZE
        self.resize(width, height)
        self.setStyleSheet(Theme.app_qss())

        self.db = DatabaseManager()
        self.scanner = None
        self.analyzer = None
        self.reset_worker = None
        self._nav_buttons: list[QPushButton] = []

        container = QWidget()
        self.setCentralWidget(container)
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(config.SIDEBAR_WIDTH)
        sidebar.setStyleSheet(f"""
            QFrame#sidebar {{
                background-color: {Theme.BG_SIDEBAR};
                border-right: 1px solid {Theme.BORDER};
            }}
        """)
        side_vbox = QVBoxLayout(sidebar)
        side_vbox.setContentsMargins(0, 0, 0, 0)
        side_vbox.setSpacing(0)

        # ── Brand header ─────────────────────────────────────────────────────
        brand_w = QWidget()
        brand_w.setFixedHeight(56)
        brand_w.setStyleSheet(f"background: {Theme.BG_SIDEBAR}; border-bottom: 1px solid {Theme.BORDER};")
        brand_h = QHBoxLayout(brand_w)
        brand_h.setContentsMargins(14, 0, 14, 0)
        brand_h.setSpacing(10)

        brand_icon_lbl = QLabel()
        brand_icon_lbl.setPixmap(icon_app_brand(28))
        brand_icon_lbl.setFixedSize(28, 28)

        brand_name_lbl = QLabel("PhotoSortX")
        brand_name_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Theme.TEXT_PRIMARY};"
            " background: transparent; border: none;"
        )

        brand_ver_lbl = QLabel("v2.3")
        brand_ver_lbl.setStyleSheet(
            f"font-size: 10px; color: {Theme.TEXT_SECTION}; background: transparent; border: none;"
        )
        brand_ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        brand_h.addWidget(brand_icon_lbl)
        brand_h.addWidget(brand_name_lbl)
        brand_h.addStretch()
        brand_h.addWidget(brand_ver_lbl)
        side_vbox.addWidget(brand_w)

        # ── Nav area ─────────────────────────────────────────────────────────
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nav_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        nav_inner = QWidget()
        nav_inner.setStyleSheet(f"background: {Theme.BG_SIDEBAR};")
        nav_vbox = QVBoxLayout(nav_inner)
        nav_vbox.setContentsMargins(8, 10, 8, 10)
        nav_vbox.setSpacing(1)

        # ── helper closures ──────────────────────────────────────────────────
        def section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {Theme.TEXT_SECTION}; font-size: 10px; font-weight: bold;"
                " padding: 14px 8px 4px 8px; background: transparent; border: none;"
            )
            return lbl

        def nav_btn(icon_name: str, label: str, tooltip: str,
                    handler, icon_size: int = 15) -> QPushButton:
            btn = QPushButton(f"  {label}")
            btn.setIcon(get_icon(icon_name, icon_size, Theme.TEXT_SECONDARY))
            btn.setIconSize(QSize(icon_size, icon_size))
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(Theme.nav_normal())
            # Store icon pairs (normal, active) for color swap
            btn._icon_name = icon_name
            btn._icon_size = icon_size
            self._nav_buttons.append(btn)

            def _on_click():
                self._set_active_nav(btn)
                handler()
            btn.clicked.connect(_on_click)
            return btn

        # ── LIBRARY section ──────────────────────────────────────────────────
        nav_vbox.addWidget(section_label("LIBRARY"))

        self.btn_nav_home = nav_btn(
            "home", "Home", "進捗・メッセージの表示",
            lambda: self.stack.setCurrentIndex(0)
        )
        self.btn_nav_gallery = nav_btn(
            "gallery", "Gallery", "ライブラリの一覧表示",
            self.show_gallery
        )

        # 取込・解析（アクティブ追跡なし・ダイアログ起動）
        self.btn_step0 = QPushButton("  Import")
        self.btn_step0.setIcon(get_icon("import", 15, Theme.TEXT_SECONDARY))
        self.btn_step0.setIconSize(QSize(15, 15))
        self.btn_step0.setToolTip("取込（フル／差分）と解析（全件／差分）を選びます")
        self.btn_step0.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_step0.setFixedHeight(36)
        self.btn_step0.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_step0.setStyleSheet(Theme.nav_normal())
        self.btn_step0.clicked.connect(self.open_step0_dialog)

        nav_vbox.addWidget(self.btn_nav_home)
        nav_vbox.addWidget(self.btn_nav_gallery)
        nav_vbox.addWidget(self.btn_step0)

        # ── CLEAN UP section ─────────────────────────────────────────────────
        nav_vbox.addWidget(section_label("CLEAN UP"))

        self.btn_nav_dup = nav_btn(
            "duplicate", "Duplicates", "完全に同じ画像のコピーを検出・削除",
            self.show_duplicate_page
        )
        self.btn_nav_blur = nav_btn(
            "blur", "Blurry photos", "ブレ・撮影ミスを検出・削除",
            self.show_blur_page
        )
        self.btn_nav_small = nav_btn(
            "tiny_file", "Tiny files", "サムネサイズ級の不要ファイルを除去",
            self.show_small_file_cleaner_page
        )
        self.btn_nav_sim = nav_btn(
            "similar", "Similar groups", "激似・連写をまとめて確認",
            self.show_similarity_page
        )
        self.btn_nav_manual = nav_btn(
            "manual_sort", "Manual sort", "残す／捨てる・フォルダ分けなど最終仕分け",
            self.show_manual_sorter_page
        )

        nav_vbox.addWidget(self.btn_nav_dup)
        nav_vbox.addWidget(self.btn_nav_blur)
        nav_vbox.addWidget(self.btn_nav_small)
        nav_vbox.addWidget(self.btn_nav_sim)
        nav_vbox.addWidget(self.btn_nav_manual)

        # ── SMART section ────────────────────────────────────────────────────
        nav_vbox.addWidget(section_label("SMART"))

        self.btn_nav_sort = nav_btn(
            "ai", "AI organize", "CLIPを使った意味的なスマート整理",
            self.show_sorter_page
        )
        nav_vbox.addWidget(self.btn_nav_sort)

        nav_vbox.addStretch()
        nav_scroll.setWidget(nav_inner)
        side_vbox.addWidget(nav_scroll, 1)

        # ── Footer ───────────────────────────────────────────────────────────
        footer_w = QWidget()
        footer_w.setStyleSheet(
            f"background: {Theme.BG_SIDEBAR}; border-top: 1px solid {Theme.BORDER};"
        )
        footer_h = QHBoxLayout(footer_w)
        footer_h.setContentsMargins(16, 10, 10, 10)
        footer_h.setSpacing(4)

        self.lbl_lib_info = QLabel("—")
        self.lbl_lib_info.setStyleSheet(
            f"font-size: 12px; color: {Theme.TEXT_MUTED}; background: transparent; border: none;"
        )

        btn_trash_icon = QPushButton()
        btn_trash_icon.setIcon(get_icon("trash", 15, Theme.TEXT_SECTION))
        btn_trash_icon.setIconSize(QSize(15, 15))
        btn_trash_icon.setFixedSize(30, 30)
        btn_trash_icon.setToolTip("削除済みファイルの一覧")
        btn_trash_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_trash_icon.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {Theme.BG_HOVER}; }}
        """)
        btn_trash_icon.clicked.connect(lambda: [
            self._set_active_nav(None), self.show_trash_list_page()
        ])

        btn_settings_icon = QPushButton()
        btn_settings_icon.setIcon(get_icon("settings", 15, Theme.TEXT_SECTION))
        btn_settings_icon.setIconSize(QSize(15, 15))
        btn_settings_icon.setFixedSize(30, 30)
        btn_settings_icon.setToolTip("設定")
        btn_settings_icon.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings_icon.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {Theme.BG_HOVER}; }}
        """)
        btn_settings_icon.clicked.connect(self._open_settings_dialog)

        footer_h.addWidget(self.lbl_lib_info)
        footer_h.addStretch()
        footer_h.addWidget(btn_trash_icon)
        footer_h.addWidget(btn_settings_icon)
        side_vbox.addWidget(footer_w)

        # ── Stack ────────────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background-color: {Theme.BG_APP};")

        # ── Home page ────────────────────────────────────────────────────────
        home_page = QWidget()
        home_page.setStyleSheet(f"background: {Theme.BG_APP};")
        home_vbox = QVBoxLayout(home_page)
        home_vbox.setContentsMargins(0, 0, 0, 0)
        home_vbox.setSpacing(0)

        # Center scrollable area
        center_w = QWidget()
        center_w.setStyleSheet(f"background: {Theme.BG_APP};")
        center_vbox = QVBoxLayout(center_w)
        center_vbox.setContentsMargins(60, 0, 60, 0)
        center_vbox.setSpacing(0)
        center_vbox.addStretch(2)

        # Hero icon
        hero_lbl = QLabel()
        hero_lbl.setPixmap(icon_hero(80))
        hero_lbl.setFixedSize(80, 80)
        hero_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_vbox.addWidget(hero_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        center_vbox.addSpacing(20)

        # Title
        title_lbl = QLabel("Welcome to PhotoSortX")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: bold; color: {Theme.TEXT_PRIMARY};"
            " background: transparent; border: none;"
        )
        center_vbox.addWidget(title_lbl)
        center_vbox.addSpacing(8)

        # Subtitle
        subtitle_lbl = QLabel(
            "AIと従来手法を組み合わせた写真整理ツール。はじめに写真を取込むか、\n既存ライブラリを解析してください。"
        )
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet(
            f"font-size: 13px; color: {Theme.TEXT_MUTED}; background: transparent; border: none;"
        )
        center_vbox.addWidget(subtitle_lbl)
        center_vbox.addSpacing(32)

        # ── CTA cards ─────────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        cards_row.addStretch()

        # Left card: 写真を取込む
        card_import = ClickableCard()
        card_import.setFixedSize(230, 130)
        card_import.setCursor(Qt.CursorShape.PointingHandCursor)
        card_import.setStyleSheet(f"""
            ClickableCard {{
                background: {Theme.BG_CARD};
                border: 1.5px solid {Theme.ACCENT};
                border-radius: 10px;
            }}
            ClickableCard:hover {{
                background: #2e2e2e;
            }}
        """)
        card_import.clicked.connect(self.open_step0_dialog)

        ci_vbox = QVBoxLayout(card_import)
        ci_vbox.setContentsMargins(16, 14, 16, 14)
        ci_vbox.setSpacing(6)

        ci_icon_lbl = QLabel()
        ci_icon_lbl.setPixmap(get_pixmap("import", 20, "white"))
        ci_icon_cont = QLabel()
        ci_icon_cont.setFixedSize(38, 38)
        ci_icon_cont.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ci_icon_cont.setStyleSheet(
            f"background: {Theme.ACCENT}; border-radius: 8px; border: none;"
        )
        ci_icon_inner = QLabel(ci_icon_cont)
        ci_icon_inner.setPixmap(get_pixmap("import", 18, "white"))
        ci_icon_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ci_icon_inner.setGeometry(0, 0, 38, 38)
        ci_icon_inner.setStyleSheet("background: transparent; border: none;")

        ci_title = QLabel("写真を取込む")
        ci_title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Theme.TEXT_PRIMARY};"
            " background: transparent; border: none;"
        )
        ci_sub = QLabel("フォルダを選んで新しく取込み")
        ci_sub.setStyleSheet(
            f"font-size: 11px; color: {Theme.TEXT_MUTED}; background: transparent; border: none;"
        )

        ci_vbox.addWidget(ci_icon_cont)
        ci_vbox.addWidget(ci_title)
        ci_vbox.addWidget(ci_sub)
        ci_vbox.addStretch()

        # Right card: ライブラリを解析
        card_analyze = ClickableCard()
        card_analyze.setFixedSize(230, 130)
        card_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        card_analyze.setStyleSheet(f"""
            ClickableCard {{
                background: {Theme.BG_CARD};
                border: 1px solid {Theme.BORDER_LIGHT};
                border-radius: 10px;
            }}
            ClickableCard:hover {{
                background: #2e2e2e;
                border-color: {Theme.ACCENT};
            }}
        """)
        card_analyze.clicked.connect(self.start_diff_analyze)

        ca_vbox = QVBoxLayout(card_analyze)
        ca_vbox.setContentsMargins(16, 14, 16, 14)
        ca_vbox.setSpacing(6)

        ca_icon_cont = QLabel()
        ca_icon_cont.setFixedSize(38, 38)
        ca_icon_cont.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ca_icon_cont.setStyleSheet(
            f"background: {Theme.BG_HOVER}; border-radius: 8px; border: none;"
        )
        ca_icon_inner = QLabel(ca_icon_cont)
        ca_icon_inner.setPixmap(get_pixmap("refresh", 18, Theme.TEXT_SECONDARY))
        ca_icon_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ca_icon_inner.setGeometry(0, 0, 38, 38)
        ca_icon_inner.setStyleSheet("background: transparent; border: none;")

        ca_title = QLabel("ライブラリを解析")
        ca_title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Theme.TEXT_PRIMARY};"
            " background: transparent; border: none;"
        )
        self.ca_sub = QLabel("枚数を確認中...")
        self.ca_sub.setStyleSheet(
            f"font-size: 11px; color: {Theme.TEXT_MUTED}; background: transparent; border: none;"
        )

        ca_vbox.addWidget(ca_icon_cont)
        ca_vbox.addWidget(ca_title)
        ca_vbox.addWidget(self.ca_sub)
        ca_vbox.addStretch()

        cards_row.addWidget(card_import)
        cards_row.addWidget(card_analyze)
        cards_row.addStretch()

        center_vbox.addLayout(cards_row)
        center_vbox.addSpacing(20)

        # "最終解析" info pill
        self.info_pill = QLabel()
        self.info_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_pill.setFixedHeight(30)
        self.info_pill.setStyleSheet(f"""
            QLabel {{
                background: {Theme.BG_CARD};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BORDER};
                border-radius: 15px;
                padding: 0 14px;
                font-size: 11px;
            }}
        """)
        center_vbox.addWidget(self.info_pill, 0, Qt.AlignmentFlag.AlignHCenter)

        center_vbox.addStretch(3)

        # ── Progress bar (bottom) ────────────────────────────────────────────
        prog_frame = QFrame()
        prog_frame.setFixedHeight(72)
        prog_frame.setStyleSheet(
            f"background: {Theme.BG_SIDEBAR}; border-top: 1px solid {Theme.BORDER_LIGHT};"
        )
        prog_vbox = QVBoxLayout(prog_frame)
        prog_vbox.setContentsMargins(32, 10, 32, 10)
        prog_vbox.setSpacing(8)

        self.lbl_status = QLabel("ライブラリを取込むか、既存データを解析してください")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"font-size: 13px; color: {Theme.TEXT_SECONDARY};"
            " background: transparent; border: none;"
        )

        # プログレス行: バー + パーセント表示
        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 3px;
                background: {Theme.BG_CARD};
            }}
            QProgressBar::chunk {{ background: {Theme.ACCENT}; border-radius: 3px; }}
        """)

        self.lbl_progress_pct = QLabel("")
        self.lbl_progress_pct.setFixedWidth(36)
        self.lbl_progress_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_progress_pct.setStyleSheet(
            f"font-size: 11px; color: {Theme.TEXT_MUTED}; background: transparent; border: none;"
        )

        prog_row.addWidget(self.progress_bar)
        prog_row.addWidget(self.lbl_progress_pct)

        prog_vbox.addWidget(self.lbl_status)
        prog_vbox.addLayout(prog_row)

        home_vbox.addWidget(center_w, 1)
        home_vbox.addWidget(prog_frame)

        self.stack.addWidget(home_page)           # index 0

        # Gallery
        self.gallery_page = GalleryPage(self.db)
        self.stack.addWidget(self.gallery_page)   # index 1

        # Feature modules
        self.duplicate_page = DuplicatePage(self.db)
        self.blur_page = BlurPage(self.db)
        self.sim_page = SimilarityPage(self.db)
        self.manual_sorter_page = ManualSorterPage(self.db)
        self.sorter_page = SorterPage(self.db)
        self.small_file_cleaner_page = SmallFileCleanerPage(self.db)
        self.trash_list_page = TrashListPage(self.db)

        self.stack.addWidget(self.duplicate_page)
        self.stack.addWidget(self.blur_page)
        self.stack.addWidget(self.sim_page)
        self.stack.addWidget(self.manual_sorter_page)
        self.stack.addWidget(self.sorter_page)
        self.stack.addWidget(self.small_file_cleaner_page)
        self.stack.addWidget(self.trash_list_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.stack)

        # Initial state
        self._set_active_nav(self.btn_nav_home)
        self.update_library_info()
        QTimer.singleShot(500, self.check_startup_sync)
        QTimer.singleShot(1000, self.check_trash_folder_setup)

    # ── Nav helpers ──────────────────────────────────────────────────────────

    def _set_active_nav(self, btn):
        """アクティブなnavボタンを更新（スタイル + アイコン色）"""
        for b in self._nav_buttons:
            b.setStyleSheet(Theme.nav_normal())
            if hasattr(b, '_icon_name'):
                b.setIcon(get_icon(b._icon_name, b._icon_size, Theme.TEXT_SECONDARY))
        if btn and btn in self._nav_buttons:
            btn.setStyleSheet(Theme.nav_active())
            if hasattr(btn, '_icon_name'):
                btn.setIcon(get_icon(btn._icon_name, btn._icon_size, Theme.TEXT_ACTIVE))

    # ── Home page helpers ─────────────────────────────────────────────────────

    def _refresh_home_page(self):
        """ホームページのCTAサブテキスト・ステータスピルを更新"""
        count = self.db.get_file_count()
        path = self.db.get_setting("root_path")
        folder_name = os.path.basename(path) if path else None

        if count > 0:
            self.ca_sub.setText(f"既存 {count:,} 枚を再解析")
        else:
            self.ca_sub.setText("取込後に解析できます")

        # 最終解析ピル
        if path and folder_name:
            try:
                db_path = config.DB_NAME
                if os.path.exists(db_path):
                    mtime = os.path.getmtime(db_path)
                    elapsed = time.time() - mtime
                    days = int(elapsed / 86400)
                    if days == 0:
                        when = "今日"
                    elif days == 1:
                        when = "1日前"
                    else:
                        when = f"{days}日前"
                    short_path = f".../{folder_name}"
                    self.info_pill.setText(f"  🕐  最終解析: {when} — {short_path}  ")
                    self.info_pill.setVisible(True)
                else:
                    self.info_pill.setVisible(False)
            except Exception:
                self.info_pill.setVisible(False)
        else:
            self.info_pill.setVisible(False)

    # ── Navigation ───────────────────────────────────────────────────────────

    def _step0_go_home(self):
        self.stack.setCurrentIndex(0)
        self._set_active_nav(self.btn_nav_home)

    def open_step0_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Import & Analyze")
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"""
            QDialog {{ background-color: {Theme.BG_CARD}; color: {Theme.TEXT_PRIMARY}; }}
            QLabel {{ color: #ccc; font-size: 13px; }}
            QPushButton {{
                background-color: #3a3a3a; color: {Theme.TEXT_PRIMARY};
                border: 1px solid #555; padding: 10px 12px;
                border-radius: 6px; font-size: 13px; text-align: left;
            }}
            QPushButton:hover {{ background-color: {Theme.ACCENT}; border-color: {Theme.ACCENT}; color: white; }}
            QPushButton#cancel {{ background: #333; color: #888; border-color: #444; }}
            QPushButton#cancel:hover {{ background: #3a3a3a; color: #ccc; }}
        """)
        sec_style = f"color: {Theme.ACCENT}; font-weight: bold; font-size: 12px; margin-top: 8px;"

        v = QVBoxLayout(dlg)
        v.setSpacing(8)
        v.setContentsMargins(18, 16, 18, 16)
        v.addWidget(QLabel("行う作業を選んでください。取込と解析は別の処理です。"))

        lbl_take = QLabel("【取込】ディスク上のフォルダとライブラリを同期")
        lbl_take.setStyleSheet(sec_style)
        v.addWidget(lbl_take)

        def _run(action: str):
            dlg.accept()
            self._step0_go_home()
            if action == "full_scan":
                self.start_scan()
            elif action == "diff_scan":
                self.start_diff_scan()
            elif action == "analyze":
                self.start_analyze()
            elif action == "diff_analyze":
                self.start_diff_analyze()

        b_full = QPushButton("フォルダを選んでフル取込\n（初回・別フォルダへ切り替え）")
        b_full.clicked.connect(lambda: _run("full_scan"))
        v.addWidget(b_full)

        b_diff = QPushButton("差分スキャン\n（前回スキャンしたフォルダの追加・削除だけ反映）")
        b_diff.clicked.connect(lambda: _run("diff_scan"))
        v.addWidget(b_diff)

        lbl_an = QLabel("【解析】取込済みファイルのハッシュ・ぼけ等を計算")
        lbl_an.setStyleSheet(sec_style)
        v.addWidget(lbl_an)

        b_an = QPushButton("詳細解析（全件）")
        b_an.clicked.connect(lambda: _run("analyze"))
        v.addWidget(b_an)

        b_dan = QPushButton("差分解析（未解析のファイルのみ）")
        b_dan.clicked.connect(lambda: _run("diff_analyze"))
        v.addWidget(b_dan)

        b_cancel = QPushButton("キャンセル")
        b_cancel.setObjectName("cancel")
        b_cancel.clicked.connect(dlg.reject)
        v.addWidget(b_cancel)

        dlg.exec()

    def _open_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(Theme.dialog_qss())

        v = QVBoxLayout(dlg)
        v.setSpacing(12)
        v.setContentsMargins(24, 20, 24, 20)

        # 削除フォルダ
        ht = QLabel("削除フォルダ")
        ht.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Theme.TEXT_PRIMARY}; border: none;"
        )
        v.addWidget(ht)

        current_trash = self.db.get_trash_folder() or config.get_default_trash_folder()
        trash_lbl = QLabel(f"現在: {current_trash}")
        trash_lbl.setWordWrap(True)
        trash_lbl.setStyleSheet(
            f"font-size: 11px; color: {Theme.TEXT_MUTED}; padding: 2px 0; border: none;"
        )
        v.addWidget(trash_lbl)

        btn_change = QPushButton("フォルダを変更...")
        btn_change.clicked.connect(lambda: [dlg.accept(), self.setup_trash_folder()])
        v.addWidget(btn_change)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {Theme.BORDER};")
        v.addWidget(sep)

        # 危険操作
        danger_title = QLabel("危険な操作")
        danger_title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {Theme.DANGER_TEXT}; border: none;"
        )
        v.addWidget(danger_title)

        danger_desc = QLabel(
            "以下の操作は元に戻せません。実際の画像ファイルは削除されませんが、\n解析データはすべて失われます。"
        )
        danger_desc.setStyleSheet(
            f"font-size: 12px; color: {Theme.TEXT_MUTED}; border: none;"
        )
        v.addWidget(danger_desc)

        self.btn_reset = QPushButton("⚠  DB全初期化")
        self.btn_reset.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.DANGER_BG}; color: {Theme.DANGER_TEXT};
                border: 1px solid {Theme.DANGER_BORDER};
                padding: 8px 16px; border-radius: 6px;
            }}
            QPushButton:hover {{ background: #4a2626; }}
        """)
        self.btn_reset.clicked.connect(lambda: [dlg.accept(), self.reset_db()])
        v.addWidget(self.btn_reset)

        v.addStretch()
        btn_close = QPushButton("閉じる")
        btn_close.clicked.connect(dlg.accept)
        v.addWidget(btn_close)

        dlg.exec()

    # ── Library info ─────────────────────────────────────────────────────────

    def update_library_info(self):
        count = self.db.get_file_count()
        if count == 0:
            self.lbl_lib_info.setText("No library")
        else:
            self.lbl_lib_info.setText(f"{count:,} photos")
        self._refresh_home_page()

    # ── Scan / Analyze ────────────────────────────────────────────────────────

    def check_startup_sync(self):
        root_path = self.db.get_setting("root_path")
        if root_path and os.path.exists(root_path):
            ans = QMessageBox.question(
                self, "同期確認",
                f"前回スキャンしたフォルダ:\n{root_path}\n\nライブラリと同期（差分更新）しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ans == QMessageBox.StandardButton.Yes:
                self.run_scanner(root_path)

    def start_scan(self):
        last_path = self.db.get_setting("root_path")
        folder = QFileDialog.getExistingDirectory(
            self, "スキャンフォルダ選択", last_path if last_path else ""
        )
        if not folder:
            return

        folder_canonical = _canonical_folder_path(folder)
        last_canonical = _canonical_folder_path(last_path) if last_path else ""
        is_different_folder = bool(last_canonical) and folder_canonical != last_canonical
        has_data_no_root = self.db.get_file_count() > 0 and not last_path

        if self.db.get_file_count() > 0:
            if has_data_no_root:
                ans = QMessageBox.question(
                    self, "ライブラリの置き換え",
                    "ライブラリに既存のデータがあります。\n\n"
                    "選択したフォルダでライブラリを置き換えますか？\n"
                    "（既存の全データがDBから削除され、今回のフォルダのみが登録されます）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return
                to_remove = set(self.db.get_all_files())
                if to_remove:
                    self.db.remove_files(to_remove)
            elif is_different_folder:
                ans = QMessageBox.question(
                    self, "別フォルダの選択",
                    "選択したフォルダは前回スキャンしたフォルダと異なります。\n\n"
                    "ライブラリをこのフォルダで置き換えますか？\n"
                    "（前回のフォルダのデータはDBから削除され、今回のフォルダのみが登録されます）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return
                from src.core import path_under_root
                all_paths = self.db.get_all_files()
                to_remove = {p for p in all_paths if path_under_root(p, last_path)}
                if to_remove:
                    self.db.remove_files(to_remove)
            else:
                ans = QMessageBox.question(
                    self, "更新確認",
                    f"ライブラリは既に存在します。\n\n選択したフォルダ: {os.path.basename(folder)}\n\n"
                    "このフォルダに対してライブラリを更新（同期）しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return

        self.run_scanner(folder)

    def _set_progress(self, value: int):
        """プログレスバーとパーセントラベルを同時に更新"""
        self.progress_bar.setValue(value)
        if value > 0:
            self.lbl_progress_pct.setText(f"{value}%")
        else:
            self.lbl_progress_pct.setText("")

    def run_scanner(self, folder):
        self.lock_buttons(True)
        self.scanner = ScannerThread(folder, self.db)
        self.scanner.progress.connect(self._set_progress)
        self.scanner.status.connect(self.lbl_status.setText)
        self.scanner.finished.connect(
            lambda: self.on_finished("スキャン完了！解析を行ってください")
        )
        self.scanner.start()

    def start_analyze(self):
        self.lock_buttons(True)
        self.analyzer = AnalyzerThread(self.db)
        self.analyzer.progress.connect(
            lambda c, t: self._set_progress(int(c / t * 100) if t else 0)
        )
        self.analyzer.status.connect(self.lbl_status.setText)
        self.analyzer.finished.connect(lambda: self.on_finished("解析完了"))
        self.analyzer.start()

    def start_diff_scan(self):
        root_path = self.db.get_setting("root_path")
        if not root_path or not os.path.exists(root_path):
            QMessageBox.warning(
                self, "エラー",
                "ルートパスが設定されていません。\n先にフル取込を実行してください。"
            )
            return
        self.run_scanner(root_path)

    def start_diff_analyze(self):
        unprocessed_count = self.db.get_unprocessed_count()
        if unprocessed_count == 0:
            QMessageBox.information(self, "情報", "解析対象のファイルがありません。")
            return
        ans = QMessageBox.question(
            self, "差分解析確認",
            f"未解析のファイルが {unprocessed_count} 件あります。\n\n解析を開始しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.start_analyze()

    def reset_db(self):
        ans = QMessageBox.question(
            self, '確認',
            "【本当に初期化しますか？】\n\n全ての解析データ、サムネイル、設定が削除されます。\n"
            "実際の画像ファイルは消えませんが、分類作業はリセットされます。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        import logging
        logging.getLogger(__name__).info("Main: Reset requested.")
        self.lbl_status.setText("初期化中... (応答なしになってもお待ちください)")
        self.lock_buttons(True)
        if hasattr(self, 'btn_reset'):
            self.btn_reset.setEnabled(False)

        self.reset_worker = DBResetWorker(self.db, self.scanner, self.analyzer)
        self.reset_worker.finished.connect(self.on_reset_finished)
        self.reset_worker.start()

    def _reset_status_style(self):
        """ステータスラベルの色をデフォルト（muted）に戻す"""
        self.lbl_status.setStyleSheet(
            f"font-size: 13px; color: {Theme.TEXT_SECONDARY};"
            " background: transparent; border: none;"
        )
        self.lbl_progress_pct.setText("")

    def on_reset_finished(self, msg):
        self.lbl_status.setText(msg)
        self.lock_buttons(False)
        self.update_library_info()
        QMessageBox.information(self, "完了", msg)

    def on_finished(self, msg):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(
            f"font-size: 13px; color: {Theme.TEXT_PRIMARY};"
            " background: transparent; border: none;"
        )
        self.lock_buttons(False)
        self._set_progress(100)
        self.update_library_info()
        # 3秒後にステータスをデフォルトの色に戻す
        QTimer.singleShot(3000, self._reset_status_style)

    def lock_buttons(self, locked):
        self.btn_step0.setEnabled(not locked)

    # ── Page navigation ───────────────────────────────────────────────────────

    def show_gallery(self):
        self.gallery_page.load_data()
        self.stack.setCurrentIndex(1)

    def show_duplicate_page(self):
        self.duplicate_page.load_data()
        self.stack.setCurrentWidget(self.duplicate_page)

    def show_blur_page(self):
        self.blur_page.load_data()
        self.stack.setCurrentWidget(self.blur_page)

    def show_similarity_page(self):
        self.stack.setCurrentWidget(self.sim_page)

    def show_manual_sorter_page(self):
        self.manual_sorter_page.refresh_source_list()
        self.stack.setCurrentWidget(self.manual_sorter_page)

    def show_sorter_page(self):
        self.stack.setCurrentWidget(self.sorter_page)

    def show_small_file_cleaner_page(self):
        self.stack.setCurrentWidget(self.small_file_cleaner_page)

    def show_trash_list_page(self):
        self.trash_list_page.load_list()
        self.stack.setCurrentWidget(self.trash_list_page)

    # ── Trash folder setup ────────────────────────────────────────────────────

    def check_trash_folder_setup(self):
        trash_folder = self.db.get_trash_folder()
        if not trash_folder:
            default_trash = config.get_default_trash_folder()
            ans = QMessageBox.question(
                self, "削除フォルダ設定",
                "削除フォルダが設定されていません。\n\n"
                f"デフォルト削除フォルダを作成しますか？\n\n場所: {default_trash}\n\n"
                "後で「設定」から変更できます。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(default_trash, exist_ok=True)
                    self.db.set_trash_folder(default_trash)
                    QMessageBox.information(
                        self, "設定完了",
                        f"削除フォルダを設定しました:\n{default_trash}"
                    )
                except Exception as e:
                    QMessageBox.critical(self, "エラー", f"削除フォルダの作成に失敗しました:\n{e}")

    def setup_trash_folder(self):
        current_trash = self.db.get_trash_folder()
        default_trash = config.get_default_trash_folder()

        msg = "削除フォルダを設定してください。\n\n"
        msg += f"現在の設定: {current_trash or '未設定（デフォルトを使用）'}\n\n"
        msg += f"デフォルト: {default_trash}\n\nフォルダを選択するか、デフォルトを使用してください。"

        reply = QMessageBox.question(
            self, "削除フォルダ設定", msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

        folder = QFileDialog.getExistingDirectory(
            self, "削除フォルダを選択",
            current_trash if current_trash else default_trash
        )
        if folder:
            if not config.validate_path(folder):
                QMessageBox.warning(self, "エラー", "無効なパスです。別のフォルダを選択してください。")
                return
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "エラー", f"フォルダの作成に失敗しました:\n{e}")
                    return
            self.db.set_trash_folder(folder)
            QMessageBox.information(self, "設定完了", f"削除フォルダを設定しました:\n{folder}")
        elif not current_trash:
            reply2 = QMessageBox.question(
                self, "デフォルト使用",
                f"デフォルト削除フォルダを使用しますか？\n\n{default_trash}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply2 == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(default_trash, exist_ok=True)
                    self.db.set_trash_folder(default_trash)
                    QMessageBox.information(
                        self, "設定完了",
                        f"デフォルト削除フォルダを設定しました:\n{default_trash}"
                    )
                except Exception as e:
                    QMessageBox.critical(self, "エラー", f"削除フォルダの作成に失敗しました:\n{e}")

    def closeEvent(self, event):
        self.db.close()
        event.accept()


# ── Entry point ──────────────────────────────────────────────────────────────

def _load_custom_fonts(app: QApplication):
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    loaded_families = []
    if os.path.isdir(fonts_dir):
        for fname in os.listdir(fonts_dir):
            if fname.lower().endswith(('.ttf', '.otf')):
                font_path = os.path.join(fonts_dir, fname)
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))

    if not loaded_families:
        return

    preferred_order = ["Inter", "Noto Sans JP", "Roboto"]
    chain = []
    for pref in preferred_order:
        for fam in loaded_families:
            if pref.lower() in fam.lower() and fam not in chain:
                chain.append(fam)

    if not chain:
        chain = list(dict.fromkeys(loaded_families))

    font = QFont(chain[0], 10)
    font.setFamilies(chain)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)


def main():
    app = QApplication(sys.argv)
    _load_custom_fonts(app)

    splash = SplashScreen()
    splash.show()

    loader = AppLoader()
    loader.progress.connect(splash.show_message)

    def on_loaded(loaded_objects):
        if loaded_objects is None:
            splash.close()
            QMessageBox.critical(
                None, "起動エラー",
                "モジュールの読み込みに失敗しました。\n詳細は debug.log を確認してください。"
            )
            return

        global DatabaseManager, ScannerThread, AnalyzerThread, ImageLoader
        global setup_logging, config
        global DuplicatePage, BlurPage, SimilarityPage, SorterPage
        global ManualSorterPage, SmallFileCleanerPage, TrashListPage

        DatabaseManager = loaded_objects.get('DatabaseManager')
        ScannerThread = loaded_objects.get('ScannerThread')
        AnalyzerThread = loaded_objects.get('AnalyzerThread')
        ImageLoader = loaded_objects.get('ImageLoader')
        setup_logging = loaded_objects.get('setup_logging')
        config = loaded_objects.get('config')

        DuplicatePage = loaded_objects.get('DuplicatePage')
        BlurPage = loaded_objects.get('BlurPage')
        SimilarityPage = loaded_objects.get('SimilarityPage')
        SorterPage = loaded_objects.get('SorterPage')
        ManualSorterPage = loaded_objects.get('ManualSorterPage')
        SmallFileCleanerPage = loaded_objects.get('SmallFileCleanerPage')
        TrashListPage = loaded_objects.get('TrashListPage')

        global window
        window = MainWindow()
        window.show()
        splash.finish(window)

    loader.finished.connect(on_loaded)
    loader.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
