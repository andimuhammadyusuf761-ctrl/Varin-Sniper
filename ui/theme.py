"""
theme.py — Varin Sniper design system (dark purple gradient + efek 3D).

Modul ini SENGAJA tidak mengimpor customtkinter di level atas supaya bisa
dipakai juga oleh tools/make_icons.py (generator ikon, stdlib + palette saja).
Import customtkinter dilakukan malas di dalam fungsi yang memang butuh widget.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# --------------------------------------------------------------------------- #
# Palette — dark purple gradient
# --------------------------------------------------------------------------- #
BG = "#07030d"             # latar paling belakang
BG_2 = "#0b0618"           # latar area utama
SIDEBAR = "#0e0720"        # sidebar
SIDEBAR_2 = "#140a2b"      # sidebar bawah (gradient)
PANEL = "#120926"          # panel kartu
PANEL_2 = "#170d2e"
CARD = "#1a0f30"           # isi kartu
CARD_HI = "#241542"        # kartu hover
CARD_LO = "#100720"        # dasar (bayangan)
HOVER = "#1f1238"

# garis bevel 3D: highlight di atas-kiri, shadow di bawah-kanan
BEVEL_HI = "#3b2367"
BEVEL_LO = "#05020b"

BORDER = "#2b1a4b"
BORDER_HI = "#7b2ff0"
BORDER_LO = "#0a0516"

ACCENT = "#b366ff"         # ungu neon utama
ACCENT_2 = "#8a2be2"
ACCENT_3 = "#e2c9ff"
GLOW = "#9d4edd"
PLASMA = "#6a1fd0"

OK = "#2bf5a0"
OK_2 = "#00d988"
BAD = "#ff4d6d"
BAD_DIM = "#3a1622"
WARN = "#ffd166"
INFO = "#7b6cff"
TAKEN = "#8c8ab0"
CLAIM = "#7ff6ff"

TEXT = "#f3edff"
TEXT_2 = "#b8a4e4"
TEXT_3 = "#7b68b0"
INK = "#0a0417"            # teks di atas tombol aksen

# ikon aplikasi (dipakai tools/make_icons.py)
ICON_TOP = "#5a17a8"
ICON_BOTTOM = "#150629"
ICON_MARK_TOP = "#f0dcff"
ICON_MARK_BOTTOM = "#a855f7"

# efek 3D ekstra (bisa dimatikan dari GUI supaya CPU 100% untuk scanning)
EFFECTS = True


def set_effects(enabled: bool) -> None:
    global EFFECTS
    EFFECTS = bool(enabled)


RADIUS = 16
RADIUS_SM = 10
PAD = 16
SIDEBAR_W = 274
HERO_H = 148
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"

# --------------------------------------------------------------------------- #
# Warna: konversi & campur
# --------------------------------------------------------------------------- #
def to_rgb(color: str) -> Tuple[float, float, float]:
    h = (color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
    except ValueError:
        return (0.0, 0.0, 0.0)


def from_rgb(r: float, g: float, b: float) -> str:
    cl = lambda v: max(0, min(255, int(round(v * 255.0))))  # noqa: E731
    return f"#{cl(r):02x}{cl(g):02x}{cl(b):02x}"


def mix(color_a: str, color_b: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    ar, ag, ab = to_rgb(color_a)
    br, bg, bb = to_rgb(color_b)
    return from_rgb(ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t)


def darken(color: str, t: float = 0.25) -> str:
    return mix(color, "#000000", t)


def lighten(color: str, t: float = 0.25) -> str:
    return mix(color, "#ffffff", t)


def alpha_over(fg: str, bg: str, alpha: float) -> str:
    """Simulasi alpha tanpa transparansi (Tk tidak punya alpha per-widget)."""
    return mix(bg, fg, alpha)


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


# --------------------------------------------------------------------------- #
# Font (cached)
# --------------------------------------------------------------------------- #
_FONTS: Dict[Tuple[str, int, str], object] = {}


def font(size: int = 12, weight: str = "normal", mono: bool = False) -> object:
    """CTkFont yang di-cache. Aman dipanggil hanya setelah root Tk dibuat."""
    family = MONO_FAMILY if mono else FONT_FAMILY
    key = (family, int(size), weight)
    cached = _FONTS.get(key)
    if cached is None:
        import customtkinter as ctk
        cached = ctk.CTkFont(family=family, size=int(size), weight=weight)
        _FONTS[key] = cached
    return cached


def apply_appearance() -> None:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


# --------------------------------------------------------------------------- #
# Gradient photo (dipakai hero banner, sidebar, header kartu)
# --------------------------------------------------------------------------- #
_GRAD_CACHE: Dict[Tuple[int, int, str, str], object] = {}
_GRAD_MAX = 24


def gradient_photo(width: int, height: int, top: str, bottom: str) -> object:
    """PhotoImage gradient vertikal (di-cache + dibatasi jumlahnya)."""
    import tkinter as tk

    w = max(1, int(width))
    h = max(2, int(height))
    key = (w, h, top, bottom)
    cached = _GRAD_CACHE.get(key)
    if cached is not None:
        return cached

    base = tk.PhotoImage(width=1, height=h)
    last = h - 1
    for y in range(h):
        base.put(mix(top, bottom, y / last), to=(0, y, 1, y + 1))
    img = base.zoom(w, 1) if w > 1 else base
    if len(_GRAD_CACHE) >= _GRAD_MAX:
        _GRAD_CACHE.clear()
    _GRAD_CACHE[key] = img
    return img
