"""
アイコン描画ユーティリティ
QPainter でストロークスタイルのアイコンを生成します。
"""
import math

from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QIcon, QPainterPath
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF


# ── 内部ヘルパー ────────────────────────────────────────────

def _make(size: int) -> tuple[QPixmap, QPainter]:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return px, p


def _pen(p: QPainter, color: str, w: float = 1.4):
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.GlobalColor.transparent)


# ── アイコン関数 ─────────────────────────────────────────────

def icon_home(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 屋根（三角形）
    roof = QPainterPath()
    roof.moveTo(s * 0.50, s * 0.08)
    roof.lineTo(s * 0.92, s * 0.52)
    roof.lineTo(s * 0.08, s * 0.52)
    roof.closeSubpath()
    p.drawPath(roof)

    # 壁
    p.drawRect(QRectF(s * 0.18, s * 0.52, s * 0.64, s * 0.40))

    # ドア
    p.drawRect(QRectF(s * 0.38, s * 0.66, s * 0.24, s * 0.26))

    p.end()
    return px


def icon_gallery(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)
    gap = s * 0.10
    half = (s * 0.88 - gap) / 2

    for row in range(2):
        for col in range(2):
            x = s * 0.06 + col * (half + gap)
            y = s * 0.06 + row * (half + gap)
            p.drawRect(QRectF(x, y, half, half))

    p.end()
    return px


def icon_import(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 上向き矢印の軸
    p.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.50, s * 0.76))

    # 矢頭
    p.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.25, s * 0.37))
    p.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.75, s * 0.37))

    # ベースライン
    p.drawLine(QPointF(s * 0.15, s * 0.88), QPointF(s * 0.85, s * 0.88))

    p.end()
    return px


def icon_duplicate(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 背面の四角
    p.drawRect(QRectF(s * 0.28, s * 0.06, s * 0.62, s * 0.62))

    # 前面の四角（左下にオフセット）
    p.drawRect(QRectF(s * 0.08, s * 0.28, s * 0.62, s * 0.62))

    p.end()
    return px


def icon_blur(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 中心の円（シャープ）
    p.drawEllipse(QRectF(s * 0.34, s * 0.34, s * 0.32, s * 0.32))

    # 中間の円
    p.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))

    # 外側の点線円（8セグメント）
    outer = QRectF(s * 0.02, s * 0.02, s * 0.96, s * 0.96)
    for i in range(8):
        p.drawArc(outer, int(i * 45 * 16), int(22 * 16))

    p.end()
    return px


def icon_tiny_file(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)
    fold = s * 0.22

    # ドキュメント輪郭（折り返しコーナー付き）
    path = QPainterPath()
    path.moveTo(s * 0.14, s * 0.04)
    path.lineTo(s * 0.86 - fold, s * 0.04)
    path.lineTo(s * 0.86, s * 0.04 + fold)
    path.lineTo(s * 0.86, s * 0.96)
    path.lineTo(s * 0.14, s * 0.96)
    path.closeSubpath()
    p.drawPath(path)

    # 折り返し線
    p.drawLine(QPointF(s * 0.86 - fold, s * 0.04),
               QPointF(s * 0.86 - fold, s * 0.04 + fold))
    p.drawLine(QPointF(s * 0.86 - fold, s * 0.04 + fold),
               QPointF(s * 0.86, s * 0.04 + fold))

    # テキスト行
    p.drawLine(QPointF(s * 0.26, s * 0.48), QPointF(s * 0.72, s * 0.48))
    p.drawLine(QPointF(s * 0.26, s * 0.60), QPointF(s * 0.72, s * 0.60))
    p.drawLine(QPointF(s * 0.26, s * 0.72), QPointF(s * 0.56, s * 0.72))

    p.end()
    return px


def icon_similar(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)
    sq = s * 0.30
    gap = s * 0.08

    offsets = [
        (s * 0.06, s * 0.06),
        (s * 0.06 + sq + gap, s * 0.06),
        (s * 0.06, s * 0.06 + sq + gap),
        (s * 0.06 + sq + gap, s * 0.06 + sq + gap),
    ]
    for x, y in offsets:
        p.drawRect(QRectF(x, y, sq, sq))

    p.end()
    return px


