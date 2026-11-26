"""Цвета и таблица стилей (QSS): почти чёрная тема, светлые акценты, боковая панель и нижняя панель запуска."""
from __future__ import annotations

import re

from ..resources import asset

ACCENT = "#ececf0"
ACCENT2 = "#b8b8c2"
TEXT = "#ececf0"
MUTED = "#9b9ba7"
OK = "#3ddc97"
WARN = "#ffd166"
ERR = "#ff6b6b"
PAGE_BG = "#0a0a0b"
GRAD_A = "#0a0a0b"   # фон окна (как в 16Launcher: почти чёрный, без градиента)
GRAD_B = "#0a0a0b"
GRAD_C = "#0a0a0b"
MODAL_BG = "#121213"
OPT_BG = "#161618"


SW_OFF = asset("switch_off.png").replace("\\", "/")  # переключатель-«тумблер» вместо квадратной галочки
SW_ON = asset("switch_on.png").replace("\\", "/")


# оформления: сдвиг тёмно-серых цветов в сторону оттенка (R, G, B); None — как есть
TONES = {"dark": (0, 0, 0), "midnight": (-2, 4, 22), "forest": (-2, 14, 4), "sunset": (18, 6, 0)}
TONE_NAMES = [("dark", "Тёмная"), ("midnight", "Полночь"), ("forest", "Лес"), ("sunset", "Закат")]
ACCENTS = ["#5b6ee1", "#c2557a", "#3f9d78", "#c98a2b", "#8b5cc2", "#2f8fb5", "#b5533c", "#6a8f3a"]


