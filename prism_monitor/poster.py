"""'Poster' look, matching the Still desktop clock: no panel, bold uppercase Barlow,
a huge faded accent number with a white headline across it, a vertical caption,
a thin white rule, then compact uppercase rows."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

TEXT = QColor('#FFFFFF')
ACCENT = QColor('#8FD8FF')
GOOD, WARN, BAD = QColor('#7CE3A1'), QColor('#FFD166'), QColor('#FF7A7A')
FAMILY = 'Barlow'
_loaded = False


def load_fonts():
    global _loaded, FAMILY
    if _loaded:
        return
    _loaded = True
    families = set()
    for file in sorted((Path(__file__).resolve().parent / 'fonts').glob('*.ttf')):
        font_id = QFontDatabase.addApplicationFont(str(file))
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    if 'Barlow' not in families:
        FAMILY = 'Sans Serif'


def font(px: float, weight=QFont.Bold, spacing: float = 0.0) -> QFont:
    f = QFont(FAMILY)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def alpha(color: QColor, a: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def temp_color(temp):
    if temp is None:
        return TEXT
    return TEXT if temp < 70 else WARN if temp < 85 else BAD


def battery_color(percent):
    if percent is None:
        return TEXT
    return BAD if percent <= 20 else WARN if percent <= 40 else TEXT


@dataclass
class Row:
    label: str
    value: str
    color: QColor
    level: float | None = None  # 0..1 draws a thin bar under the value (battery)


@dataclass
class Group:
    caption: str
    rows: list[Row]


class PosterView(QWidget):
    def __init__(self):
        super().__init__()
        load_fonts()
        self.scale = 1.0
        self.hero: tuple[str, str, str, str] = ('', '', '', '')  # number, unit, headline, subline
        self.caption = 'SYSTEM'
        self.groups: list[Group] = []
        self.setAttribute(Qt.WA_TranslucentBackground)
        shadow = QGraphicsDropShadowEffect(self)  # keeps white text readable on bright wallpaper
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(shadow)
        self._size = QSize(200, 200)

    # data -------------------------------------------------------------------
    def set_content(self, hero, caption, groups, scale):
        self.hero, self.caption, self.groups, self.scale = hero, caption, groups, scale
        self._size = self._layout(None)
        self.updateGeometry()
        self.setFixedSize(self._size)
        self.update()

    def sizeHint(self):
        return self._size

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._layout(p)

    # one routine both measures (painter None) and draws ------------------------------
    def _layout(self, p: QPainter | None) -> QSize:
        m = 46.0 * self.scale  # Still's "main size"
        pad = 10 * self.scale
        number, unit, headline, subline = self.hero

        num_font = font(m * 2.2, QFont.Bold)  # background number: smaller than Still's, sits right of the headline start
        num_fm = QFontMetricsF(num_font)
        ink = num_fm.tightBoundingRect('8')
        num_top, num_h = ink.top(), ink.height()
        num_w = max(num_fm.horizontalAdvance('88'), num_fm.horizontalAdvance(number))

        cap_size = m * .2
        cap_font = font(cap_size, QFont.DemiBold, cap_size * .85)
        cap_fm = QFontMetricsF(cap_font)
        cap_len = cap_fm.horizontalAdvance(self.caption)
        cap_col = cap_fm.height() + m * .22

        y = pad
        num_x = pad + cap_col + m * 1.7  # shifted right, behind the end of the headline
        head_font = font(m * .72, QFont.Bold)
        head_fm = QFontMetricsF(head_font)
        head_ink = head_fm.tightBoundingRect('M')
        head_x = pad + cap_col + m * .3
        head_cap = y + num_h * .38
        head_base = head_cap - head_ink.top()

        sub_font = font(max(11.0, m * .3), QFont.Bold, 1.2 * self.scale)
        sub_fm = QFontMetricsF(sub_font)
        sub_ink = sub_fm.tightBoundingRect('8')
        sub_cap = head_cap + head_ink.height() + m * .3
        sub_base = sub_cap - sub_ink.top()
        line_y = sub_cap + sub_ink.height() + m * .2
        line_w = max(m * 1.1, sub_fm.horizontalAdvance(subline) * .9)

        unit_font = font(m * .62, QFont.Bold)
        unit_fm = QFontMetricsF(unit_font)
        unit_x = num_x + num_w + m * .06
        width = max(num_x + num_w + (unit_fm.horizontalAdvance(unit) + m * .06 if unit else 0), head_x + head_fm.horizontalAdvance(headline),
                    head_x + sub_fm.horizontalAdvance(subline), head_x + line_w)
        hero_bottom = max(y + num_h, y + cap_len, line_y + 2 * self.scale)

        if p:
            # big number, fading towards its base like Still's poster day
            grad = QLinearGradient(0, y, 0, y + num_h)
            grad.setColorAt(0, alpha(ACCENT, 1))
            grad.setColorAt(.45, alpha(ACCENT, 225 / 255))
            grad.setColorAt(1, alpha(ACCENT, 28 / 255))
            p.setFont(num_font)
            p.setPen(QPen(grad, 0))
            number_w = num_fm.horizontalAdvance(number)
            p.drawText(QPointF(num_x + (num_w - number_w) / 2, y - num_top), number)
            if unit:  # unit sits at the top right of the number, like a superscript
                unit_x = num_x + (num_w + number_w) / 2 + m * .06
                p.setFont(unit_font)
                p.setPen(alpha(ACCENT, .95))
                p.drawText(QPointF(unit_x, y - unit_fm.tightBoundingRect('C').top()), unit)
            # vertical caption, reading bottom to top
            p.save()
            p.translate(pad + cap_fm.ascent(), y + max(num_h, cap_len))
            p.rotate(-90)
            p.setFont(cap_font)
            p.setPen(alpha(TEXT, .9))
            p.drawText(QPointF(0, 0), self.caption)
            p.restore()
            p.setFont(head_font)
            p.setPen(TEXT)
            p.drawText(QPointF(head_x, head_base), headline)
            p.setFont(sub_font)
            p.drawText(QPointF(head_x, sub_base), subline)
            p.fillRect(QRectF(head_x, line_y, line_w, max(1.0, 1.6 * self.scale)), alpha(TEXT, .85))

        # rows ------------------------------------------------------------------
        label_font = font(m * .3, QFont.DemiBold, 1.4 * self.scale)
        value_font = font(m * .34, QFont.Bold, .6 * self.scale)
        group_font = font(m * .22, QFont.Bold, m * .22 * .6)
        lf, vf, gf = QFontMetricsF(label_font), QFontMetricsF(value_font), QFontMetricsF(group_font)
        row_h = max(lf.height(), vf.height()) + 3 * self.scale
        left = head_x
        widest = 0.0
        for g in self.groups:
            for r in g.rows:
                widest = max(widest, lf.horizontalAdvance(r.label) + 22 * self.scale + vf.horizontalAdvance(r.value))
            widest = max(widest, gf.horizontalAdvance(g.caption))
        width = max(width, left + widest)
        right = width

        cy = hero_bottom + m * .35
        for g in self.groups:
            if p:
                p.setFont(group_font)
                p.setPen(ACCENT)
                p.drawText(QPointF(left, cy + gf.ascent()), g.caption)
            cy += gf.height() + 4 * self.scale
            for r in g.rows:
                base = cy + max(lf.ascent(), vf.ascent())
                if p:
                    p.setFont(label_font)
                    p.setPen(alpha(TEXT, .82))
                    p.drawText(QPointF(left, base), lf.elidedText(r.label, Qt.ElideRight,
                                                                 right - left - vf.horizontalAdvance(r.value) - 16 * self.scale))
                    p.setFont(value_font)
                    p.setPen(r.color)
                    vw = vf.horizontalAdvance(r.value)
                    p.drawText(QPointF(right - vw, base), r.value)
                    if r.level is not None:
                        bar_y = base + 3 * self.scale
                        p.fillRect(QRectF(right - vw, bar_y, vw, 1.4 * self.scale), alpha(TEXT, .2))
                        p.fillRect(QRectF(right - vw, bar_y, vw * max(0.0, min(1.0, r.level)), 1.4 * self.scale), r.color)
                cy += row_h + (4 * self.scale if r.level is not None else 0)
            cy += m * .22
        return QSize(int(right + pad + 2), int(max(hero_bottom, cy) + pad))
