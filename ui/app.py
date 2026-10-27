"""
app.py — GUI Varin Sniper (dark purple gradient, efek 3D, bilingual).

Susunan baru:
  * sidebar   : logo, navigasi berikon (indikator geser), pemilih bahasa,
                saklar wallpaper/efek 3D, kartu status mesin.
  * hero      : banner 3D live (wireframe vault + partikel kedalaman) dengan
                judul aplikasi digambar langsung di kanvas.
  * deck      : pil status, tombol START/STOP 3D, dan chip statistik.
  * pages     : 7 halaman; halaman besar dipecah lagi jadi sub-tab kapsul
                (SegmentedTabs) supaya tidak menumpuk dalam satu layar.
  * footer    : ringkasan mesin (uptime, checks/s, proxy, discord).

Semua teks diambil dari ui.i18n (English default, Indonesia tersedia).
Mengganti bahasa membangun ulang seluruh UI lalu mengembalikan isi (log,
daftar available/claimed, akun, proxy, riwayat) dari state controller.
"""
from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

from checker import Checker, CheckResult, NameStatus
from controller import AVAILABLE_FILE, CLAIMED_FILE, SniperController, now_hms
from generator import (
    enumerate_ordered, generate_pattern, generate_random, generate_smart_random,
    get_pattern_examples,
)
from proxy import ProxyManager
import claimer as clm
from scan_history import (
    STATUS_AVAILABLE, STATUS_CLAIMED, STATUS_ERROR, STATUS_RATE_LIMITED,
    STATUS_TAKEN, STATUS_UNKNOWN,
)
from ui import icons as icons_mod
from ui import theme as T
from ui.i18n import LANGUAGE_NAMES, LANGUAGES, t
from ui.wallpaper import LiveWallpaper3D
from ui.widgets import (
    Card3D, ListPane, LogView, SegmentedTabs, StatChip3D, Toast, button,
    claim_modal, labeled_entry, slider_row, switch_row,
)
from utils import append_to_file, load_names_from_file, save_config

PAGES: Tuple[str, ...] = ("checker", "sniper", "accounts", "proxies", "history", "settings", "stats")

HISTORY_STATUSES: Tuple[str, ...] = (
    STATUS_AVAILABLE, STATUS_TAKEN, STATUS_ERROR, STATUS_UNKNOWN,
    STATUS_RATE_LIMITED, STATUS_CLAIMED,
)


class HistoryPane(ctk.CTkFrame):
    """Daftar riwayat SQLite dengan filter status + rescan/hapus (bilingual)."""

    def __init__(self, master: Any, app: "VarinSniperApp") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.controller = app.controller
        self.sh = app.controller.scan_history
        self._filter = "__all__"

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(bar, text=t("hist.filter"), font=T.font(10, "bold"),
                     text_color=T.TEXT_3).pack(side="left", padx=(0, 8))

        self._labels = {t("hist.filter_all"): "__all__"}
        for status in HISTORY_STATUSES:
            self._labels[status] = status
        self.opt = ctk.CTkOptionMenu(
            bar, values=[t("hist.filter_all")] + list(HISTORY_STATUSES), width=180,
            height=32, corner_radius=T.RADIUS_SM, font=T.font(10), fg_color=T.CARD,
            button_color=T.CARD_HI, button_hover_color=T.BORDER_HI,
            dropdown_fg_color=T.PANEL, command=self._on_filter,
        )
        self.opt.set(t("hist.filter_all"))
        self.opt.pack(side="left", padx=(0, 10))
        button(bar, t("hist.btn_rescan"), self._rescan, "soft", icon="refresh",
               width=190, height=32, font_size=10).pack(side="left", padx=(0, 8))
        button(bar, t("hist.btn_delete"), self._delete, "danger", icon="trash",
               width=150, height=32, font_size=10).pack(side="left")

        self.text = tk.Text(
            self, bg=T.CARD, fg=T.TEXT, relief="flat", bd=0, highlightthickness=0,
            wrap="none", font=(T.MONO_FAMILY, 10), padx=12, pady=10,
            selectbackground=T.BORDER_HI, selectforeground=T.TEXT, state="disabled",
        )
        self.scroll = ctk.CTkScrollbar(self, command=self.text.yview, width=12,
                                       button_color=T.BORDER_HI, fg_color=T.CARD)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.scroll.pack(side="right", fill="y", padx=(0, 8))

        self.text.tag_configure("avail", foreground=T.OK)
        self.text.tag_configure("taken", foreground=T.TAKEN)
        self.text.tag_configure("error", foreground=T.BAD)
        self.text.tag_configure("unknown", foreground=T.WARN)
        self.text.tag_configure("rate", foreground=T.WARN)
        self.text.tag_configure("claimed", foreground=T.CLAIM)
        self.reload()

    # -- data -------------------------------------------------------------- #
    def _rows(self) -> List[Dict[str, Any]]:
        if self._filter == "__all__":
            return self.sh.list_all()
        return self.sh.list_by_status(self._filter)

    def reload(self) -> None:
        rows = self._rows()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for row in rows:
            stamp = time.strftime("%Y-%m-%d %H:%M",
                                  time.localtime(row.get("scanned_at", 0)))
            tag = {
                STATUS_AVAILABLE: "avail",
                STATUS_TAKEN: "taken",
                STATUS_ERROR: "error",
                STATUS_UNKNOWN: "unknown",
                STATUS_RATE_LIMITED: "rate",
                STATUS_CLAIMED: "claimed",
            }.get(row["status"], "unknown")
            self.text.insert("end", f"{stamp}  {row['name']:<16}  {row['status']}\n", (tag,))
        self.text.configure(state="disabled")
        self.text.see("end")

    def _on_filter(self, label: str) -> None:
        self._filter = self._labels.get(label, "__all__")
        self.reload()

    def _rescan(self) -> None:
        names = [r["name"] for r in self._rows()
                 if r["status"] in (STATUS_ERROR, STATUS_UNKNOWN, STATUS_RATE_LIMITED)]
        if not names:
            self.controller.emit("log", ("info", t("log.rescan_none")))
            return
        added = self.controller.enqueue_many(names)
        self.controller.emit("log", ("ok", t("log.rescan", n=added)))
        self.reload()

    def _delete(self) -> None:
        removed = 0
        for row in self._rows():
            if row["status"] in (STATUS_ERROR, STATUS_UNKNOWN):
                self.sh.delete(row["name"])
                removed += 1
        self.controller.emit("log", ("warn", t("log.history_deleted", n=removed)))
        self.reload()


class VarinSniperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=T.BG)
        self.title(t("app.window_title"))
        self.geometry("1520x950")
        self.minsize(1240, 780)
        self._center(1520, 950)
        icons_mod.set_window_icon(self)

        self.controller = SniperController()
        self.cfg = self.controller.config

        # bahasa & efek 3D mengikuti config (default: English, efek aktif)
        from ui import i18n
        i18n.set_language(self.cfg.get("language", "en"))
        T.set_effects(bool(self.cfg.get("effects_3d", True)))

        # state yang harus selamat saat UI dibangun ulang (ganti bahasa)
        self._log_lines: List[Tuple[str, str, str]] = []
        self._available: List[str] = []
        self._claimed: List[str] = []
        self._watch: List[str] = []

        self.active = "checker"
        self._toast: Optional[Toast] = None
        self._wallpapers: List[LiveWallpaper3D] = []
        self._nav_items: Dict[str, Dict[str, Any]] = {}
        self._hero: Optional[tk.Canvas] = None
        self._hero_wall: Optional[LiveWallpaper3D] = None
        self._resize_job: Optional[str] = None
        self._spinner_idx = 0
        self._side_grad: Optional[object] = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_ui()
        self._sync_state_to_ui()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-Return>", lambda _e: self._start())
        self.bind("<Escape>", lambda _e: self._stop())
        self.bind("<FocusIn>", lambda _e: self._resume_wallpaper())
        self.bind("<FocusOut>", lambda _e: self._pause_wallpaper())
        self.bind("<Unmap>", lambda _e: self._pause_wallpaper())
        self.after(90, self._pump_events)
        self.after(450, self._tick)

        self._log("info", t("log.ready", name=t("app.name"), version=t("app.version"),
                            accounts=len(self.controller.accounts),
                            proxies=len(self.controller.proxies)))

    # ------------------------------------------------------------------ #
    # Pembangunan UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self._build_sidebar()
        self._build_main()
        self._switch_page(self.active, animate=False)

    def _rebuild(self) -> None:
        """Bangun ulang seluruh UI (dipakai saat bahasa berubah)."""
        for wall in list(self._wallpapers):
            wall.stop()
        self._wallpapers.clear()
        self._nav_items.clear()
        try:
            self.sidebar.destroy()
            self.main.destroy()
        except Exception:  # noqa: BLE001
            pass
        self._hero = None
        self._hero_wall = None
        self._toast = None
        self.title(t("app.window_title"))   # judul ikut bahasa baru
        self._build_ui()
        self._sync_state_to_ui()

    def _center(self, width: int, height: int) -> None:
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{width}x{height}+{max(0, (sw - width) // 2)}+{max(0, (sh - height) // 3)}")
        except Exception:  # noqa: BLE001
            pass

    # -- sidebar -------------------------------------------------------- #
    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=T.SIDEBAR_W, corner_radius=0, fg_color=T.SIDEBAR)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        self.sidebar = side

        # gradient latar (label dibuat duluan supaya berada di belakang widget lain)
        try:
            self._side_grad = T.gradient_photo(T.SIDEBAR_W, 1400, T.SIDEBAR_2, T.SIDEBAR)
            tk.Label(side, image=self._side_grad, bd=0, bg=T.SIDEBAR).place(
                x=0, y=0, relwidth=1, relheight=1)
        except Exception:  # noqa: BLE001
            pass

        self.nav_indicator = ctk.CTkFrame(side, width=4, height=34, corner_radius=2,
                                          fg_color=T.ACCENT)
        self.nav_indicator.place(x=8, y=60)

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(22, 6))
        logo_img = icons_mod.logo("small")
        if logo_img is not None:
            ctk.CTkLabel(head, text="", image=logo_img).pack(side="left", padx=(0, 12))
        name_box = ctk.CTkFrame(head, fg_color="transparent")
        name_box.pack(side="left")
        ctk.CTkLabel(name_box, text=t("app.name"), font=T.font(19, "bold"),
                     text_color=T.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(name_box, text=t("app.version"), font=T.font(10, "bold"),
                     text_color=T.ACCENT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(side, text=t("app.tagline"), font=T.font(9, "bold"), text_color=T.TEXT_3,
                     anchor="w").pack(anchor="w", padx=18)

        ctk.CTkFrame(side, height=1, fg_color=T.BORDER).pack(fill="x", padx=18, pady=(14, 10))

        for page in PAGES:
            wrap = ctk.CTkFrame(side, fg_color="transparent", height=46)
            wrap.pack(fill="x", padx=12, pady=2)
            wrap.pack_propagate(False)
            btn = ctk.CTkButton(
                wrap, text="  " + t(f"nav.{page}"), anchor="w", height=42,
                corner_radius=T.RADIUS_SM, fg_color="transparent", hover_color=T.CARD,
                text_color=T.TEXT_2, font=T.font(13, "bold"), border_width=0,
                image=icons_mod.nav_icon(page, False), compound="left",
                command=lambda p=page: self._switch_page(p),
            )
            btn.pack(fill="both", expand=True)
            self._nav_items[page] = {"btn": btn, "wrap": wrap}

        lang_box = ctk.CTkFrame(side, fg_color="transparent")
        lang_box.pack(fill="x", padx=18, pady=(16, 0))
        ctk.CTkLabel(lang_box, text=t("side.language"), font=T.font(10, "bold"),
                     text_color=T.TEXT_3, anchor="w").pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(lang_box, fg_color=T.CARD_LO, corner_radius=T.RADIUS_SM,
                           border_width=1, border_color=T.BORDER)
        row.pack(fill="x")
        for code in LANGUAGES:
            active = code == t.lang
            ctk.CTkButton(
                row, text=("EN" if code == "en" else "ID"), height=28, width=56,
                corner_radius=T.RADIUS_SM - 3,
                fg_color=T.CARD_HI if active else "transparent", hover_color=T.CARD_HI,
                font=T.font(11, "bold"), text_color=T.ACCENT_3 if active else T.TEXT_3,
                border_width=0, command=lambda c=code: self._set_language(c),
            ).pack(side="left", padx=4, pady=4)
        ctk.CTkLabel(lang_box, text=LANGUAGE_NAMES.get(t.lang, "English"), font=T.font(9),
                     text_color=T.TEXT_3, anchor="w").pack(anchor="w", pady=(4, 0))

        view_box = ctk.CTkFrame(side, fg_color="transparent")
        view_box.pack(side="bottom", fill="x", padx=18, pady=(0, 12))
        self.sw_wallpaper = ctk.CTkSwitch(
            view_box, text=t("app.wallpaper"), font=T.font(11), progress_color=T.ACCENT,
            button_color=T.TEXT, button_hover_color=T.ACCENT_3, text_color=T.TEXT_2,
            command=self._toggle_wallpaper)
        self.sw_wallpaper.pack(anchor="w")
        if self.cfg.get("wallpaper_3d", True):
            self.sw_wallpaper.select()
        self.sw_effects = ctk.CTkSwitch(
            view_box, text=t("side.depth_effects"), font=T.font(11), progress_color=T.ACCENT_2,
            button_color=T.TEXT, button_hover_color=T.ACCENT_3, text_color=T.TEXT_2,
            command=self._toggle_effects)
        self.sw_effects.pack(anchor="w", pady=(6, 0))
        if self.cfg.get("effects_3d", True):
            self.sw_effects.select()
        ctk.CTkFrame(view_box, height=1, fg_color=T.BORDER).pack(fill="x", pady=(12, 8))
        ctk.CTkLabel(view_box, text=f"{t('app.name')}  {t('app.version')}", font=T.font(9),
                     text_color=T.TEXT_3, anchor="w").pack(anchor="w")

        status_card = ctk.CTkFrame(side, fg_color=T.PANEL, corner_radius=T.RADIUS_SM,
                                   border_width=1, border_color=T.BEVEL_HI)
        status_card.pack(side="bottom", fill="x", padx=16, pady=(0, 10))
        inner = ctk.CTkFrame(status_card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        self.side_status = ctk.CTkLabel(inner, text="● " + t("side.status_idle"),
                                        font=T.font(11, "bold"), text_color=T.WARN, anchor="w")
        self.side_status.pack(fill="x")
        self.side_uptime = ctk.CTkLabel(inner, text=t("side.uptime", value="00:00:00"),
                                        font=T.font(10), text_color=T.TEXT_3, anchor="w")
        self.side_uptime.pack(fill="x", pady=(3, 0))
        self.side_queue = ctk.CTkLabel(inner, text=t("side.queue", value=0), font=T.font(10),
                                       text_color=T.TEXT_3, anchor="w")
        self.side_queue.pack(fill="x")

    # -- main area ------------------------------------------------------ #
    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=T.BG_2, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        self.main = main

        self._build_hero(main)
        self._build_deck(main)

        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=16, pady=(12, 0))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        builders = {
            "checker": self._page_checker,
            "sniper": self._page_sniper,
            "accounts": self._page_accounts,
            "proxies": self._page_proxies,
            "history": self._page_history,
            "settings": self._page_settings,
            "stats": self._page_stats,
        }
        self.pages: Dict[str, ctk.CTkFrame] = {}
        for page in PAGES:
            frame = ctk.CTkFrame(self.content, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            builders[page](frame)
            self.pages[page] = frame

        self._build_footer(main)

    def _build_hero(self, parent: ctk.CTkFrame) -> None:
        hero = tk.Canvas(parent, height=T.HERO_H, bg=T.BG, highlightthickness=0, bd=0)
        hero.grid(row=0, column=0, sticky="ew")
        self._hero = hero

        wall = LiveWallpaper3D(hero, 1200, T.HERO_H,
                              enabled=bool(self.cfg.get("wallpaper_3d", True)))
        self._hero_wall = wall
        self._wallpapers.append(wall)

        hero.create_text(30, T.HERO_H * 0.40, anchor="w", text=t("app.name"), fill=T.TEXT,
                         font=T.font(30, "bold"), tags="hero")
        hero.create_text(32, T.HERO_H * 0.66, anchor="w", text=t("app.subtitle"),
                         fill=T.ACCENT_3, font=T.font(11), tags="hero")
        self._hero_status = hero.create_text(
            1170, T.HERO_H * 0.42, anchor="e", text="● " + t("head.status_idle"),
            fill=T.WARN, font=T.font(13, "bold"), tags="hero")
        self._hero_progress = hero.create_text(
            1170, T.HERO_H * 0.66, anchor="e", text=t("head.progress_idle"),
            fill=T.TEXT_3, font=T.font(10), tags="hero")

        hero.bind("<Configure>", self._on_hero_resize)
        if wall.enabled:
            wall.start()

    def _on_hero_resize(self, event: Any) -> None:
        if self._hero_wall is None:
            return
        self._hero_wall.configure_size(event.width, event.height)
        try:
            if self._hero is not None:
                self._hero.coords(self._hero_status, event.width - 30, event.height * 0.42)
                self._hero.coords(self._hero_progress, event.width - 30, event.height * 0.66)
        except Exception:  # noqa: BLE001
            pass

    def _build_deck(self, parent: ctk.CTkFrame) -> None:
        deck = ctk.CTkFrame(parent, fg_color=T.PANEL, corner_radius=T.RADIUS,
                            border_width=1, border_color=T.BEVEL_HI)
        deck.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
        inner = ctk.CTkFrame(deck, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left")
        pill = ctk.CTkFrame(left, fg_color=T.CARD_LO, corner_radius=T.RADIUS_SM,
                            border_width=1, border_color=T.BORDER)
        pill.pack(anchor="w")
        self.status_dot = ctk.CTkLabel(pill, text="●", font=T.font(12), text_color=T.WARN)
        self.status_dot.pack(side="left", padx=(10, 4), pady=5)
        self.status_text = ctk.CTkLabel(pill, text=t("head.status_idle"), font=T.font(10, "bold"),
                                        text_color=T.TEXT_2)
        self.status_text.pack(side="left", padx=(0, 10), pady=5)
        self.page_title = ctk.CTkLabel(left, text="", font=T.font(11), text_color=T.TEXT_3,
                                       anchor="w")
        self.page_title.pack(anchor="w", pady=(6, 0))

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(side="right", padx=(12, 0))
        self.btn_start = button(actions, t("btn.start"), self._start, "success", icon="play",
                                width=150, height=52, font_size=14)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_stop = button(actions, t("btn.stop"), self._stop, "danger", icon="stop",
                               width=136, height=52, font_size=14)
        self.btn_stop.pack(side="left")
        self.btn_stop.configure(state="disabled")

        chips = ctk.CTkFrame(right, fg_color="transparent")
        chips.pack(side="right")
        self.chips: Dict[str, StatChip3D] = {}
        for key, label_key, color in (
            ("checked", "chip.checked", T.TEXT),
            ("available", "chip.available", T.ACCENT),
            ("claimed", "chip.claimed", T.OK),
            ("queue", "chip.queue", T.WARN),
            ("threads", "chip.threads", T.ACCENT_2),
        ):
            chip = StatChip3D(chips, t(label_key), "0", color)
            chip.pack(side="left", padx=(0, 8))
            self.chips[key] = chip

    def _build_footer(self, parent: ctk.CTkFrame) -> None:
        footer = ctk.CTkFrame(parent, fg_color="transparent", height=28)
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=(6, 10))
        self.foot_left = ctk.CTkLabel(footer, text="", font=T.font(10), text_color=T.TEXT_3)
        self.foot_left.pack(side="left")
        self.foot_right = ctk.CTkLabel(footer, text="", font=T.font(10), text_color=T.TEXT_3)
        self.foot_right.pack(side="right")

    # ------------------------------------------------------------------ #
    # Navigasi & preferensi tampilan
    # ------------------------------------------------------------------ #
    def _switch_page(self, page: str, animate: bool = True) -> None:
        if page not in self.pages:
            return
        self.active = page
        for key, frame in self.pages.items():
            if key == page:
                frame.grid()
            else:
                frame.grid_remove()
        for key, item in self._nav_items.items():
            active = key == page
            try:
                item["btn"].configure(
                    fg_color=T.CARD_HI if active else "transparent",
                    text_color=T.ACCENT_3 if active else T.TEXT_2,
                    image=icons_mod.nav_icon(key, active),
                )
            except Exception:  # noqa: BLE001
                pass
        try:
            self.page_title.configure(text=t(f"nav.{page}").upper())
        except Exception:  # noqa: BLE001
            pass
        self._move_nav_indicator(animate)
        if page == "history":
            self._reload_history_pane()

    def _move_nav_indicator(self, animate: bool = True) -> None:
        item = self._nav_items.get(self.active)
        if item is None:
            return
        try:
            self.update_idletasks()
            target = item["wrap"].winfo_y() + 6
            current = self.nav_indicator.winfo_y()
            self.nav_indicator.lift()
            if not animate or abs(target - current) < 2:
                self.nav_indicator.place(x=8, y=target, width=4, height=34)
                return
            steps = 6

            def step(i: int) -> None:
                ratio = T.ease_out_cubic(i / steps)
                y = T.lerp(current, target, ratio)
                try:
                    self.nav_indicator.place(x=8, y=y, width=4, height=34)
                except Exception:  # noqa: BLE001
                    return
                if i < steps:
                    self.after(16, lambda: step(i + 1))

            step(1)
        except Exception:  # noqa: BLE001
            pass

    def _set_language(self, code: str) -> None:
        from ui import i18n
        if not i18n.set_language(code):
            return
        self.cfg["language"] = code
        save_config(self.cfg)
        self._rebuild()
        self._toast_message(t("toast.language", language=LANGUAGE_NAMES.get(code, code)), T.ACCENT)

    def _apply_wallpaper(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.cfg["wallpaper_3d"] = enabled
        save_config(self.cfg)
        for wall in list(self._wallpapers):
            wall.set_enabled(enabled)
        try:
            if enabled:
                self.sw_wallpaper.select()
            else:
                self.sw_wallpaper.deselect()
        except Exception:  # noqa: BLE001
            pass

    def _toggle_wallpaper(self) -> None:
        """Saklar di sidebar."""
        self._apply_wallpaper(bool(self.sw_wallpaper.get()))

    def _toggle_wallpaper_cfg(self) -> None:
        """Saklar di halaman Settings."""
        self._apply_wallpaper(bool(self.sw_wallpaper_cfg.get()))

    def _apply_effects(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.cfg["effects_3d"] = enabled
        save_config(self.cfg)
        T.set_effects(enabled)
        try:
            if enabled:
                self.sw_effects.select()
            else:
                self.sw_effects.deselect()
        except Exception:  # noqa: BLE001
            pass

    def _toggle_effects(self) -> None:
        """Saklar di sidebar."""
        self._apply_effects(bool(self.sw_effects.get()))

    def _toggle_effects_cfg(self) -> None:
        """Saklar di halaman Settings."""
        self._apply_effects(bool(self.sw_effects_cfg.get()))

    def _pause_wallpaper(self) -> None:
        for wall in list(self._wallpapers):
            wall.pause()

    def _resume_wallpaper(self) -> None:
        for wall in list(self._wallpapers):
            wall.resume()

    # ------------------------------------------------------------------ #
    # Halaman: Checker
    # ------------------------------------------------------------------ #
    def _page_checker(self, page: ctk.CTkFrame) -> None:
        tabs = SegmentedTabs(page)
        tabs.pack(fill="both", expand=True)

        def build_target(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("checker.entry_title"), t("checker.entry_sub"),
                          icon="search", accent=T.ACCENT)
            card.pack(fill="both", expand=True)
            body = card.content()

            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x")
            self.ent_check = ctk.CTkEntry(
                row, placeholder_text=t("checker.placeholder"), height=44,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(13))
            self.ent_check.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.ent_check.bind("<Return>", lambda _e: self._check_single())
            button(row, t("checker.btn_check"), self._check_single, "soft", icon="search",
                   width=126, height=44).pack(side="left", padx=(0, 8))
            button(row, t("checker.btn_add"), self._add_target, "primary", icon="plus",
                   width=124, height=44).pack(side="left")

            gen = ctk.CTkFrame(body, fg_color="transparent")
            gen.pack(fill="x", pady=(12, 0))
            for text_key, cmd, variant, icon in (
                ("checker.gen_load", self._load_txt, "ghost", "folder"),
                ("checker.gen_3l", lambda: self._gen_names(3), "ghost", "sparkle"),
                ("checker.gen_4l", lambda: self._gen_names(4), "ghost", "sparkle"),
                ("checker.gen_3l_full", self._gen_full_3l, "soft", "sniper"),
                ("checker.gen_smart", self._gen_smart_rare, "ghost", "sparkle"),
            ):
                button(gen, t(text_key), cmd, variant, icon=icon, height=34,
                       font_size=11).pack(side="left", padx=(0, 6))

            pattern_row = ctk.CTkFrame(body, fg_color="transparent")
            pattern_row.pack(fill="x", pady=(12, 0))
            ctk.CTkLabel(pattern_row, text=t("checker.pattern"), font=T.font(10, "bold"),
                         text_color=T.TEXT_3).pack(side="left", padx=(0, 8))
            examples = get_pattern_examples()
            self.ent_pattern = ctk.CTkEntry(
                pattern_row, placeholder_text=examples[0] if examples else "a_d", height=34,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(11))
            self.ent_pattern.pack(side="left", fill="x", expand=True, padx=(0, 8))
            button(pattern_row, t("checker.btn_generate"), self._gen_pattern, "ghost",
                   icon="sparkle", width=150, height=34, font_size=11).pack(side="left")

            queue_row = ctk.CTkFrame(body, fg_color="transparent")
            queue_row.pack(fill="x", pady=(16, 0))
            self.lbl_queue_total = ctk.CTkLabel(queue_row, text=t("checker.queue_waiting", n=0),
                                                font=T.font(12, "bold"), text_color=T.WARN)
            self.lbl_queue_total.pack(side="left")
            self.progress = ctk.CTkProgressBar(queue_row, height=8, corner_radius=4,
                                               progress_color=T.ACCENT, fg_color=T.CARD_LO)
            self.progress.pack(side="left", fill="x", expand=True, padx=16)
            self.progress.set(0)
            button(queue_row, t("checker.btn_clear"), self._clear_queue, "danger", icon="trash",
                   width=180, height=32, font_size=11).pack(side="right")

        def build_results(frame: ctk.CTkFrame) -> None:
            frame.grid_columnconfigure((0, 1), weight=1, uniform="res")
            frame.grid_rowconfigure(0, weight=1)

            avail_card = Card3D(frame, t("checker.avail_title"), t("checker.avail_sub"),
                                icon="export", accent=T.OK)
            avail_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            avail_body = avail_card.content()
            self.avail_box = ListPane(avail_body, height=13, color=T.ACCENT)
            self.avail_box.pack(fill="both", expand=True)
            avail_row = ctk.CTkFrame(avail_body, fg_color="transparent")
            avail_row.pack(fill="x", pady=(8, 0))
            self.lbl_avail_count = ctk.CTkLabel(avail_row, text=t("checker.found", n=0),
                                                font=T.font(10, "bold"), text_color=T.ACCENT)
            self.lbl_avail_count.pack(side="left")
            button(avail_row, t("checker.btn_export"), lambda: self._export(AVAILABLE_FILE),
                   "ghost", icon="export", width=130, height=30,
                   font_size=10).pack(side="right")

            claimed_card = Card3D(frame, t("checker.claimed_title"), t("checker.claimed_sub"),
                                  icon="key", accent=T.OK)
            claimed_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
            claimed_body = claimed_card.content()
            self.claimed_box = ListPane(claimed_body, height=13, color=T.OK)
            self.claimed_box.pack(fill="both", expand=True)
            claimed_row = ctk.CTkFrame(claimed_body, fg_color="transparent")
            claimed_row.pack(fill="x", pady=(8, 0))
            self.lbl_claimed_count = ctk.CTkLabel(claimed_row,
                                                  text=t("checker.claimed_count", n=0),
                                                  font=T.font(10, "bold"), text_color=T.OK)
            self.lbl_claimed_count.pack(side="left")
            button(claimed_row, t("checker.btn_export"), lambda: self._export(CLAIMED_FILE),
                   "ghost", icon="export", width=130, height=30,
                   font_size=10).pack(side="right")

        tabs.add("target", t("sub.target"), build_target)
        tabs.add("results", t("sub.results"), build_results)

    # ------------------------------------------------------------------ #
    # Halaman: Sniper
    # ------------------------------------------------------------------ #
    def _page_sniper(self, page: ctk.CTkFrame) -> None:
        tabs = SegmentedTabs(page)
        tabs.pack(fill="both", expand=True)

        def build_claim(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("sniper.claim_title"), t("sniper.claim_sub"),
                          icon="sniper", accent=T.OK)
            card.pack(fill="both", expand=True)
            body = card.content()
            self.sw_auto_claim = switch_row(
                body, t("sniper.sw_auto_claim"), self._toggle_auto_claim, T.OK,
                bool(self.cfg.get("auto_claim")))
            self.sw_watch = switch_row(
                body, t("sniper.sw_watch"), self._toggle_watch, T.ACCENT,
                bool(self.cfg.get("watch_mode", True)))
            ctk.CTkLabel(body, text=t("sniper.claim_status").upper(), font=T.font(10, "bold"),
                         text_color=T.TEXT_3, anchor="w").pack(fill="x", pady=(12, 4))
            self.log_box = LogView(body, height=12)
            self.log_box.pack(fill="both", expand=True)

        def build_watch(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("sniper.watch_title"), t("sniper.watch_sub"),
                          icon="checker", accent=T.WARN)
            card.pack(fill="both", expand=True)
            body = card.content()
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(0, 8))
            self.ent_watch = ctk.CTkEntry(row, placeholder_text=t("sniper.watch_placeholder"),
                                          height=38, corner_radius=T.RADIUS_SM, fg_color=T.CARD,
                                          border_color=T.BORDER, font=T.font(12))
            self.ent_watch.pack(side="left", fill="x", expand=True, padx=(0, 8))
            button(row, t("sniper.btn_watch"), self._add_watch, "primary", icon="plus",
                   width=130, height=38).pack(side="left")
            self.watch_box = ListPane(body, height=12, color=T.WARN)
            self.watch_box.pack(fill="both", expand=True)

        def build_live(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("sniper.live_title"), t("sniper.live_sub"),
                          icon="stats", accent=T.CLAIM)
            card.pack(fill="both", expand=True)
            self.activity_box = LogView(card.content(), height=12)
            self.activity_box.pack(fill="both", expand=True)

        tabs.add("claim", t("sub.claim"), build_claim)
        tabs.add("watch", t("sub.watch"), build_watch)
        tabs.add("live", t("sub.live"), build_live)

    # ------------------------------------------------------------------ #
    # Halaman: Accounts
    # ------------------------------------------------------------------ #
    def _page_accounts(self, page: ctk.CTkFrame) -> None:
        tabs = SegmentedTabs(page)
        tabs.pack(fill="both", expand=True)

        def build_login(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("acc.add_title"), t("acc.add_sub"), icon="key", accent=T.OK)
            card.pack(fill="both", expand=True)
            body = card.content()

            ep_row = ctk.CTkFrame(body, fg_color="transparent")
            ep_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(ep_row, text=t("acc.email"), font=T.font(10, "bold"),
                         text_color=T.TEXT_3, width=76, anchor="w").pack(side="left")
            self.ent_ep_email = ctk.CTkEntry(
                ep_row, placeholder_text=t("acc.email_placeholder"), height=40,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(12))
            self.ent_ep_email.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ctk.CTkLabel(ep_row, text=t("acc.password"), font=T.font(10, "bold"),
                         text_color=T.TEXT_3, width=84, anchor="w").pack(side="left")
            self.ent_ep_password = ctk.CTkEntry(
                ep_row, placeholder_text=t("acc.password_placeholder"), height=40,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(12), show="•")
            self.ent_ep_password.pack(side="left", fill="x", expand=True, padx=(0, 10))
            button(ep_row, t("acc.btn_login"), self._add_email_password_account, "success",
                   icon="key", width=200, height=40).pack(side="left")

            label_row = ctk.CTkFrame(body, fg_color="transparent")
            label_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(label_row, text=t("acc.label"), font=T.font(10, "bold"),
                         text_color=T.TEXT_3, width=76, anchor="w").pack(side="left")
            self.ent_acc_label = ctk.CTkEntry(
                label_row, placeholder_text=t("acc.label_placeholder"), height=36,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(12))
            self.ent_acc_label.pack(side="left", fill="x", expand=True, padx=(10, 0))

            token_row = ctk.CTkFrame(body, fg_color="transparent")
            token_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(token_row, text=t("acc.token"), font=T.font(10, "bold"),
                         text_color=T.TEXT_3, width=76, anchor="w").pack(side="left")
            self.ent_token = ctk.CTkEntry(
                token_row, placeholder_text=t("acc.token_placeholder"), height=40,
                corner_radius=T.RADIUS_SM, fg_color=T.CARD, border_color=T.BORDER,
                font=T.font(11))
            self.ent_token.pack(side="left", fill="x", expand=True, padx=(0, 12))
            self.opt_token_type = ctk.CTkOptionMenu(
                token_row, values=[t("acc.token_type_auto"), "mc_token", "ms_token"],
                width=160, height=38, corner_radius=T.RADIUS_SM, fg_color=T.CARD,
                button_color=T.CARD_HI, button_hover_color=T.BORDER_HI,
                dropdown_fg_color=T.PANEL, dropdown_hover_color=T.CARD_HI, font=T.font(11))
            self.opt_token_type.set(t("acc.token_type_auto"))
            self.opt_token_type.pack(side="left")

            action_row = ctk.CTkFrame(body, fg_color="transparent")
            action_row.pack(fill="x")
            button(action_row, t("acc.btn_token"), self._add_token_account, "primary",
                   icon="plus", width=200, height=40).pack(side="left", padx=(0, 10))
            self.lbl_acc_hint = ctk.CTkLabel(action_row, text="", font=T.font(10),
                                             text_color=T.TEXT_3)
            self.lbl_acc_hint.pack(side="left")

        def build_list(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("acc.list_title"), t("acc.list_sub"), icon="accounts",
                          accent=T.ACCENT)
            card.pack(fill="both", expand=True)
            body = card.content()
            self.accounts_box = ListPane(body, height=11, color=T.TEXT)
            self.accounts_box.pack(fill="both", expand=True)
            btn_row = ctk.CTkFrame(body, fg_color="transparent")
            btn_row.pack(fill="x", pady=(8, 0))
            button(btn_row, t("acc.btn_refresh"), self._refresh_all_tokens, "soft",
                   icon="refresh", width=190, height=32, font_size=11).pack(side="left", padx=(0, 8))
            button(btn_row, t("acc.btn_reload"), self._reload_accounts, "ghost", icon="folder",
                   width=150, height=32, font_size=11).pack(side="left")
            button(btn_row, t("acc.btn_clear"), self._clear_all_accounts, "danger", icon="trash",
                   width=150, height=32, font_size=11).pack(side="right")

        tabs.add("login", t("sub.login"), build_login)
        tabs.add("accounts", t("sub.accounts"), build_list)

    # ------------------------------------------------------------------ #
    # Halaman: Proxies
    # ------------------------------------------------------------------ #
    def _page_proxies(self, page: ctk.CTkFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        ctrl = Card3D(page, t("proxy.title"), t("proxy.sub"), icon="proxies", accent=T.ACCENT_2)
        ctrl.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        body = ctrl.content()
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        button(row, t("proxy.btn_load"), self._load_proxies, "primary", icon="folder",
               width=210, height=38).pack(side="left", padx=(0, 8))
        button(row, t("proxy.btn_test"), self._test_proxies, "soft", icon="refresh",
               width=160, height=38).pack(side="left", padx=(0, 8))
        button(row, t("proxy.btn_clean"), self._clean_proxies, "ghost", icon="trash",
               width=180, height=38).pack(side="left")
        self.sw_proxy_rot = ctk.CTkSwitch(
            row, text=t("proxy.auto_rotate"), font=T.font(11), progress_color=T.ACCENT,
            button_color=T.TEXT, button_hover_color=T.ACCENT_3, text_color=T.TEXT_2,
            command=lambda: self._save_setting("proxy_rotate", bool(self.sw_proxy_rot.get())))
        self.sw_proxy_rot.pack(side="right")
        if self.cfg.get("proxy_rotate", True):
            self.sw_proxy_rot.select()

        self.lbl_proxy_stats = ctk.CTkLabel(body, text=t("proxy.none_loaded"), font=T.font(10),
                                            text_color=T.TEXT_3, anchor="w")
        self.lbl_proxy_stats.pack(fill="x", pady=(10, 0))

        lst = Card3D(page, t("proxy.list_title"), t("proxy.list_sub"), icon="proxies",
                     accent=T.ACCENT_2)
        lst.grid(row=1, column=0, sticky="nsew")
        self.proxy_box = ListPane(lst.content(), height=14, color=T.TEXT_2)
        self.proxy_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Halaman: History
    # ------------------------------------------------------------------ #
    def _page_history(self, page: ctk.CTkFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        card = Card3D(page, t("hist.title"), t("hist.sub"), icon="history", accent=T.CLAIM)
        card.grid(row=0, column=0, sticky="nsew")
        self.history_pane = HistoryPane(card.content(), self)
        self.history_pane.pack(fill="both", expand=True)

    def _reload_history_pane(self) -> None:
        pane = getattr(self, "history_pane", None)
        if pane is not None:
            try:
                pane.reload()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # Halaman: Settings
    # ------------------------------------------------------------------ #
    def _page_settings(self, page: ctk.CTkFrame) -> None:
        tabs = SegmentedTabs(page)
        tabs.pack(fill="both", expand=True)

        def build_performance(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("set.perf_title"), t("set.perf_sub"), icon="stats",
                          accent=T.ACCENT_2)
            card.pack(fill="both", expand=True)
            body = card.content()
            self.sld_threads, _ = slider_row(body, t("set.threads"), 1, 100,
                                             int(self.cfg.get("threads", 15)))
            self.ent_timeout = labeled_entry(body, t("set.timeout"),
                                             str(self.cfg.get("timeout", 10.0)))

        def build_behavior(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("set.behavior_title"), t("set.behavior_sub"),
                          icon="settings", accent=T.OK)
            card.pack(fill="both", expand=True)
            body = card.content()
            self.sw_stealth = switch_row(
                body, t("set.sw_stealth"),
                lambda: self._save_setting("stealth_mode", bool(self.sw_stealth.get())),
                T.ACCENT_2, bool(self.cfg.get("stealth_mode", True)))
            self.sw_sound = switch_row(
                body, t("set.sw_sound"),
                lambda: self._save_setting("sound_notifications", bool(self.sw_sound.get())),
                T.OK, bool(self.cfg.get("sound_notifications")))
            self.sw_auto_claim_cfg = switch_row(
                body, t("set.sw_auto_claim"),
                lambda: self._save_setting("auto_claim", bool(self.sw_auto_claim_cfg.get())),
                T.OK, bool(self.cfg.get("auto_claim")))
            self.sw_watch_cfg = switch_row(
                body, t("set.sw_watch"),
                lambda: self._save_setting("watch_mode", bool(self.sw_watch_cfg.get())),
                T.WARN, bool(self.cfg.get("watch_mode", True)))

        def build_notify(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("set.notify_title"), t("set.notify_sub"), icon="globe",
                          accent=T.INFO)
            card.pack(fill="both", expand=True)
            body = card.content()
            self.ent_webhook = labeled_entry(body, t("set.webhook"),
                                             self.cfg.get("discord_webhook_url", ""),
                                             placeholder=t("set.webhook_placeholder"))
            self.sw_discord = switch_row(
                body, t("set.enable_webhook"),
                lambda: self._save_setting("use_discord_webhook", bool(self.sw_discord.get())),
                T.ACCENT_2, bool(self.cfg.get("use_discord_webhook")))
            self.sw_notify_avail = switch_row(
                body, t("set.notify_avail"),
                lambda: self._save_setting("notify_on_available", bool(self.sw_notify_avail.get())),
                T.ACCENT, bool(self.cfg.get("notify_on_available", True)))
            self.sw_notify_claim = switch_row(
                body, t("set.notify_claim"),
                lambda: self._save_setting("notify_on_claimed", bool(self.sw_notify_claim.get())),
                T.OK, bool(self.cfg.get("notify_on_claimed", True)))

        def build_appearance(frame: ctk.CTkFrame) -> None:
            card = Card3D(frame, t("set.appear_title"), t("set.appear_sub"), icon="sparkle",
                          accent=T.ACCENT)
            card.pack(fill="both", expand=True)
            body = card.content()
            ctk.CTkLabel(body, text=t("set.language"), font=T.font(11, "bold"),
                         text_color=T.TEXT_2, anchor="w").pack(fill="x")
            lang_row = ctk.CTkFrame(body, fg_color="transparent")
            lang_row.pack(fill="x", pady=(6, 4))
            for code in LANGUAGES:
                active = code == t.lang
                button(lang_row, LANGUAGE_NAMES.get(code, code),
                       lambda c=code: self._set_language(c),
                       "primary" if active else "ghost", icon="globe", width=180, height=36,
                       font_size=11).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(body, text=t("set.language_hint"), font=T.font(10), text_color=T.TEXT_3,
                         anchor="w").pack(fill="x", pady=(0, 10))
            self.sw_wallpaper_cfg = switch_row(
                body, t("set.wallpaper"),
                lambda: self._toggle_wallpaper_cfg(), T.ACCENT,
                bool(self.cfg.get("wallpaper_3d", True)))
            ctk.CTkLabel(body, text=t("set.wallpaper_hint"), font=T.font(10),
                         text_color=T.TEXT_3, anchor="w").pack(fill="x", pady=(0, 10))
            self.sw_effects_cfg = switch_row(
                body, t("set.effects"),
                lambda: self._toggle_effects_cfg(), T.ACCENT_2,
                bool(self.cfg.get("effects_3d", True)))
            ctk.CTkLabel(body, text=t("set.effects_hint"), font=T.font(10), text_color=T.TEXT_3,
                         anchor="w").pack(fill="x")

        tabs.add("performance", t("sub.performance"), build_performance)
        tabs.add("behavior", t("sub.behavior"), build_behavior)
        tabs.add("notify", t("sub.notify"), build_notify)
        tabs.add("appearance", t("sub.appearance"), build_appearance)

        save_row = ctk.CTkFrame(page, fg_color="transparent")
        save_row.pack(fill="x", pady=(10, 0))
        button(save_row, t("set.btn_save"), self._save_all_settings, "primary", icon="save",
               width=230, height=44).pack(side="left")
        self.lbl_saved = ctk.CTkLabel(save_row, text="", font=T.font(11), text_color=T.OK)
        self.lbl_saved.pack(side="left", padx=12)

    # ------------------------------------------------------------------ #
    # Halaman: Stats
    # ------------------------------------------------------------------ #
    def _page_stats(self, page: ctk.CTkFrame) -> None:
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        head = Card3D(page, t("stats.overview"), t("stats.overview_sub"), icon="stats",
                      accent=T.ACCENT)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        hbody = head.content()
        grid = ctk.CTkFrame(hbody, fg_color="transparent")
        grid.pack(fill="x")
        self.stats_labels: Dict[str, StatChip3D] = {}
        for idx, (key, label_key, color) in enumerate((
            ("st_checked", "st.total_checked", T.TEXT),
            ("st_available", "st.available", T.ACCENT),
            ("st_claimed", "st.claimed", T.OK),
            ("st_taken", "st.taken", T.TAKEN),
            ("st_errors", "st.errors", T.BAD),
            ("st_rate", "st.rate_limited", T.WARN),
        )):
            chip = StatChip3D(grid, t(label_key), "0", color, wide=True)
            chip.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=(0, 8), pady=4)
            grid.grid_columnconfigure(idx % 3, weight=1, uniform="stg")
            self.stats_labels[key] = chip

        detail = Card3D(page, t("stats.throughput"), t("stats.throughput_sub"), icon="clock",
                        accent=T.OK)
        detail.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        dbody = detail.content()
        drow = ctk.CTkFrame(dbody, fg_color="transparent")
        drow.pack(fill="x")
        ctk.CTkLabel(drow, text=t("stats.success_rate"), font=T.font(11), text_color=T.TEXT_2,
                     width=140, anchor="w").pack(side="left")
        self.st_success_bar = ctk.CTkProgressBar(drow, height=10, corner_radius=5,
                                                 progress_color=T.OK, fg_color=T.CARD_LO)
        self.st_success_bar.set(0)
        self.st_success_bar.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.st_success_lbl = ctk.CTkLabel(drow, text="0.0%", font=T.font(11, "bold"),
                                           text_color=T.OK, width=70)
        self.st_success_lbl.pack(side="left")
        self.st_meta_lbl = ctk.CTkLabel(dbody, text="", font=T.font(10), text_color=T.TEXT_3,
                                        anchor="w")
        self.st_meta_lbl.pack(fill="x", pady=(10, 0))

        hist = Card3D(page, t("stats.claim_history"), t("stats.claim_history_sub"),
                      icon="history", accent=T.OK)
        hist.grid(row=2, column=0, sticky="nsew")
        self.history_box = ListPane(hist.content(), height=9, color=T.OK)
        self.history_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Sinkronisasi state -> UI (juga dipakai setelah ganti bahasa)
    # ------------------------------------------------------------------ #
    def _sync_state_to_ui(self) -> None:
        self._reload_accounts()
        self._reload_proxies()
        self._reload_claim_history()
        self._reload_history_pane()
        try:
            self.avail_box.replace(self._available, prefix="✓")
            self.claimed_box.replace(self._claimed, prefix="★")
            self.watch_box.replace(self._watch, prefix="•")
            self.lbl_avail_count.configure(text=t("checker.found", n=len(self._available)))
            self.lbl_claimed_count.configure(text=t("checker.claimed_count", n=len(self._claimed)))
            for tag, message, stamp in self._log_lines[-400:]:
                self.log_box.write(tag, message, stamp)
                self.activity_box.write(tag, message, stamp)
        except Exception:  # noqa: BLE001
            pass
        self._refresh_status(self.controller.running, int(self.cfg.get("threads", 15)))

    # ------------------------------------------------------------------ #
    # Event loop
    # ------------------------------------------------------------------ #
    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.controller.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            pass
        try:
            self.after(90, self._pump_events)
        except Exception:  # noqa: BLE001
            pass

    def _handle_event(self, kind: str, payload: Any) -> None:
        if kind == "log":
            tag, text = payload
            self._log(tag, text)
            try:
                self.activity_box.write(tag, text, now_hms())
            except Exception:  # noqa: BLE001
                pass
        elif kind == "result":
            res: CheckResult = payload
            if res.status == NameStatus.AVAILABLE:
                self._log("avail", t("log.result_available", name=res.name))
            elif res.status == NameStatus.TAKEN:
                self._log("taken", t("log.result_taken", name=res.name))
            else:
                self._log("bad", t("log.result_other", name=res.name,
                                   status=res.status.value.lower(), reason=res.reason))
        elif kind == "available":
            name = payload
            self._available.append(name)
            try:
                self.avail_box.append(name, prefix="✓")
                self.lbl_avail_count.configure(text=t("checker.found", n=len(self._available)))
                self.activity_box.write("avail", f"AVAILABLE  {name}", now_hms())
            except Exception:  # noqa: BLE001
                pass
            self._toast_message(t("toast.available", name=name), T.ACCENT)
            self._reload_history_pane()
        elif kind == "claimed":
            name, account = payload
            self._claimed.append(f"{name}  ·  {account}")
            try:
                self.claimed_box.append(f"{name}  ·  {account}", prefix="★")
                self.lbl_claimed_count.configure(
                    text=t("checker.claimed_count", n=len(self._claimed)))
                self.activity_box.write("claim", f"CLAIMED  {name}  via {account}", now_hms())
            except Exception:  # noqa: BLE001
                pass
            self._reload_claim_history()
            self._reload_history_pane()
            try:
                claim_modal(self, name, account, t("dlg.claim_title"), t("dlg.claim_head"),
                            t("dlg.claim_via"), t("dlg.claim_ok"))
            except Exception:  # noqa: BLE001
                pass
        elif kind == "status":
            state, threads = payload if isinstance(payload, tuple) else (str(payload), 0)
            self._refresh_status(state == "running", int(threads or 0))

    def _refresh_status(self, running: bool, threads: int) -> None:
        color = T.OK if running else T.WARN
        head_key = "head.status_running" if running else "head.status_idle"
        side_key = "side.status_running" if running else "side.status_idle"
        try:
            self.status_text.configure(text=t(head_key))
            self.status_dot.configure(text_color=color)
            self.side_status.configure(text="● " + t(side_key), text_color=color)
            self.btn_start.configure(state="disabled" if running else "normal")
            self.btn_stop.configure(state="normal" if running else "disabled")
            if self._hero is not None:
                self._hero.itemconfigure(self._hero_status, fill=color,
                                         text="● " + t(head_key))
                self._hero.itemconfigure(
                    self._hero_progress,
                    text=(t("head.progress_work", n=self.controller.queue_size()) if running
                          else t("head.progress_idle")))
            if running:
                self.progress.configure(mode="indeterminate")
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(0)
        except Exception:  # noqa: BLE001
            pass
        if running and threads:
            try:
                self.chips["threads"].set(threads)
            except Exception:  # noqa: BLE001
                pass

    def _tick(self) -> None:
        try:
            stats = self.controller.stats.get_stats()
            queue_len = self.controller.queue_size()

            self.chips["checked"].set(stats["total_checked"])
            self.chips["available"].set(stats["available"])
            self.chips["claimed"].set(stats["claimed"])
            self.chips["queue"].set(queue_len)
            self.chips["threads"].set(int(self.cfg.get("threads", 15))
                                      if self.controller.running else 0)

            self.side_uptime.configure(text=t("side.uptime", value=stats["uptime"]))
            self.side_queue.configure(text=t("side.queue", value=queue_len))
            self.lbl_queue_total.configure(
                text=t("checker.queue_running" if self.controller.running
                       else "checker.queue_waiting", n=queue_len))
            if self._hero is not None:
                self._hero.itemconfigure(
                    self._hero_progress,
                    text=(t("head.progress_work", n=queue_len) if self.controller.running
                          else t("head.progress_idle")))

            mapping = {
                "st_checked": stats["total_checked"], "st_available": stats["available"],
                "st_claimed": stats["claimed"], "st_taken": stats["taken"],
                "st_errors": stats["errors"], "st_rate": stats["rate_limited"],
            }
            for key, value in mapping.items():
                chip = self.stats_labels.get(key)
                if chip is not None:
                    chip.set(value)

            rate = float(stats["success_rate"])
            self.st_success_bar.set(max(0.0, min(rate / 100.0, 1.0)))
            self.st_success_lbl.configure(text=f"{rate:.1f}%")
            self.st_meta_lbl.configure(text=t("st.meta", uptime=stats["uptime"],
                                              rate=stats["checks_per_sec"], taken=stats["taken"]))

            alive = sum(1 for p in self.controller.proxies if getattr(p, "alive", False))
            self.foot_left.configure(text=t(
                "foot.left", name=t("app.name"), version=t("app.version"),
                state=t("app.footer_running" if self.controller.running else "app.footer_idle"),
                accounts=len(self.controller.accounts)))
            self.foot_right.configure(text=t(
                "foot.right", rate=stats["checks_per_sec"], alive=alive,
                discord=t("foot.on" if self.cfg.get("use_discord_webhook") else "foot.off")))
        except Exception:  # noqa: BLE001
            pass
        try:
            self.after(500, self._tick)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Log & notifikasi
    # ------------------------------------------------------------------ #
    def _log(self, tag: str, message: str) -> None:
        stamp = now_hms()
        self._log_lines.append((tag, message, stamp))
        if len(self._log_lines) > 900:
            del self._log_lines[:300]
        try:
            self.log_box.write(tag, message, stamp)
        except Exception:  # noqa: BLE001
            pass

    def _toast_message(self, message: str, color: str = T.ACCENT, ms: int = 3400) -> None:
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:  # noqa: BLE001
                pass
        toast = Toast(self, message, color)
        toast.place(relx=0.985, y=96, anchor="ne")
        self._toast = toast
        self.after(ms, lambda: self._dismiss_toast(toast))

    def _dismiss_toast(self, widget: Toast) -> None:
        try:
            if widget.winfo_exists():
                widget.destroy()
        except Exception:  # noqa: BLE001
            pass
        if self._toast is widget:
            self._toast = None

    # ------------------------------------------------------------------ #
    # Aksi: checker
    # ------------------------------------------------------------------ #
    def _check_single(self) -> None:
        name = self.ent_check.get().strip().lower()
        if not name:
            return
        self.ent_check.delete(0, "end")
        threading.Thread(target=self._single_worker, args=(name,), daemon=True).start()

    def _single_worker(self, name: str) -> None:
        checker = Checker(delay=0.0)
        res = checker.check(name)
        self.controller.scan_history.record(name, res.status.value, "", res.reason or "")
        if res.status == NameStatus.AVAILABLE:
            append_to_file(AVAILABLE_FILE, res.name)
            self.controller.stats.increment("total")
            self.controller.stats.increment("available")
            self.controller.emit("available", res.name)
            self.controller.emit("result", res)
        elif res.status == NameStatus.TAKEN:
            self.controller.stats.increment("total")
            self.controller.stats.increment("taken")
            self.controller.emit("result", res)
        else:
            self.controller.emit("result", res)

    def _add_target(self) -> None:
        name = self.ent_check.get().strip().lower()
        if not name:
            return
        if self.controller.enqueue(name):
            self._log("info", t("log.queued", name=name))
            self.ent_check.delete(0, "end")
        else:
            self._toast_message(t("toast.invalid_dup", name=name), T.WARN, 2800)

    def _add_watch(self) -> None:
        name = self.ent_watch.get().strip().lower()
        if not name:
            return
        if self.controller.enqueue(name):
            self._watch.append(name)
            try:
                self.watch_box.append(name)
            except Exception:  # noqa: BLE001
                pass
            self._log("info", t("log.watch_added", name=name))
            self.ent_watch.delete(0, "end")
            self._toast_message(t("toast.watching", name=name), T.ACCENT, 2400)
        else:
            self._toast_message(t("toast.already_watched", name=name), T.WARN, 2400)

    def _load_txt(self) -> None:
        path = filedialog.askopenfilename(title=t("checker.gen_load"),
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        names = load_names_from_file(path)
        added = self.controller.enqueue_many(names)
        base = os.path.basename(path)
        self._log("ok", t("log.names_loaded", n=added, file=base))
        self._toast_message(t("toast.loaded", n=added, file=base), T.OK, 2600)

    def _gen_names(self, length: int) -> None:
        names = generate_random(500, length)
        added = self.controller.enqueue_many(names)
        self._log("ok", t("log.gen_names", n=added, length=length))
        self._toast_message(t("toast.gen", n=added, length=length), T.ACCENT, 2600)

    def _gen_full_3l(self) -> None:
        names = enumerate_ordered(3)
        added = self.controller.enqueue_many(names)
        self._log("ok", t("log.gen_full", n=added))
        self._toast_message(t("toast.gen_full", n=added), T.ACCENT, 3200)

    def _gen_smart_rare(self) -> None:
        names = generate_smart_random(500, 3)
        added = self.controller.enqueue_many(names)
        self._log("ok", t("log.gen_smart", n=added))
        self._toast_message(t("toast.gen_smart", n=added), T.ACCENT, 2600)

    def _gen_pattern(self) -> None:
        pattern = self.ent_pattern.get().strip()
        if not pattern:
            self._toast_message(t("toast.pattern_missing"), T.WARN, 2600)
            return
        names = generate_pattern([pattern], 500)
        added = self.controller.enqueue_many(names)
        self._log("ok", t("log.gen_pattern", pattern=pattern, n=added))
        self._toast_message(t("toast.pattern_done", pattern=pattern, n=added), T.ACCENT, 2600)

    def _clear_queue(self) -> None:
        if not messagebox.askyesno(t("dlg.clear_queue_title"), t("dlg.clear_queue_msg")):
            return
        cleared = self.controller.clear_queue()
        self._toast_message(t("toast.queue_cleared", n=cleared), T.WARN, 2400)

    def _export(self, path: str) -> None:
        if not os.path.exists(path):
            self._toast_message(t("toast.export_missing", file=path), T.WARN, 2400)
            return
        target = filedialog.asksaveasfilename(defaultextension=".txt",
                                              initialfile=os.path.basename(path))
        if not target:
            return
        try:
            with open(path, "r", encoding="utf-8") as src, open(target, "w",
                                                               encoding="utf-8") as dst:
                dst.write(src.read())
            self._toast_message(t("toast.export_ok", file=os.path.basename(target)), T.OK, 2600)
        except Exception as exc:  # noqa: BLE001
            self._toast_message(t("toast.export_fail", error=exc), T.BAD, 3400)

    def _start(self) -> None:
        if self.controller.running:
            return
        self._save_all_settings_quiet()
        self.controller.start()
        self._log("ok", t("log.engine_started"))

    def _stop(self) -> None:
        if not self.controller.running:
            return
        self.controller.stop()
        self._log("warn", t("log.engine_stopped"))

    def _toggle_auto_claim(self) -> None:
        value = bool(self.sw_auto_claim.get())
        self._save_setting("auto_claim", value)
        try:
            if value:
                self.sw_auto_claim_cfg.select()
            else:
                self.sw_auto_claim_cfg.deselect()
        except Exception:  # noqa: BLE001
            pass
        self._log("info", t("log.auto_claim", state=t("log.on" if value else "log.off")))

    def _toggle_watch(self) -> None:
        value = bool(self.sw_watch.get())
        self._save_setting("watch_mode", value)
        try:
            if value:
                self.sw_watch_cfg.select()
            else:
                self.sw_watch_cfg.deselect()
        except Exception:  # noqa: BLE001
            pass
        self._log("info", t("log.watch_mode", state=t("log.on" if value else "log.off")))

    # ------------------------------------------------------------------ #
    # Aksi: accounts
    # ------------------------------------------------------------------ #
    def _add_token_account(self) -> None:
        token = self.ent_token.get().strip()
        email = self.ent_acc_label.get().strip()
        if not token:
            self._toast_message(t("toast.token_missing"), T.WARN, 3000)
            return
        kind = self.opt_token_type.get()
        if kind == t("acc.token_type_auto"):
            kind = clm.classify_token(token)
            if kind == "unknown":
                kind = "mc_token"
        self.lbl_acc_hint.configure(text=t("misc.verify_kind", kind=kind), text_color=T.WARN)
        self._log("info", t("log.adding_account", kind=kind))

        def work() -> None:
            try:
                if kind == "ms_token":
                    acc = clm.login_with_ms_token(token, email)
                else:
                    acc = clm.login_with_mc_token(token, email)
                self.controller.accounts.append(acc)
                clm.save_accounts(self.controller.accounts)
                state = "verified" if acc.token_verified else "429"
                self.after(0, lambda: self._toast_message(
                    t("toast.account_added", account=acc.label()), T.OK, 3200))
                self.after(0, lambda: self.ent_token.delete(0, "end"))
                self.after(0, lambda: self.lbl_acc_hint.configure(
                    text=t("misc.account_ready"), text_color=T.OK))
                self.after(0, self._reload_accounts)
                self.after(0, lambda: self._log(
                    "ok", t("log.account_added", state=state, account=acc.label())))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda m=msg: self._log("bad", t("log.token_invalid", error=m)))
                self.after(0, lambda m=msg: self._toast_message(
                    f"{t('misc.token_invalid')}: {m}", T.BAD, 4600))
                self.after(0, lambda: self.lbl_acc_hint.configure(
                    text=t("misc.token_invalid"), text_color=T.BAD))

        threading.Thread(target=work, daemon=True).start()

    def _add_email_password_account(self) -> None:
        email = self.ent_ep_email.get().strip()
        password = self.ent_ep_password.get().strip()
        if not email or not password:
            self._toast_message(t("toast.login_fields"), T.WARN, 3000)
            return
        self.lbl_acc_hint.configure(text=t("misc.login_running"), text_color=T.WARN)
        self._log("info", t("log.login_oauth", email=email))

        def work() -> None:
            try:
                acc = clm.login_with_oauth(email, password)
                self.controller.accounts.append(acc)
                clm.save_accounts(self.controller.accounts)
                self.after(0, lambda: self._toast_message(
                    t("toast.account_added", account=acc.label()), T.OK, 3200))
                self.after(0, lambda: self.ent_ep_email.delete(0, "end"))
                self.after(0, lambda: self.ent_ep_password.delete(0, "end"))
                self.after(0, lambda: self.lbl_acc_hint.configure(
                    text=t("misc.account_ready"), text_color=T.OK))
                self.after(0, self._reload_accounts)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda m=msg: self._log("bad", t("log.login_failed", error=m)))
                self.after(0, lambda m=msg: self._toast_message(
                    t("log.login_failed", error=m), T.BAD, 4600))
                self.after(0, lambda: self.lbl_acc_hint.configure(
                    text=t("misc.login_failed"), text_color=T.BAD))

        threading.Thread(target=work, daemon=True).start()

    def _reload_accounts(self) -> None:
        self.controller.accounts = clm.load_accounts()
        rows: List[str] = []
        for idx, acc in enumerate(self.controller.accounts, 1):
            state = t("acc.state_valid") if acc.is_token_valid() else t("acc.state_expired")
            refresh = (t("acc.refresh_ok") if getattr(acc, "refresh_token", None)
                       else t("acc.refresh_none"))
            rows.append(f"[{idx:02d}] {acc.label():<34} {state:<9} {refresh}")
        if not rows:
            rows = [t("acc.empty")]
        try:
            self.accounts_box.replace(rows, prefix="›")
        except Exception:  # noqa: BLE001
            pass

    def _refresh_all_tokens(self) -> None:
        if not self.controller.accounts:
            self._toast_message(t("toast.account_none"), T.WARN, 2400)
            return
        self._log("info", t("log.token_refresh_all"))

        def work() -> None:
            for acc in list(self.controller.accounts):
                try:
                    clm.refresh_account_tokens(acc)
                    self.after(0, lambda a=acc: self._log(
                        "ok", t("log.token_refreshed", account=a.label())))
                except Exception as exc:  # noqa: BLE001
                    self.after(0, lambda a=acc, e=exc: self._log(
                        "bad", t("log.token_refresh_fail", account=a.label(), error=e)))
            clm.save_accounts(self.controller.accounts)
            self.after(0, self._reload_accounts)
            self.after(0, lambda: self._toast_message(t("toast.refresh_done"), T.OK, 2600))

        threading.Thread(target=work, daemon=True).start()

    def _clear_all_accounts(self) -> None:
        if not messagebox.askyesno(t("dlg.clear_acc_title"), t("dlg.clear_acc_msg")):
            return
        self.controller.accounts = []
        clm.save_accounts([])
        self._reload_accounts()
        self._toast_message(t("toast.account_cleared"), T.WARN, 2400)

    # ------------------------------------------------------------------ #
    # Aksi: proxies
    # ------------------------------------------------------------------ #
    def _load_proxies(self) -> None:
        path = filedialog.askopenfilename(title=t("proxy.btn_load"),
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        proxies = ProxyManager.load_from_file(path)
        self.controller.proxies = proxies
        self.controller.proxy_manager.proxies = proxies
        self._save_setting("proxy_file", path)
        self._reload_proxies()
        self._log("ok", t("log.proxies_loaded", n=len(proxies)))
        self._toast_message(t("toast.proxy_loaded", n=len(proxies)), T.OK, 2600)

    def _test_proxies(self) -> None:
        if not self.controller.proxies:
            self._toast_message(t("toast.proxy_none"), T.WARN, 2400)
            return
        self.lbl_proxy_stats.configure(text=t("proxy.testing"), text_color=T.WARN)
        self._log("info", t("log.proxies_testing"))

        def work() -> None:
            result = self.controller.proxy_manager.test_all()
            self.after(0, lambda: self.lbl_proxy_stats.configure(
                text=t("proxy.result", alive=result["alive"], dead=result["dead"],
                       total=result["total"]),
                text_color=T.OK if result["alive"] else T.BAD))
            self.after(0, self._reload_proxies)
            self.after(0, lambda: self._toast_message(
                t("toast.proxy_result", alive=result["alive"], dead=result["dead"]),
                T.OK if result["alive"] else T.WARN, 3000))

        threading.Thread(target=work, daemon=True).start()

    def _clean_proxies(self) -> None:
        removed = self.controller.proxy_manager.auto_clean()
        self.controller.proxies = self.controller.proxy_manager.proxies
        self._reload_proxies()
        self._log("warn", t("log.proxies_cleaned", n=removed))
        self._toast_message(t("toast.proxy_cleaned", n=removed), T.WARN, 2400)

    def _reload_proxies(self) -> None:
        rows: List[str] = []
        for idx, proxy in enumerate(self.controller.proxies, 1):
            state = "ALIVE" if getattr(proxy, "alive", False) else "DEAD"
            rows.append(f"[{idx:03d}] {proxy.host:>15}:{proxy.port:<6} {proxy.proxy_type:<7} "
                        f"{state:<5} score {getattr(proxy, 'score', 0):>3.0f}")
        if not rows:
            rows = [t("proxy.empty")]
        try:
            self.proxy_box.replace(rows, prefix="›")
        except Exception:  # noqa: BLE001
            pass

    def _reload_claim_history(self) -> None:
        rows = []
        for item in self.controller.claim_history[-200:][::-1]:
            rows.append(f"{item.get('time', '?')}   {item.get('name', '?'):<16} "
                        f"{item.get('account', '')}")
        try:
            self.history_box.replace(rows, prefix="✓")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Aksi: settings
    # ------------------------------------------------------------------ #
    def _save_setting(self, key: str, value: Any) -> None:
        self.cfg[key] = value
        save_config(self.cfg)

    def _collect_settings(self) -> Dict[str, Any]:
        def as_float(entry: ctk.CTkEntry, fallback: float) -> float:
            try:
                return float(entry.get().strip().replace(",", "."))
            except (ValueError, AttributeError):
                return fallback

        return {
            "threads": int(self.sld_threads.get()),
            "timeout": min(max(as_float(self.ent_timeout, 10.0), 1.0), 60.0),
            "stealth_mode": bool(self.sw_stealth.get()),
            "sound_notifications": bool(self.sw_sound.get()),
            "auto_claim": bool(self.sw_auto_claim_cfg.get()),
            "watch_mode": bool(self.sw_watch_cfg.get()),
            "use_discord_webhook": bool(self.sw_discord.get()),
            "notify_on_available": bool(self.sw_notify_avail.get()),
            "notify_on_claimed": bool(self.sw_notify_claim.get()),
            "discord_webhook_url": self.ent_webhook.get().strip(),
        }

    def _save_all_settings_quiet(self) -> None:
        try:
            self.cfg.update(self._collect_settings())
            save_config(self.cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"save settings failed: {exc}")

    def _save_all_settings(self) -> None:
        try:
            self.cfg.update(self._collect_settings())
            save_config(self.cfg)
            self.lbl_saved.configure(text=t("set.saved"), text_color=T.OK)
            self.after(2500, lambda: self.lbl_saved.configure(text=""))
            self._log("ok", t("log.settings_saved"))
            self._toast_message(t("toast.settings_saved"), T.OK, 2400)
        except Exception as exc:  # noqa: BLE001
            self._toast_message(t("toast.settings_failed", error=exc), T.BAD, 3400)

    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        try:
            for wall in list(self._wallpapers):
                wall.stop()
            if self.controller.running:
                self.controller.stop()
            self.controller.scan_history.close()
            self._save_all_settings_quiet()
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.destroy()


PremiumSniper = VarinSniperApp