def tint(hex_color: str, tone: str) -> str:
    """Тёмно-серый цвет #rrggbb смещается в сторону оттенка; остальные цвета не меняются."""
    d = TONES.get(tone)
    h = hex_color.lstrip("#")
    if not d or len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if max(r, g, b) - min(r, g, b) > 3 or max(r, g, b) > 0x32:
        return hex_color
    k = min(1.0, max(r, g, b) / 40)
    out = [max(0, min(255, round(c + dc * k))) for c, dc in zip((r, g, b), d)]
    return "#%02x%02x%02x" % tuple(out)


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _mix(hex_color: str, to: int, amount: float) -> str:
    h = hex_color.lstrip("#")
    c = [round(int(h[i:i + 2], 16) * (1 - amount) + to * amount) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(c)


def look(tone: str = "dark", accent: str = "") -> None:
    """Запоминает цвета фона окна для выбранного оформления (их читает рисование фона)."""
    global GRAD_A, GRAD_B, GRAD_C
    GRAD_A = GRAD_B = GRAD_C = tint("#0a0a0b", tone)


def qss(glass: bool = True, strength: int = 60, tone: str = "dark", accent: str = "") -> str:
    text = _qss(glass, strength, accent if re.fullmatch(r"#[0-9a-fA-F]{6}", str(accent or "")) else "")
    return re.sub(r"#[0-9a-fA-F]{6}\b", lambda m: tint(m.group(0), tone), text) if tone in TONES and tone != "dark" else text


def _qss(glass: bool, strength: int, accent: str) -> str:
    s = max(0, min(100, int(strength)))
    # «Стекло»: чем сильнее, тем прозрачнее панели (видно фон)
    a = int(150 + (100 - s) * 0.9) if glass else 235
    a = max(90, min(240, a))
    card = f"rgba(18,18,19,{a})"
    soft = f"rgba(0,0,0,{max(60, a - 70)})"
    acc = accent or ACCENT
    out = f"""
* {{ font-family: "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif; font-size: 13px; color: {TEXT}; }}
QWidget {{ background: transparent; }}
QDialog, QMessageBox {{ background: {MODAL_BG}; }}
QToolTip {{ background: {OPT_BG}; color: {TEXT}; border: 1px solid rgba(255,255,255,40); padding: 4px 6px; }}

QLabel {{ background: transparent; }}
QLabel[kind="h1"] {{ font-size: 34px; font-weight: 800; }}
QLabel[kind="h2"] {{ font-size: 18px; font-weight: 700; }}
QLabel[kind="h3"] {{ font-size: 13px; font-weight: 700; color: {TEXT}; }}
QLabel[kind="muted"] {{ color: {MUTED}; }}
QLabel[kind="ok"] {{ color: {OK}; }}
QLabel[kind="warn"] {{ color: {WARN}; }}
QLabel[kind="err"] {{ color: {ERR}; }}
QLabel[kind="accent"] {{ color: {acc}; font-weight: 700; }}
QLabel[kind="ph"] {{ background: rgba(0,0,0,80); border-radius: 10px; color: {TEXT}; font-weight: 800; font-size: 20px; }}

QFrame#card, QFrame[kind="card"] {{ background: {card}; border: 1px solid rgba(255,255,255,24); border-radius: 14px; }}
QFrame[kind="soft"] {{ background: {soft}; border: 1px solid rgba(255,255,255,24); border-radius: 12px; }}
QFrame[kind="current"] {{ background: {card}; border: 2px solid {acc}; border-radius: 14px; }}
QFrame[kind="fit"] {{ background: rgba(60,200,120,45); border: 1px solid rgba(110,231,160,160); border-radius: 10px; }}
QFrame#rail {{ background: #121213; border: 1px solid rgba(255,255,255,24); border-radius: 18px; }}
QFrame#pill {{ background: #111113; border: 1px solid rgba(255,255,255,26); border-radius: 12px; }}
QFrame#launchbar {{ background: #121213; border: 1px solid rgba(255,255,255,24); border-radius: 16px; }}
QFrame[kind="build"] {{ background: #131315; border: 1px solid rgba(255,255,255,24); border-radius: 14px; }}
QFrame[kind="build"]:hover {{ border-color: rgba(255,255,255,70); }}
QFrame[kind="buildsel"] {{ background: #19191c; border: 1px solid rgba(255,255,255,110); border-radius: 14px; }}
QFrame#navbar {{ background: {card}; border: 1px solid rgba(255,255,255,24); border-radius: 14px; }}

QPushButton {{ background: #1c1c1e; border: 1px solid #2c2c30; border-radius: 10px;
  padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #26262a; }}
QPushButton:pressed {{ background: #303035; }}
QPushButton:disabled {{ color: rgba(244,241,255,110); background: rgba(255,255,255,12); border-color: rgba(255,255,255,20); }}
QPushButton[kind="primary"] {{ border: none; color: #111114; background: #f1f1f4; }}
QPushButton[kind="primary"]:hover {{ background: #ffffff; }}
QPushButton[kind="primary"]:disabled {{ color: rgba(17,17,20,150); background: rgba(255,255,255,90); }}
QPushButton[kind="danger"] {{ background: rgba(255,107,107,50); border-color: rgba(255,107,107,150); color: #ffd3d3; }}
QPushButton[kind="danger"]:hover {{ background: rgba(255,107,107,90); }}
QPushButton[kind="small"] {{ padding: 3px 10px; font-size: 12px; border-radius: 8px; }}
QPushButton[kind="nav"] {{ border: none; background: transparent; padding: 8px 16px; border-radius: 10px; font-weight: 700; color: {MUTED}; }}
QPushButton[kind="nav"]:hover {{ background: rgba(255,255,255,30); color: {TEXT}; }}
QPushButton[kind="nav"]:checked {{ color: #111114; background: #f1f1f4; }}
QPushButton[kind="chip"] {{ border-radius: 14px; padding: 4px 12px; background: rgba(0,0,0,70); }}
QPushButton[kind="chip"]:checked {{ border-color: {acc}; color: {acc}; }}
QPushButton[kind="play"] {{ font-size: 17px; font-weight: 800; padding: 14px 44px; border-radius: 12px; border: none; color: #111114;
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #dcdce2); }}
QPushButton[kind="play"]:hover {{ background: #ffffff; }}
QPushButton[kind="play"]:disabled {{ color: rgba(17,17,20,150); background: rgba(255,255,255,90); }}
QPushButton[kind="rail"] {{ border: none; background: transparent; border-radius: 12px; padding: 8px 2px; font-size: 10px;
  font-weight: 600; color: {MUTED}; min-width: 58px; }}
QPushButton[kind="rail"]:hover {{ background: rgba(255,255,255,18); color: {TEXT}; }}
QPushButton[kind="rail"]:checked {{ background: rgba(255,255,255,30); color: #ffffff; }}
QPushButton[kind="pill"] {{ border: none; background: transparent; padding: 4px 10px; border-radius: 8px; font-weight: 700; }}
QPushButton[kind="pill"]:hover {{ background: rgba(255,255,255,26); }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: #111113; border: 1px solid #2a2a2e; border-radius: 9px; padding: 6px 9px;
  selection-background-color: #5a5a66; selection-color: #ffffff; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {acc}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {OPT_BG}; border: 1px solid rgba(255,255,255,50); selection-background-color: rgba(255,255,255,110); outline: 0; }}
QListWidget, QTreeWidget, QTableWidget {{ background: rgba(0,0,0,70); border: 1px solid rgba(255,255,255,24); border-radius: 10px; outline: 0; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: rgba(255,255,255,90); color: {TEXT}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 36px; height: 20px; border: none; background: transparent; image: url("{SW_OFF}"); }}
QCheckBox::indicator:checked {{ image: url("{SW_ON}"); }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 8px; border: 1px solid rgba(255,255,255,80); background: rgba(0,0,0,90); }}
QRadioButton::indicator:checked {{ background: #f1f1f4; border-color: #f1f1f4; }}

QSlider::groove:horizontal {{ height: 6px; background: rgba(255,255,255,40); border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: #dcdce2; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; border-radius: 8px; background: #fff; }}

QProgressBar {{ background: rgba(255,255,255,40); border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #f1f1f4, stop:1 #bdbdc6); }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,70); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,120); }}
QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,70); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: rgba(0,0,0,70); padding: 7px 16px; border-radius: 9px; margin-right: 4px; color: {MUTED}; }}
QTabBar::tab:selected {{ background: rgba(255,255,255,60); color: {TEXT}; }}
QMenu {{ background: {OPT_BG}; border: 1px solid rgba(255,255,255,50); padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(255,255,255,90); }}
"""
    if accent:
        dark = _lum(accent) > 0.55
        on = "#111114" if dark else "#ffffff"
        out = out.replace("color: #111114", f"color: {on}")
        out = out.replace("#f1f1f4", accent).replace("#dcdce2", _mix(accent, 255, 0.15)).replace("#bdbdc6", _mix(accent, 0, 0.25))
        out = out.replace("stop:0 #ffffff", f"stop:0 {_mix(accent, 255, 0.25)}")
    return out