def icon_manual_sort(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # チェックボックス
    p.drawRect(QRectF(s * 0.08, s * 0.08, s * 0.84, s * 0.84))

    # チェックマーク
    check = QPainterPath()
    check.moveTo(s * 0.24, s * 0.52)
    check.lineTo(s * 0.44, s * 0.72)
    check.lineTo(s * 0.76, s * 0.30)
    p.drawPath(check)

    p.end()
    return px


def icon_ai(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    s = float(size)
    cx, cy = s / 2, s / 2
    r_long = s * 0.44
    r_short = s * 0.11

    path = QPainterPath()
    path.moveTo(cx, cy - r_long)
    path.lineTo(cx + r_short, cy - r_short)
    path.lineTo(cx + r_long, cy)
    path.lineTo(cx + r_short, cy + r_short)
    path.lineTo(cx, cy + r_long)
    path.lineTo(cx - r_short, cy + r_short)
    path.lineTo(cx - r_long, cy)
    path.lineTo(cx - r_short, cy - r_short)
    path.closeSubpath()

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)

    p.end()
    return px


def icon_trash(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 缶本体
    p.drawRect(QRectF(s * 0.18, s * 0.30, s * 0.64, s * 0.62))

    # 蓋
    p.drawLine(QPointF(s * 0.10, s * 0.26), QPointF(s * 0.90, s * 0.26))

    # 取っ手
    p.drawLine(QPointF(s * 0.38, s * 0.10), QPointF(s * 0.62, s * 0.10))
    p.drawLine(QPointF(s * 0.38, s * 0.10), QPointF(s * 0.32, s * 0.26))
    p.drawLine(QPointF(s * 0.62, s * 0.10), QPointF(s * 0.68, s * 0.26))

    # 内側の縦線
    p.drawLine(QPointF(s * 0.40, s * 0.42), QPointF(s * 0.40, s * 0.84))
    p.drawLine(QPointF(s * 0.60, s * 0.42), QPointF(s * 0.60, s * 0.84))

    p.end()
    return px


def icon_settings(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color, 1.3)
    s = float(size)

    # 中心の円
    p.drawEllipse(QRectF(s * 0.30, s * 0.30, s * 0.40, s * 0.40))

    # ギアの歯（8方向）
    for i in range(8):
        angle = math.radians(i * 45)
        r1 = s * 0.38
        r2 = s * 0.48
        x1 = s / 2 + r1 * math.cos(angle)
        y1 = s / 2 + r1 * math.sin(angle)
        x2 = s / 2 + r2 * math.cos(angle)
        y2 = s / 2 + r2 * math.sin(angle)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    p.end()
    return px


def icon_refresh(size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 円弧（270度）
    p.drawArc(QRectF(s * 0.12, s * 0.12, s * 0.76, s * 0.76),
              int(90 * 16), int(-270 * 16))

    # 矢頭
    tip_x = s / 2
    tip_y = s * 0.12
    arrow = QPainterPath()
    arrow.moveTo(tip_x - s * 0.16, tip_y + s * 0.02)
    arrow.lineTo(tip_x, tip_y - s * 0.01)
    arrow.lineTo(tip_x + s * 0.16, tip_y + s * 0.16)
    p.drawPath(arrow)

    p.end()
    return px


def icon_clock(size: int = 16, color: str = "#666666") -> QPixmap:
    px, p = _make(size)
    _pen(p, color)
    s = float(size)

    # 文字盤
    p.drawEllipse(QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88))

    # 短針
    p.drawLine(QPointF(s * 0.50, s * 0.50),
               QPointF(s * 0.50, s * 0.26))

    # 長針
    p.drawLine(QPointF(s * 0.50, s * 0.50),
               QPointF(s * 0.70, s * 0.58))

    p.end()
    return px


# ── ブランドアイコン ──────────────────────────────────────────

def icon_app_brand(size: int = 28) -> QPixmap:
    """サイドバーのブランドアイコン（青丸角背景 + フォトフレーム）"""
    px, p = _make(size)
    s = float(size)

    # 青い丸角背景
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#3d5fc2"))
    p.drawRoundedRect(QRectF(0, 0, s, s), 7, 7)

    # 白いフォトフレームアイコン
    _pen(p, "white", max(1.0, s * 0.07))
    m = s * 0.18
    p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))

    # 山型
    mountain = QPainterPath()
    mountain.moveTo(m + 1, s - m - 2)
    mountain.lineTo(s * 0.38, m + s * 0.18)
    mountain.lineTo(s * 0.54, s * 0.50)
    mountain.lineTo(s * 0.68, m + s * 0.12)
    mountain.lineTo(s - m - 1, s - m - 2)
    p.drawPath(mountain)

    # 太陽
    sun_r = s * 0.08
    p.drawEllipse(QRectF(s * 0.62, m + 2, sun_r * 2, sun_r * 2))

    p.end()
    return px


def icon_hero(size: int = 80) -> QPixmap:
    """ホームページ中央の大アイコン（暗い青背景 + フォトフレーム）"""
    px, p = _make(size)
    s = float(size)

    # 暗い青い丸角背景
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2a3d6e"))
    p.drawRoundedRect(QRectF(0, 0, s, s), 18, 18)

    # ライトブルーのフォトフレームアイコン
    _pen(p, "#7aa8ff", max(1.5, s * 0.03))
    m = s * 0.18
    p.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))

    # 山型
    mountain = QPainterPath()
    mountain.moveTo(m + 2, s - m - 3)
    mountain.lineTo(s * 0.36, m + s * 0.20)
    mountain.lineTo(s * 0.52, s * 0.52)
    mountain.lineTo(s * 0.68, m + s * 0.14)
    mountain.lineTo(s - m - 2, s - m - 3)
    p.drawPath(mountain)

    # 太陽
    sun_r = s * 0.07
    p.drawEllipse(QRectF(s * 0.62, m + 3, sun_r * 2, sun_r * 2))

    p.end()
    return px


# ── ディスパッチャー ──────────────────────────────────────────

_ICON_MAP = {
    "home":        icon_home,
    "gallery":     icon_gallery,
    "import":      icon_import,
    "duplicate":   icon_duplicate,
    "blur":        icon_blur,
    "tiny_file":   icon_tiny_file,
    "similar":     icon_similar,
    "manual_sort": icon_manual_sort,
    "ai":          icon_ai,
    "trash":       icon_trash,
    "settings":    icon_settings,
    "refresh":     icon_refresh,
    "clock":       icon_clock,
}


def get_icon(name: str, size: int = 16, color: str = "#b0b0b0") -> QIcon:
    """名前からQIconを生成して返す。"""
    fn = _ICON_MAP.get(name)
    if fn is None:
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        return QIcon(px)
    return QIcon(fn(size, color))


def get_pixmap(name: str, size: int = 16, color: str = "#b0b0b0") -> QPixmap:
    fn = _ICON_MAP.get(name)
    if fn is None:
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        return px
    return fn(size, color)
