"""
widgets.py — komponen UI Varin Sniper yang bisa dipakai ulang (tema dark
purple gradient + efek 3D hemat CPU).

Prinsip anti-lag:
  * "3D" dibuat dari bevel statis (garis highlight + bayangan) — tidak ada
    animasi per-frame.
  * Hover/press hanya mengganti warna (configure), bukan menggeser geometri,
    jadi tidak memicu re-layout terus-menerus.
  * Semua font, gambar gradient, dan ikon di-cache.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

from ui import icons as icons_mod
from ui import theme as T


# --------------------------------------------------------------------------- #
# Helper: tombol dengan bevel + efek tekan
# --------------------------------------------------------------------------- #
VARIANTS: Dict[str, Dict[str, str]] = {
    "primary": {"fg": T.ACCENT, "hi": T.ACCENT_3, "text": T.INK, "border": T.ACCENT_3,
                "icon": "ink", "press": T.ACCENT_2},
    "success": {"fg": T.OK, "hi": "#5cffc0", "text": T.INK, "border": "#8dffd0",
                "icon": "ink", "press": T.OK_2},
    "ghost": {"fg": T.CARD, "hi": T.CARD_HI, "text": T.TEXT_2, "border": T.BORDER,
              "icon": "hi", "press": T.HOVER},
    "soft": {"fg": T.CARD_HI, "hi": "#2c1a52", "text": T.ACCENT_3, "border": T.BORDER_HI,
             "icon": "hi", "press": T.BORDER_HI},
    "danger": {"fg": T.CARD, "hi": T.BAD_DIM, "text": T.BAD, "border": "#4a2430",
               "icon": "hi", "press": T.BAD_DIM},
}

_ICON_REFS: List[object] = []


def button(parent: Any, text: str, command: Optional[Callable[[], None]] = None,
           variant: str = "ghost", icon: str = "", width: int = 0, height: int = 38,
           font_size: int = 12, bold: bool = True, radius: int = T.RADIUS_SM,
           anchor: str = "center", padx: int = 0) -> ctk.CTkButton:
    """Tombol 3D dengan ikon opsional. `icon` = nama di set act_*."""
    spec = VARIANTS.get(variant, VARIANTS["ghost"])
    kwargs: Dict[str, Any] = dict(
        text=text, command=command, height=height, corner_radius=radius,
        fg_color=spec["fg"], hover_color=spec["press"], text_color=spec["text"],
        border_width=1, border_color=spec["border"],
        font=T.font(font_size, "bold" if bold else "normal"), anchor=anchor,
    )
    if width:
        kwargs["width"] = width
    if padx:
        kwargs["padx"] = padx

    image = icons_mod.action_icon(icon, spec["icon"]) if icon else None
    if image is not None:
        _ICON_REFS.append(image)
        kwargs["image"] = image
        kwargs["compound"] = "left"

    btn = ctk.CTkButton(parent, **kwargs)

    # efek 3D: hover lebih terang, tekan lebih gelap (tanpa re-layout)
    def _enter(_e: Any) -> None:
        if not T.EFFECTS:
            return
        try:
            btn.configure(fg_color=spec["hi"])
        except Exception:  # noqa: BLE001
            pass

    def _leave(_e: Any) -> None:
        if not T.EFFECTS:
            return
        try:
            btn.configure(fg_color=spec["fg"])
        except Exception:  # noqa: BLE001
            pass

    def _press(_e: Any) -> None:
        try:
            btn.configure(fg_color=T.darken(spec["fg"], 0.22),
                          border_color=spec["border"])
        except Exception:  # noqa: BLE001
            pass

    btn.bind("<Enter>", _enter, add="+")
    btn.bind("<Leave>", _leave, add="+")
    btn.bind("<ButtonPress-1>", _press, add="+")
    btn.bind("<ButtonRelease-1>", _enter, add="+")
    return btn


# --------------------------------------------------------------------------- #
# Kartu 3D
# --------------------------------------------------------------------------- #
class Card3D(ctk.CTkFrame):
    """Kartu dengan bayangan, bevel highlight, dan header berjudul."""

    def __init__(self, master: Any, title: str = "", subtitle: str = "",
                 icon: str = "", accent: str = T.ACCENT, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.accent = accent
        self._body: Optional[ctk.CTkFrame] = None

        shadow = ctk.CTkFrame(self, fg_color=T.BEVEL_LO, corner_radius=T.RADIUS + 3)
        shadow.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))

        self.frame = ctk.CTkFrame(
            shadow, fg_color=T.PANEL, corner_radius=T.RADIUS,
            border_width=1, border_color=T.BEVEL_HI,
        )
        self.frame.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))

        if title:
            head = ctk.CTkFrame(self.frame, fg_color="transparent", height=34)
            head.pack(fill="x", padx=T.PAD, pady=(T.PAD - 4, 6))
            head.pack_propagate(False)

            icon_img = icons_mod.action_icon(icon, "hi") if icon else None
            if icon_img is not None:
                _ICON_REFS.append(icon_img)
                ctk.CTkLabel(head, text="", image=icon_img).pack(side="left", padx=(0, 8))

            ctk.CTkLabel(head, text=title, font=T.font(13, "bold"), text_color=T.TEXT,
                         anchor="w").pack(side="left")
            if subtitle:
                ctk.CTkLabel(head, text=subtitle, font=T.font(10), text_color=T.TEXT_3,
                             anchor="w").pack(side="left", padx=(10, 0), pady=(2, 0))

            # aksen tipis di bawah header
            line = ctk.CTkFrame(self.frame, height=2, fg_color=T.BORDER)
            line.pack(fill="x", padx=T.PAD)
            ctk.CTkFrame(line, height=2, width=64, fg_color=accent).place(x=0, y=0)

    def content(self) -> ctk.CTkFrame:
        if self._body is None:
            self._body = ctk.CTkFrame(self.frame, fg_color="transparent")
            self._body.pack(fill="both", expand=True, padx=T.PAD, pady=(10, T.PAD))
        return self._body


# --------------------------------------------------------------------------- #
# Chip statistik 3D
# --------------------------------------------------------------------------- #
class StatChip3D(ctk.CTkFrame):
    """Kotak statistik: nilai besar + label, dengan garis aksen kiri."""

    def __init__(self, master: Any, label: str, value: str = "0",
                 color: str = T.ACCENT, wide: bool = False, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", T.CARD)
        kwargs.setdefault("corner_radius", T.RADIUS_SM)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.BORDER)
        super().__init__(master, **kwargs)

        ctk.CTkFrame(self, width=3, fg_color=color, corner_radius=2).pack(
            side="left", fill="y", padx=(6, 0), pady=8)

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.pack(side="left", fill="both", expand=True, padx=(10, 14), pady=8)
        self.value_lbl = ctk.CTkLabel(box, text=value,
                                      font=T.font(22 if wide else 17, "bold"),
                                      text_color=color, anchor="w")
        self.value_lbl.pack(anchor="w")
        ctk.CTkLabel(box, text=label.upper(), font=T.font(9, "bold"),
                     text_color=T.TEXT_3, anchor="w").pack(anchor="w")

    def set(self, value: Any) -> None:
        text = str(value)
        if self.value_lbl.cget("text") != text:
            self.value_lbl.configure(text=text)


# --------------------------------------------------------------------------- #
# Log berwarna
# --------------------------------------------------------------------------- #
class LogView(tk.Frame):
    TAGS = {
        "ok": T.OK, "avail": T.ACCENT, "claim": T.CLAIM, "bad": T.BAD,
        "taken": T.TAKEN, "warn": T.WARN, "info": T.INFO, "muted": T.TEXT_3,
    }

    def __init__(self, master: Any, height: int = 12, **kwargs: Any) -> None:
        kwargs.setdefault("bg", T.CARD)
        super().__init__(master, highlightthickness=0, **kwargs)
        self.autoscroll = True

        self.text = tk.Text(
            self, bg=T.CARD, fg=T.TEXT, insertbackground=T.ACCENT, relief="flat", bd=0,
            highlightthickness=0, wrap="word", height=height, font=(T.MONO_FAMILY, 10),
            padx=12, pady=10, spacing1=1, spacing3=2,
            selectbackground=T.BORDER_HI, selectforeground=T.TEXT, state="disabled",
        )
        self.scroll = ctk.CTkScrollbar(self, command=self.text.yview, width=12,
                                       button_color=T.BORDER_HI, fg_color=T.CARD)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        for name, color in self.TAGS.items():
            self.text.tag_configure(name, foreground=color)
        self.text.tag_configure("time", foreground=T.TEXT_3)
        self.text.tag_configure("claim_bold", foreground=T.CLAIM, font=(T.MONO_FAMILY, 10, "bold"))

    def _on_scroll(self, first: str, last: str) -> None:
        try:
            self.autoscroll = float(last) >= 0.999
        except (TypeError, ValueError):
            self.autoscroll = True
        self.scroll.set(first, last)

    def write(self, tag: str, message: str, stamp: str = "") -> None:
        tag = tag if tag in self.TAGS else "info"
        self.text.configure(state="normal")
        if stamp:
            self.text.insert("end", f"{stamp}  ", "time")
        self.text.insert("end", message + "\n", (tag, "claim_bold") if tag == "claim" else (tag,))
        try:
            lines = int(self.text.index("end-1c").split(".")[0])
            if lines > 900:
                self.text.delete("1.0", "300.0")
        except Exception:  # noqa: BLE001
            pass
        self.text.configure(state="disabled")
        if self.autoscroll:
            self.text.see("end")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class ListPane(tk.Frame):
    """Daftar read-only bergaris monospace dengan penanda jumlah."""

    def __init__(self, master: Any, height: int = 10, color: str = T.TEXT,
                 **kwargs: Any) -> None:
        kwargs.setdefault("bg", T.CARD)
        super().__init__(master, highlightthickness=0, **kwargs)
        self.count = 0
        self.text = tk.Text(
            self, bg=T.CARD, fg=color, relief="flat", bd=0, highlightthickness=0,
            wrap="none", height=height, font=(T.MONO_FAMILY, 10), padx=12, pady=10,
            selectbackground=T.BORDER_HI, state="disabled", cursor="arrow",
        )
        self.scroll = ctk.CTkScrollbar(self, command=self.text.yview, width=12,
                                       button_color=T.BORDER_HI, fg_color=T.CARD)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

    def append(self, value: str, prefix: str = "•") -> None:
        self.count += 1
        self.text.configure(state="normal")
        self.text.insert("end", f"{prefix} {value}\n")
        self.text.configure(state="disabled")
        self.text.see("end")

    def replace(self, values: Sequence[str], prefix: str = "•") -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for value in values:
            self.text.insert("end", f"{prefix} {value}\n")
        self.text.configure(state="disabled")
        self.count = len(values)


# --------------------------------------------------------------------------- #
# Tab segmented 3D (dipakai di dalam tiap halaman)
# --------------------------------------------------------------------------- #
class SegmentedTabs(ctk.CTkFrame):
    """Sub-tab gaya kapsul dengan indikator geser — hemat CPU (bukan animasi)."""

    def __init__(self, master: Any, height: int = 38, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._frames: Dict[str, ctk.CTkFrame] = {}
        self._order: List[str] = []
        self.active = ""

        self.bar = ctk.CTkFrame(self, fg_color=T.CARD_LO, corner_radius=T.RADIUS_SM,
                                border_width=1, border_color=T.BORDER)
        self.bar.pack(fill="x")
        self.indicator = ctk.CTkFrame(self.bar, fg_color=T.CARD_HI, corner_radius=T.RADIUS_SM - 2,
                                      border_width=1, border_color=T.BORDER_HI)
        self.stack = ctk.CTkFrame(self, fg_color="transparent")
        self.stack.pack(fill="both", expand=True, pady=(10, 0))
        self.stack.grid_rowconfigure(0, weight=1)
        self.stack.grid_columnconfigure(0, weight=1)
        self._indicator_ready = False

    def add(self, key: str, label: str, builder: Optional[Callable[[ctk.CTkFrame], None]] = None
            ) -> ctk.CTkFrame:
        btn = ctk.CTkButton(
            self.bar, text=label, height=30, corner_radius=T.RADIUS_SM - 3,
            fg_color="transparent", hover_color=T.CARD,
            text_color=T.TEXT_3, font=T.font(11, "bold"),
            command=lambda k=key: self.select(k),
        )
        btn.pack(side="left", padx=(6, 0), pady=5)
        self._buttons[key] = btn

        frame = ctk.CTkFrame(self.stack, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        self._frames[key] = frame
        self._order.append(key)
        if builder is not None:
            builder(frame)
        if not self.active:
            self.select(key)
        return frame

    def select(self, key: str) -> None:
        if key not in self._frames:
            return
        self.active = key
        for name, frame in self._frames.items():
            if name == key:
                frame.grid()
            else:
                frame.grid_remove()
            btn = self._buttons[name]
            btn.configure(text_color=T.ACCENT_3 if name == key else T.TEXT_3,
                          font=T.font(11, "bold"))
        self._move_indicator()

    def _move_indicator(self) -> None:
        btn = self._buttons.get(self.active)
        if btn is None:
            return
        try:
            self.update_idletasks()
            x = btn.winfo_x() - 4
            width = btn.winfo_width() + 8
            self.indicator.place(x=max(0, x), y=3, width=width, height=self.bar.winfo_height() - 6)
            self.indicator.lower(self.bar)
            self._indicator_ready = True
        except Exception:  # noqa: BLE001
            pass

    def refresh_labels(self, labels: Dict[str, str]) -> None:
        for key, label in labels.items():
            if key in self._buttons:
                self._buttons[key].configure(text=label)


# --------------------------------------------------------------------------- #
# Baris pengaturan (switch)
# --------------------------------------------------------------------------- #
def switch_row(parent: Any, text: str, command: Callable[[], None],
               color: str = T.ACCENT, initial: bool = False) -> ctk.CTkSwitch:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=3)
    sw = ctk.CTkSwitch(row, text=text, font=T.font(11), progress_color=color,
                       button_color=T.TEXT, button_hover_color=T.ACCENT_3,
                       text_color=T.TEXT_2, command=command)
    sw.pack(anchor="w")
    if initial:
        sw.select()
    return sw


def labeled_entry(parent: Any, label: str, value: str = "", width: int = 150,
                  placeholder: str = "") -> ctk.CTkEntry:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=4)
    ctk.CTkLabel(row, text=label, font=T.font(11), text_color=T.TEXT_2,
                 width=width, anchor="w").pack(side="left")
    entry = ctk.CTkEntry(row, height=34, corner_radius=T.RADIUS_SM, fg_color=T.CARD,
                         border_color=T.BORDER, font=T.font(12),
                         placeholder_text=placeholder)
    entry.pack(side="left", fill="x", expand=True)
    if value:
        entry.insert(0, value)
    return entry


def slider_row(parent: Any, label: str, lo: int, hi: int, value: int,
               width: int = 150) -> Tuple[ctk.CTkSlider, ctk.CTkLabel]:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=6)
    ctk.CTkLabel(row, text=label, font=T.font(11), text_color=T.TEXT_2,
                 width=width, anchor="w").pack(side="left")
    slider = ctk.CTkSlider(row, from_=lo, to=hi, height=16, corner_radius=8,
                           button_color=T.ACCENT, button_hover_color=T.ACCENT_3,
                           progress_color=T.ACCENT_2, fg_color=T.CARD)
    slider.set(value)
    slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
    value_lbl = ctk.CTkLabel(row, text=str(value), font=T.font(11, "bold"),
                             text_color=T.ACCENT, width=40)
    value_lbl.pack(side="left")
    slider.configure(command=lambda v: value_lbl.configure(text=str(int(float(v)))))
    return slider, value_lbl


# --------------------------------------------------------------------------- #
# Toast + dialog
# --------------------------------------------------------------------------- #
class Toast(ctk.CTkFrame):
    def __init__(self, master: Any, message: str, color: str = T.ACCENT) -> None:
        super().__init__(master, fg_color=T.CARD_HI, corner_radius=T.RADIUS_SM,
                         border_width=1, border_color=color)
        ctk.CTkFrame(self, width=4, fg_color=color, corner_radius=2).pack(
            side="left", fill="y", padx=(6, 0), pady=8)
        ctk.CTkLabel(self, text=message, font=T.font(11, "bold"), text_color=color,
                     wraplength=420, justify="left").pack(side="left", padx=12, pady=10)


def claim_modal(app: Any, name: str, account: str, title: str, head: str,
                via: str, ok_text: str) -> None:
    modal = ctk.CTkToplevel(app)
    modal.title(title)
    modal.configure(fg_color=T.BG)
    modal.geometry("460x290")
    modal.resizable(False, False)
    try:
        modal.attributes("-topmost", True)
        modal.transient(app)
    except Exception:  # noqa: BLE001
        pass

    card = ctk.CTkFrame(modal, fg_color=T.PANEL, corner_radius=18, border_width=1,
                        border_color=T.OK)
    card.pack(fill="both", expand=True, padx=16, pady=16)
    logo = icons_mod.logo("small")
    if logo is not None:
        _ICON_REFS.append(logo)
        ctk.CTkLabel(card, text="", image=logo).pack(pady=(16, 0))
    ctk.CTkLabel(card, text=head, font=T.font(15, "bold"), text_color=T.OK).pack(pady=(8, 0))
    ctk.CTkLabel(card, text=name, font=T.font(26, "bold"), text_color=T.ACCENT).pack(pady=(4, 2))
    ctk.CTkLabel(card, text=via.format(account=account), font=T.font(10),
                 text_color=T.TEXT_3).pack()
    button(card, ok_text, modal.destroy, "success", icon="play", width=170, height=40).pack(pady=14)

    modal.update_idletasks()
    x = app.winfo_x() + (app.winfo_width() - 460) // 2
    y = app.winfo_y() + (app.winfo_height() - 290) // 3
    modal.geometry(f"+{max(0, x)}+{max(0, y)}")
