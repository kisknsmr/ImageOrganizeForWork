"""
デザイントークン — PhotoSortX UIの色・タイポグラフィ・QSSを一元管理
"""


class Theme:
    # ── Backgrounds ─────────────────────────────────────────
    BG_APP       = "#242424"   # メインコンテンツ領域
    BG_SIDEBAR   = "#1a1a1a"   # サイドバー
    BG_CARD      = "#2a2a2a"   # カード・パネル
    BG_HOVER     = "#2d2d2d"   # ホバー状態
    BG_ACTIVE    = "#313131"   # アクティブなnavアイテム
    BG_ICON_PRIMARY = "#3d5fc2"  # アクセントアイコン背景（青）
    BG_ICON_MUTED   = "#2e2e2e"  # 通常アイコン背景

    # ── Accent ──────────────────────────────────────────────
    ACCENT       = "#5b8aff"   # プライマリアクセント
    ACCENT_DARK  = "#3d5fc2"   # 濃いアクセント

    # ── Text ────────────────────────────────────────────────
    TEXT_PRIMARY   = "#f0f0f0"
    TEXT_SECONDARY = "#b0b0b0"
    TEXT_MUTED     = "#666666"
    TEXT_SECTION   = "#555555"  # section headers
    TEXT_ACTIVE    = "#ffffff"  # active nav item

    # ── Borders ─────────────────────────────────────────────
    BORDER       = "#333333"
    BORDER_LIGHT = "#3d3d3d"

    # ── Semantic ────────────────────────────────────────────
    DANGER_BG     = "#3a1e1e"
    DANGER_TEXT   = "#ff6b6b"
    DANGER_BORDER = "#5a2424"

    # ── Font sizes ──────────────────────────────────────────
    FS_SECTION = "10px"
    FS_NAV     = "13px"
    FS_BODY    = "13px"
    FS_CAPTION = "11px"
    FS_HEADING = "26px"
    FS_SUBHEAD = "14px"

    # ── Composed QSS ────────────────────────────────────────
    @classmethod
    def app_qss(cls) -> str:
        return f"""
            QMainWindow, QDialog {{
                background-color: {cls.BG_APP};
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FS_BODY};
            }}
            QWidget {{
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FS_BODY};
            }}
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background-color: {cls.BG_CARD};
                max-height: 4px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {cls.ACCENT};
                border-radius: 2px;
            }}
            QListView, QListWidget {{
                background-color: {cls.BG_SIDEBAR};
                border: none;
            }}
            QToolTip {{
                background-color: {cls.BG_CARD};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER_LIGHT};
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {cls.BORDER_LIGHT};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """

    @classmethod
    def nav_normal(cls) -> str:
        """通常状態のnavボタンスタイル"""
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                padding: 7px 12px 7px 12px;
                text-align: left;
                font-size: {cls.FS_NAV};
                color: {cls.TEXT_SECONDARY};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {cls.BG_HOVER};
                color: {cls.TEXT_PRIMARY};
            }}
        """

    @classmethod
    def nav_active(cls) -> str:
        """アクティブ状態のnavボタンスタイル"""
        return f"""
            QPushButton {{
                background: {cls.BG_ACTIVE};
                border: none;
                padding: 7px 12px 7px 12px;
                text-align: left;
                font-size: {cls.FS_NAV};
                color: {cls.TEXT_ACTIVE};
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {cls.BG_HOVER};
                color: {cls.TEXT_ACTIVE};
            }}
        """

    @classmethod
    def dialog_qss(cls) -> str:
        return f"""
            QDialog {{
                background-color: {cls.BG_CARD};
                color: {cls.TEXT_PRIMARY};
            }}
            QLabel {{ color: {cls.TEXT_SECONDARY}; font-size: 13px; }}
            QPushButton {{
                background: {cls.BG_HOVER};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER_LIGHT};
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: #383838; }}
        """
