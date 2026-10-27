"""
icons.py — pemuat set ikon Varin Sniper (PNG hasil tools/make_icons.py).

Semua ikon di-cache dan dimuat malas (lazy) supaya startup tetap cepat. Kalau
file aset hilang (mis. exe tidak menyertakan folder assets), fungsi di sini
mengembalikan None dan UI otomatis jatuh ke tampilan teks saja.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from typing import Dict, Optional, Tuple

_CACHE: Dict[Tuple[str, str], object] = {}

_ACT_VARIANT_INDEX = {"hi": 0, "dim": 1, "ink": 2}


def resource_path(*parts: str) -> str:
    """Path aset yang benar baik saat jalan dari source maupun dari .exe."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _load(rel_parts: Tuple[str, ...], key: Tuple[str, str]) -> Optional[object]:
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = resource_path(*rel_parts)
    if not os.path.exists(path):
        return None
    try:
        img = tk.PhotoImage(file=path)
    except Exception:  # noqa: BLE001  (Tk tanpa dukungan PNG, file rusak, dll.)
        return None
    _CACHE[key] = img
    return img


def nav_icon(name: str, active: bool = True) -> Optional[object]:
    """Ikon navigasi sidebar: varian terang saat aktif, redup saat tidak."""
    variant = "hi" if active else "dim"
    return _load(("assets", "icons", f"nav_{name}_{variant}.png"), ("nav", f"{name}_{variant}"))


def action_icon(name: str, variant: str = "hi") -> Optional[object]:
    """Ikon tombol: hi (di latar gelap), dim (sekunder), ink (di tombol terang)."""
    variant = variant if variant in _ACT_VARIANT_INDEX else "hi"
    return _load(("assets", "icons", f"act_{name}_{variant}.png"), ("act", f"{name}_{variant}"))


def logo(size: str = "big") -> Optional[object]:
    """Logo sidebar: 'big' = 128px, 'small' = 64px."""
    if size == "small":
        return _load(("assets", "logo_small.png"), ("logo", "small"))
    return _load(("assets", "logo.png"), ("logo", "big"))


def app_icon_photo() -> Optional[object]:
    return _load(("assets", "icon.png"), ("app", "png"))


def set_window_icon(window: object) -> bool:
    """Pasang ikon window: .ico di Windows, fallback PNG (iconphoto)."""
    ico = resource_path("assets", "icon.ico")
    if os.name == "nt" and os.path.exists(ico):
        try:
            window.iconbitmap(ico)  # type: ignore[attr-defined]
            return True
        except Exception:  # noqa: BLE001
            pass
    img = app_icon_photo()
    if img is not None:
        try:
            window.iconphoto(True, img)  # type: ignore[attr-defined]
            return True
        except Exception:  # noqa: BLE001
            pass
    return False
