#!/usr/bin/env python3
"""
MC Sniper — 3L/4L Minecraft Username Sniper (Premium GUI)

Tabs: Checker | Sniper | Accounts | Proxies | Settings | Stats

Aturan pemisahan:
  * SniperController  -> mesin (antrian, worker thread, claim, statistik)
  * LogView / ListPane / StatChip / Card -> komponen GUI yang bisa dipakai ulang
  * MCSniperApp       -> layout, navigasi, dan reaksi terhadap event controller

Semua update GUI dari thread lain dilewatkan queue `controller.events`
dan dipompa oleh `.after()` di thread utama, jadi GUI tetap responsif.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from utils import (
    load_config, save_config, load_names_from_file, append_to_file,
    format_uptime, StatsTracker, send_discord_webhook,
)
from checker import Checker, CheckResult, NameStatus
from generator import (
    enumerate_ordered, generate_pattern, generate_random,
    generate_smart_random, get_pattern_examples,
)
from proxy import Proxy, ProxyManager
import claimer as clm

logger = logging.getLogger("MinecraftSniper.GUI")

# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_NAME = "MC Sniper"
APP_VERSION = "v2.2 Pro"
WINDOW_TITLE = "MC Sniper | 3L/4L Username Sniper"

BG = "#0d0d12"          # background utama
SIDEBAR = "#111118"     # panel sidebar
PANEL = "#1a1a24"       # panel / card
CARD = "#1e1e2a"        # isi card
CARD_HI = "#242431"     # card hover / aktif
BORDER = "#262636"      # garis halus
BORDER_HI = "#33405e"   # garis saat aktif

ACCENT = "#00f0ff"      # neon cyan
ACCENT2 = "#5b8bff"     # electric blue
ACCENT_DIM = "#0a3d47"
OK = "#00ff9f"          # success
BAD = "#ff4d6d"         # error
WARN = "#ffd166"        # warning
INFO = "#5b8bff"
TEXT = "#eef2f7"
TEXT2 = "#8b8ba7"
TEXT3 = "#5d5d75"
TAKEN_C = "#7e7e96"
CLAIM_C = "#7ff6ff"

RADIUS = 12
PAD = 14

# File paths
AVAILABLE_FILE = "available.txt"
CLAIMED_FILE = "claimed.txt"
FAILED_FILE = "failed.txt"
HISTORY_FILE = "claim_history.json"

TABS = ("Checker", "Sniper", "Accounts", "Proxies", "Settings", "Stats")
NAV = (
    ("Checker", "🎯", "Checker"),
    ("Sniper", "⚡", "Sniper"),
    ("Accounts", "👤", "Accounts"),
    ("Proxies", "🛡", "Proxies"),
    ("Settings", "⚙", "Settings"),
    ("Stats", "📊", "Stats"),
)


def now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def font(size: int = 12, weight: str = "normal", family: str = "Segoe UI") -> ctk.CTkFont:
    return ctk.CTkFont(family=family, size=size, weight=weight)


MONO = "Consolas"


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #
class DiscordNotifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def notify_available(self, name: str) -> None:
        self._send("🎯 Username Available!", f"**{name}** is available to claim!", 0x00FF9F,
                   "notify_on_available")

    def notify_claimed(self, name: str, account: str) -> None:
        self._send("🎉 Claim Success!", f"**{name}** claimed via `{account}`", 0x00F0FF,
                   "notify_on_claimed")

    def _send(self, title: str, desc: str, color: int, flag: str) -> None:
        if not self.config.get("use_discord_webhook") or not self.config.get(flag):
            return
        url = self.config.get("discord_webhook_url", "")
        if not url:
            return
        threading.Thread(target=send_discord_webhook, args=(url, title, desc, color),
                         daemon=True).start()


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class SniperController:
    """Mesin sniper. Tidak menyentuh widget sama sekali — hanya emit event."""

    def __init__(self):
        self.events: queue.Queue = queue.Queue()
        self.config = load_config()
        self.stop_event = threading.Event()
        self.names_queue: queue.Queue = queue.Queue()
        self.pending: set = set()
        self.taken: set = set()
        self._lock = threading.Lock()
        self.workers: List[threading.Thread] = []
        self.watch_thread: Optional[threading.Thread] = None
        self.running = False
        self.start_time = time.time()
        self.stats = StatsTracker()
        self.proxies: List[Proxy] = []
        self.proxy_manager = ProxyManager()
        self.accounts: List[clm.MMCAccount] = []
        self.claim_history: List[Dict[str, Any]] = []
        self.load_history()
        self.notifier = DiscordNotifier(self.config)

    # -- persistence -------------------------------------------------------
    def load_history(self) -> None:
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
                    self.claim_history = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("history load failed: %s", exc)
            self.claim_history = []

    def save_history(self) -> None:
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.claim_history[-1000:], fh, indent=2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("history save failed: %s", exc)

    # -- events ------------------------------------------------------------
    def emit(self, kind: str, payload: Any = None) -> None:
        try:
            self.events.put((kind, payload), timeout=1)
        except Exception:  # noqa: BLE001
            pass

    # -- queue -------------------------------------------------------------
    def enqueue(self, name: str) -> bool:
        name = (name or "").strip().lower()
        if not (3 <= len(name) <= 16):
            return False
        if not all(ch.isalnum() or ch == "_" for ch in name):
            return False
        with self._lock:
            if name in self.pending or name in self.taken:
                return False
            self.pending.add(name)
        self.names_queue.put(name)
        return True

    def enqueue_many(self, names: List[str]) -> int:
        added = 0
        for name in names:
            if self.enqueue(name):
                added += 1
        return added

    def queue_snapshot(self) -> List[str]:
        with self._lock:
            return sorted(self.pending)

    def queue_size(self) -> int:
        with self._lock:
            return len(self.pending)

    def clear_queue(self) -> int:
        with self._lock:
            cleared = len(self.pending)
            self.pending.clear()
            self.taken.clear()
        while True:
            try:
                self.names_queue.get_nowait()
            except queue.Empty:
                break
        self.emit("log", ("info", f"Queue cleared — {cleared} nama dibuang"))
        return cleared

    def remove_from_queue(self, name: str) -> None:
        with self._lock:
            self.pending.discard(name)

    # -- lifecycle ---------------------------------------------------------
    def start(self, names: Optional[List[str]] = None) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.start_time = time.time()
        self.stats = StatsTracker()
        self.accounts = clm.load_accounts() or self.accounts

        checker_kwargs = dict(
            proxies=self.proxies,
            proxy_rotate=bool(self.config.get("proxy_rotate", True)),
            delay=0.0,
            timeout=float(self.config.get("timeout", 10.0)),
            stealth=bool(self.config.get("stealth_mode", True)),
            adaptive=False,
            max_retries=1,
        )
        n_threads = max(1, min(int(self.config.get("threads", 15)), 100))

        if names:
            self.enqueue_many(names)

        self.workers = []
        for idx in range(n_threads):
            worker = threading.Thread(
                target=self._worker, args=(Checker(**checker_kwargs),),
                name=f"Checker-{idx}", daemon=True,
            )
            worker.start()
            self.workers.append(worker)

        if self.config.get("watch_mode", True) and not (self.watch_thread and self.watch_thread.is_alive()):
            self.watch_thread = threading.Thread(target=self._watch_loop, name="Watcher", daemon=True)
            self.watch_thread.start()

        self.emit("status", f"RUNNING · {n_threads} threads")
        self.emit("log", ("ok", f"Engine start — {n_threads} threads, no rate limit"))

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.emit("status", "STOPPED")
        self.emit("log", ("warn", "Menghentikan semua worker..."))
        for worker in self.workers:
            worker.join(timeout=1.5)
        self.workers = []

    # -- worker ------------------------------------------------------------
    def _worker(self, checker: Checker) -> None:
        while not self.stop_event.is_set():
            try:
                name = self.names_queue.get(timeout=0.3)
            except queue.Empty:
                if not self.running:
                    break
                continue

            try:
                result = checker.check(name)
                self.stats.increment("total")

                if result.status == NameStatus.AVAILABLE:
                    self.stats.increment("available")
                    append_to_file(AVAILABLE_FILE, result.name)
                    self.emit("available", result.name)
                    self.notifier.notify_available(result.name)
                    if self.config.get("auto_claim") and self.accounts:
                        self.try_claim(result.name)
                elif result.status == NameStatus.TAKEN:
                    self.stats.increment("taken")
                    with self._lock:
                        self.taken.add(result.name)
                        self.pending.discard(result.name)
                else:
                    self.stats.increment("errors")
                    self.emit("log", ("warn", f"{name}: {result.reason or 'error'}"))

                self.emit("result", result)
            except Exception as exc:  # noqa: BLE001
                logger.exception("worker error")
                self.stats.increment("errors")
                self.emit("log", ("bad", f"worker error pada {name}: {exc}"))
            finally:
                self.names_queue.task_done()

    def _requeue(self, name: str) -> None:
        pass

    def _watch_loop(self) -> None:
        while not self.stop_event.is_set() and self.running:
            time.sleep(max(5.0, float(self.config.get("watch_interval", 30))))
            if not self.running or not self.config.get("watch_mode", True):
                continue
            with self._lock:
                recheck = list(self.taken)
                self.taken.clear()
            if not recheck:
                continue
            added = self.enqueue_many(recheck)
            if added:
                self.emit("log", ("info", f"Watch mode: re-check {added} nama taken"))

    # -- claim -------------------------------------------------------------
    def try_claim(self, name: str) -> None:
        threading.Thread(target=self._do_claim, args=(name,), daemon=True).start()

    def _do_claim(self, name: str) -> None:
        try:
            if not self.accounts:
                self.emit("log", ("warn", f"'{name}' available tapi belum ada akun terdaftar"))
                return

            smart = clm.SmartClaimQueue(self.accounts)
            max_attempts = int(self.config.get("claim_max_accounts", 0)) or len(self.accounts)
            attempts = 0

            while attempts < max_attempts and not self.stop_event.is_set():
                acc = smart.get_next_account()
                if not acc:
                    break
                attempts += 1
                self.emit("log", ("info", f"Claim '{name}' via {acc.label()} [{attempts}/{max_attempts}]"))

                result = clm.claim_name(acc, name)
                clm.save_accounts(self.accounts)

                if result.status == clm.ClaimStatus.SUCCESS:
                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    append_to_file(CLAIMED_FILE, f"{name} | {acc.label()} | {stamp}")
                    self.stats.increment("claimed")
                    self.claim_history.append(
                        {"name": name, "account": acc.label(), "time": stamp, "status": "success"}
                    )
                    self.save_history()
                    self.remove_from_queue(name)
                    self.emit("claimed", (name, acc.label()))
                    self.notifier.notify_claimed(name, acc.label())
                    if self.config.get("sound_notifications", False):
                        threading.Thread(target=self._play_sound, daemon=True).start()
                    return

                if result.status == clm.ClaimStatus.NAME_TAKEN:
                    append_to_file(FAILED_FILE, f"{name} | taken | {result.message} | {now_hms()}")
                    self.remove_from_queue(name)
                    self.emit("log", ("taken", f"claim '{name}' gagal: {result.message}"))
                    return

                if result.status == clm.ClaimStatus.RATE_LIMITED:
                    time.sleep(3)
                    continue

                if result.status in (clm.ClaimStatus.NOT_ELIGIBLE, clm.ClaimStatus.COOLDOWN):
                    append_to_file(FAILED_FILE, f"{name} | not_eligible | {result.message} | {now_hms()}")
                    self.emit("log", ("warn", f"'{name}' tidak eligible via {acc.label()}: {result.message}"))
                    continue

                append_to_file(FAILED_FILE, f"{name} | {result.status.value} | {result.message} | {now_hms()}")
                self.emit("log", ("warn", f"'{name}' gagal via {acc.label()}: {result.message}"))

            self.emit("log", ("bad", f"Claim '{name}' gagal setelah {attempts} percobaan"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("claim error")
            self.emit("log", ("bad", f"Claim exception '{name}': {exc}"))

    def _play_sound(self) -> None:
        try:
            if os.path.exists("success.mp3"):
                from playsound import playsound  # type: ignore

                playsound("success.mp3")
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            print("\a", end="", flush=True)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Reusable widgets
# --------------------------------------------------------------------------- #
class Card(ctk.CTkFrame):
    """Panel dengan judul + area isi."""

    def __init__(self, master: Any, title: str = "", subtitle: str = "", **kwargs: Any):
        kwargs.setdefault("fg_color", PANEL)
        kwargs.setdefault("corner_radius", RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER)
        super().__init__(master, **kwargs)
        self.body: Optional[ctk.CTkFrame] = None

        if title:
            head = ctk.CTkFrame(self, fg_color="transparent", height=30)
            head.pack(fill="x", padx=PAD + 4, pady=(PAD - 2, 4))
            ctk.CTkLabel(head, text=title, font=font(13, "bold"), text_color=TEXT,
                         anchor="w").pack(side="left")
            if subtitle:
                ctk.CTkLabel(head, text=subtitle, font=font(10), text_color=TEXT3,
                             anchor="w").pack(side="left", padx=(10, 0), pady=(2, 0))
            self.head = head
        else:
            self.head = None

    def content(self) -> ctk.CTkFrame:
        if self.body is None:
            self.body = ctk.CTkFrame(self, fg_color="transparent")
            self.body.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        return self.body


class StatChip(ctk.CTkFrame):
    """Kotak statistik kecil untuk header / tab Stats."""

    def __init__(self, master: Any, label: str, value: str = "0", color: str = ACCENT,
                 wide: bool = False, **kwargs: Any):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER)
        super().__init__(master, **kwargs)
        self._color = color
        padx = 18 if wide else 12
        self.value_lbl = ctk.CTkLabel(
            self, text=value, font=font(22 if wide else 16, "bold"), text_color=color,
        )
        self.value_lbl.pack(anchor="w", padx=padx, pady=(10 if wide else 6, 0))
        ctk.CTkLabel(self, text=label.upper(), font=font(9, "bold"), text_color=TEXT3).pack(
            anchor="w", padx=padx, pady=(0, 10 if wide else 6)
        )

    def set(self, value: Any) -> None:
        text = str(value)
        if self.value_lbl.cget("text") != text:
            self.value_lbl.configure(text=text)

    def set_color(self, color: str) -> None:
        self._color = color
        self.value_lbl.configure(text_color=color)


class LogView(tk.Frame):
    """Log berwarna + timestamp + autoscroll (tk.Text agar tag warna andal)."""

    TAGS = {
        "ok": OK,
        "avail": ACCENT,
        "claim": CLAIM_C,
        "bad": BAD,
        "taken": TAKEN_C,
        "warn": WARN,
        "info": INFO,
        "muted": TEXT3,
    }

    def __init__(self, master: Any, height: int = 14, **kwargs: Any):
        super().__init__(master, bg=CARD, highlightthickness=0, **kwargs)
        self.autoscroll = True

        self.text = tk.Text(
            self, bg=CARD, fg=TEXT, insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=0, wrap="word", height=height, font=(MONO, 10),
            padx=12, pady=10, spacing1=1, spacing3=2,
            selectbackground="#2b3550", selectforeground=TEXT, state="disabled",
        )
        self.scroll = ctk.CTkScrollbar(self, command=self._yview, width=12,
                                       button_color=BORDER_HI, fg_color=CARD)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        for name, color in self.TAGS.items():
            self.text.tag_configure(name, foreground=color)
        self.text.tag_configure("time", foreground=TEXT3)
        self.text.tag_configure("claim_bold", foreground=CLAIM_C, font=(MONO, 10, "bold"))

    def _yview(self, *args: Any) -> None:
        self.text.yview(*args)

    def _on_scroll(self, first: str, last: str) -> None:
        try:
            self.autoscroll = float(last) >= 0.999
        except (TypeError, ValueError):
            self.autoscroll = True
        self.scroll.set(first, last)

    def write(self, tag: str, message: str, stamp: bool = True) -> None:
        tag = tag if tag in self.TAGS else "info"
        self.text.configure(state="normal")
        if stamp:
            self.text.insert("end", f"{now_hms()}  ", "time")
        suffix = None
        if tag == "claim":
            suffix = "claim_bold"
        self.text.insert("end", message + "\n", (tag, suffix) if suffix else (tag,))
        # batasi ukuran log agar tidak menggerus memori saat berjalan lama
        if int(self.text.index("end-1c").split(".")[0]) > 900:
            self.text.delete("1.0", "300.0")
        self.text.configure(state="disabled")
        if self.autoscroll:
            self.text.see("end")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class ListPane(tk.Frame):
    """Daftar read-only dengan badge jumlah (dipakai Available / Claimed / Queue)."""

    def __init__(self, master: Any, height: int = 10, color: str = TEXT, **kwargs: Any):
        super().__init__(master, bg=CARD, highlightthickness=0, **kwargs)
        self.count = 0
        self.color = color
        self.text = tk.Text(
            self, bg=CARD, fg=color, relief="flat", bd=0, highlightthickness=0,
            wrap="none", height=height, font=(MONO, 10), padx=12, pady=10,
            selectbackground="#2b3550", state="disabled", cursor="arrow",
        )
        self.scroll = ctk.CTkScrollbar(self, command=self.text.yview, width=12,
                                       button_color=BORDER_HI, fg_color=CARD)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        self.scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

    def append(self, value: str, prefix: str = "•") -> None:
        self.count += 1
        self.text.configure(state="normal")
        self.text.insert("end", f"{prefix} {value}\n")
        self.text.configure(state="disabled")
        self.text.see("end")

    def replace(self, values: List[str], prefix: str = "•") -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for value in values:
            self.text.insert("end", f"{prefix} {value}\n")
        self.text.configure(state="disabled")
        self.count = len(values)

    def clear(self) -> None:
        self.replace([])


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class MCSniperApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title(WINDOW_TITLE)
        self.geometry("1440x880")
        self.minsize(1180, 720)
        self._center(1440, 880)
        self._set_icon()

        self.controller = SniperController()
        self.cfg = self.controller.config

        self.active_tab = "Checker"
        self.nav_items: Dict[str, Dict[str, Any]] = {}
        self.views: Dict[str, ctk.CTkFrame] = {}
        self.chips: Dict[str, StatChip] = {}
        self.stats_labels: Dict[str, ctk.CTkLabel] = {}
        self._toast_widget: Optional[ctk.CTkFrame] = None
        self._spinner_frames = "⠋⠙⠹⸨⠸⠼⠴⠦⠧⠇⠏"
        self._spinner_idx = 0
        self._last_queue_ui = 0.0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-Return>", lambda _e: self._start())
        self.bind("<Escape>", lambda _e: self._stop())

        self.after(80, self._pump_events)
        self.after(500, self._tick_stats)
        self.after(300, self._tick_spinner)

        self._log("info", f"{APP_NAME} {APP_VERSION} siap — {len(self.controller.accounts)} akun, "
                          f"{len(self.controller.proxies)} proxy")

    # -- window helpers ----------------------------------------------------
    def _center(self, width: int, height: int) -> None:
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{width}x{height}+{max(0, (sw - width) // 2)}+{max(0, (sh - height) // 3)}")
        except Exception:  # noqa: BLE001
            pass

    def _set_icon(self) -> None:
        for name in ("assets/icon.ico", "icon.ico"):
            if os.path.exists(name):
                try:
                    self.iconbitmap(name)
                    return
                except Exception:  # noqa: BLE001
                    pass
        for name in ("assets/icon.png", "icon.png"):
            if os.path.exists(name):
                try:
                    self.iconphoto(True, tk.PhotoImage(file=name))
                    return
                except Exception:  # noqa: BLE001
                    pass

    # -- sidebar -----------------------------------------------------------
    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=248, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.pack_propagate(False)

        # logo
        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.pack(fill="x", padx=22, pady=(26, 8))
        row = ctk.CTkFrame(logo, fg_color="transparent")
        row.pack(anchor="w")
        ctk.CTkLabel(row, text="⚡", font=font(22), text_color=ACCENT).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(row, text="MC SNIPER", font=font(20, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(logo, text="3L / 4L  USERNAME HUNTER", font=font(9, "bold"),
                     text_color=ACCENT2).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(side, height=1, fg_color=BORDER).pack(fill="x", padx=18, pady=(18, 12))

        # nav
        for key, icon, label in NAV:
            wrap = ctk.CTkFrame(side, fg_color="transparent", height=44)
            wrap.pack(fill="x", padx=12, pady=2)
            wrap.pack_propagate(False)

            bar = ctk.CTkFrame(wrap, width=3, corner_radius=2, fg_color="transparent")
            bar.pack(side="left", fill="y", padx=(0, 6), pady=8)

            btn = ctk.CTkButton(
                wrap, text=f"  {icon}   {label}", anchor="w", height=40, corner_radius=9,
                fg_color="transparent", hover_color=CARD, text_color=TEXT2,
                font=font(13), border_width=0,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(side="left", fill="both", expand=True)
            self.nav_items[key] = {"bar": bar, "btn": btn}

        # bottom status
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)

        self.side_status = ctk.CTkLabel(bottom, text="● IDLE", font=font(11, "bold"),
                                        text_color=WARN, anchor="w")
        self.side_status.pack(fill="x")
        self.side_uptime = ctk.CTkLabel(bottom, text="uptime  00:00:00", font=font(10),
                                        text_color=TEXT3, anchor="w")
        self.side_uptime.pack(fill="x", pady=(2, 0))
        self.side_queue = ctk.CTkLabel(bottom, text="queue  0", font=font(10),
                                       text_color=TEXT3, anchor="w")
        self.side_queue.pack(fill="x")
        ctk.CTkFrame(bottom, height=1, fg_color=BORDER).pack(fill="x", pady=10)
        ctk.CTkLabel(bottom, text=f"{APP_NAME}  {APP_VERSION}", font=font(9),
                     text_color=TEXT3, anchor="w").pack(fill="x")

        self._switch_tab("Checker")

    # -- main area ---------------------------------------------------------
    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        self._build_header(main)

        self.content = ctk.CTkFrame(main, fg_color=BG)
        self.content.grid(row=1, column=0, sticky="nsew", padx=(18, 18), pady=(4, 0))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        builders = {
            "Checker": self._tab_checker,
            "Sniper": self._tab_sniper,
            "Accounts": self._tab_accounts,
            "Proxies": self._tab_proxies,
            "Settings": self._tab_settings,
            "Stats": self._tab_stats,
        }
        for name in TABS:
            view = ctk.CTkFrame(self.content, fg_color="transparent")
            view.grid(row=0, column=0, sticky="nsew")
            self.views[name] = view
            builders[name](view)

        self._build_footer(main)

    def _build_header(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkFrame(parent, fg_color=BG, height=104)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        header.pack_propagate(False)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="y")
        ctk.CTkLabel(left, text="MC Sniper", font=font(24, "bold"), text_color=TEXT).pack(
            anchor="w", pady=(14, 0)
        )
        self.header_sub = ctk.CTkLabel(left, text="Ready · proxyless · multi-source checker",
                                       font=font(11), text_color=TEXT2)
        self.header_sub.pack(anchor="w")

        # status pill
        self.status_pill = ctk.CTkFrame(left, fg_color=CARD, corner_radius=8, border_width=1,
                                        border_color=BORDER)
        self.status_pill.pack(anchor="w", pady=(8, 0))
        self.status_dot = ctk.CTkLabel(self.status_pill, text="●", font=font(12),
                                       text_color=WARN)
        self.status_dot.pack(side="left", padx=(10, 4), pady=3)
        self.status_text = ctk.CTkLabel(self.status_pill, text="IDLE", font=font(10, "bold"),
                                        text_color=TEXT2)
        self.status_text.pack(side="left", padx=(0, 10), pady=3)

        # right: chips + start/stop
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", fill="y")

        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(side="right", fill="y", padx=(10, 0), pady=12)

        self.btn_start = ctk.CTkButton(
            actions, text="▶  START", width=132, height=52, corner_radius=11,
            fg_color=OK, hover_color="#00d988", text_color="#05231a",
            font=font(14, "bold"), command=self._start,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            actions, text="■  STOP", width=118, height=52, corner_radius=11,
            fg_color=CARD, hover_color="#33202a", text_color=BAD,
            border_width=1, border_color="#43222c", font=font(14, "bold"),
            command=self._stop, state="disabled",
        )
        self.btn_stop.pack(side="left")

        chips_row = ctk.CTkFrame(right, fg_color="transparent")
        chips_row.pack(side="right", pady=12)
        for key, label, color in (
            ("checked", "Checked", TEXT),
            ("available", "Available", ACCENT),
            ("claimed", "Claimed", OK),
            ("queue", "Queue", WARN),
            ("threads", "Threads", ACCENT2),
        ):
            chip = StatChip(chips_row, label, "0", color)
            chip.pack(side="left", padx=(0, 8))
            self.chips[key] = chip

    def _build_footer(self, parent: ctk.CTkFrame) -> None:
        footer = ctk.CTkFrame(parent, fg_color=BG, height=28)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(6, 10))
        footer.pack_propagate(False)

        self.foot_left = ctk.CTkLabel(
            footer, text=f"{APP_NAME} {APP_VERSION}   ·   ready",
            font=font(10), text_color=TEXT3,
        )
        self.foot_left.pack(side="left")

        self.foot_right = ctk.CTkLabel(
            footer, text="checks/s 0.00   ·   proxy 0 alive   ·   discord off",
            font=font(10), text_color=TEXT3,
        )
        self.foot_right.pack(side="right")

    # -- navigation --------------------------------------------------------
    def _switch_tab(self, name: str) -> None:
        self.active_tab = name
        for key, item in self.nav_items.items():
            if key == name:
                item["bar"].configure(fg_color=ACCENT)
                item["btn"].configure(fg_color=CARD_HI, text_color=ACCENT,
                                      font=font(13, "bold"), hover_color=CARD_HI)
            else:
                item["bar"].configure(fg_color="transparent")
                item["btn"].configure(fg_color="transparent", text_color=TEXT2,
                                      font=font(13), hover_color=CARD)
        for key, view in self.views.items():
            if key == name:
                view.grid(row=0, column=0, sticky="nsew")
            else:
                view.grid_remove()

    # ------------------------------------------------------------------ #
    # Tab: Checker
    # ------------------------------------------------------------------ #
    def _tab_checker(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # --- input card ---
        entry_card = Card(tab, "Target & Queue",
                          "playerdb → minecraftservices → mojang → ashcon → namemc → mcchecker")
        entry_card.grid(row=0, column=0, sticky="ew", pady=(2, 10))
        body = entry_card.content()

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        self.ent_check = ctk.CTkEntry(
            row, placeholder_text="username (3–16 karakter, a-z 0-9 _)",
            height=44, corner_radius=10, fg_color=CARD, border_color=BORDER,
            font=font(13),
        )
        self.ent_check.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ent_check.bind("<Return>", lambda _e: self._check_single())

        ctk.CTkButton(row, text="Check", width=104, height=44, corner_radius=10,
                      fg_color=CARD_HI, hover_color="#2c2c3d", text_color=ACCENT,
                      border_width=1, border_color=BORDER_HI, font=font(12, "bold"),
                      command=self._check_single).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="＋ Add", width=100, height=44, corner_radius=10,
                      fg_color=ACCENT, hover_color="#00cfdd", text_color="#04222b",
                      font=font(12, "bold"), command=self._add_target).pack(side="left")

        gen = ctk.CTkFrame(body, fg_color="transparent")
        gen.pack(fill="x", pady=(10, 0))
        for text, cmd, color, tc in (
            ("📁 Load .txt", self._load_txt, CARD, TEXT),
            ("3L × 500", lambda: self._gen_names(3), CARD, TEXT),
            ("4L × 500", lambda: self._gen_names(4), CARD, TEXT),
            ("⚡ 3L FULL", self._gen_full_3l, CARD_HI, ACCENT),
            ("Smart Gen", self._gen_smart, CARD, TEXT),
        ):
            ctk.CTkButton(gen, text=text, height=34, corner_radius=9, fg_color=color,
                          hover_color=CARD_HI, text_color=tc, border_width=1,
                          border_color=BORDER, font=font(11), command=cmd).pack(
                side="left", padx=(0, 6)
            )

        pattern_row = ctk.CTkFrame(body, fg_color="transparent")
        pattern_row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(pattern_row, text="Pattern", font=font(10, "bold"),
                     text_color=TEXT3).pack(side="left", padx=(0, 8))
        self.ent_pattern = ctk.CTkEntry(
            pattern_row, placeholder_text=get_pattern_examples()[0] if get_pattern_examples() else "a_d",
            height=34, corner_radius=9, fg_color=CARD, border_color=BORDER, font=font(11),
        )
        self.ent_pattern.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(pattern_row, text="Generate", width=110, height=34, corner_radius=9,
                      fg_color=CARD, hover_color=CARD_HI, text_color=TEXT, border_width=1,
                      border_color=BORDER, font=font(11),
                      command=self._gen_pattern).pack(side="left")

        # --- queue strip ---
        queue_card = Card(tab, "Queue", "")
        queue_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        qbody = queue_card.content()
        qrow = ctk.CTkFrame(qbody, fg_color="transparent")
        qrow.pack(fill="x")
        self.lbl_queue_total = ctk.CTkLabel(qrow, text="0 nama menunggu", font=font(12, "bold"),
                                            text_color=WARN)
        self.lbl_queue_total.pack(side="left")
        self.progress = ctk.CTkProgressBar(qrow, height=8, corner_radius=4,
                                           progress_color=ACCENT, fg_color=CARD)
        self.progress.pack(side="left", fill="x", expand=True, padx=16)
        self.progress.set(0)
        ctk.CTkButton(qrow, text="Clear Queue", width=120, height=32, corner_radius=9,
                      fg_color=CARD, hover_color="#33202a", text_color=BAD, border_width=1,
                      border_color="#43222c", font=font(11),
                      command=self._clear_queue).pack(side="right")

        # --- results ---
        results = ctk.CTkFrame(tab, fg_color="transparent")
        results.grid(row=2, column=0, sticky="nsew")
        results.grid_columnconfigure((0, 1), weight=1, uniform="res")
        results.grid_rowconfigure(0, weight=1)

        avail_card = Card(results, "🟢 Available", "tersimpan di available.txt")
        avail_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        avail_body = avail_card.content()
        self.avail_box = ListPane(avail_body, height=12, color=ACCENT)
        self.avail_box.pack(fill="both", expand=True)
        avail_row = ctk.CTkFrame(avail_body, fg_color="transparent")
        avail_row.pack(fill="x", pady=(8, 0))
        self.lbl_avail_count = ctk.CTkLabel(avail_row, text="0 found", font=font(10, "bold"),
                                             text_color=ACCENT)
        self.lbl_avail_count.pack(side="left")
        ctk.CTkButton(avail_row, text="Export", width=90, height=28, corner_radius=8,
                      fg_color=CARD, hover_color=CARD_HI, text_color=TEXT2, border_width=1,
                      border_color=BORDER, font=font(10),
                      command=lambda: self._export(AVAILABLE_FILE)).pack(side="right")

        claimed_card = Card(results, "🏆 Claimed", "tersimpan di claimed.txt")
        claimed_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        claimed_body = claimed_card.content()
        self.claimed_box = ListPane(claimed_body, height=12, color=OK)
        self.claimed_box.pack(fill="both", expand=True)
        claimed_row = ctk.CTkFrame(claimed_body, fg_color="transparent")
        claimed_row.pack(fill="x", pady=(8, 0))
        self.lbl_claimed_count = ctk.CTkLabel(claimed_row, text="0 claimed",
                                               font=font(10, "bold"), text_color=OK)
        self.lbl_claimed_count.pack(side="left")
        ctk.CTkButton(claimed_row, text="Export", width=90, height=28, corner_radius=8,
                      fg_color=CARD, hover_color=CARD_HI, text_color=TEXT2, border_width=1,
                      border_color=BORDER, font=font(10),
                      command=lambda: self._export(CLAIMED_FILE)).pack(side="right")

    # ------------------------------------------------------------------ #
    # Tab: Sniper
    # ------------------------------------------------------------------ #
    def _tab_sniper(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure((0, 1), weight=1, uniform="sniper")
        tab.grid_rowconfigure(1, weight=1)

        ctrl = Card(tab, "Auto Claim", "claim otomatis begitu nama AVAILABLE")
        ctrl.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(2, 10))
        body = ctrl.content()

        self.sw_auto_claim = ctk.CTkSwitch(
            body, text="Auto claim aktif", font=font(12), progress_color=OK,
            button_color=TEXT, button_hover_color=TEXT, text_color=TEXT,
            command=self._toggle_auto_claim,
        )
        self.sw_auto_claim.pack(anchor="w", pady=(0, 10))
        if self.cfg.get("auto_claim"):
            self.sw_auto_claim.select()

        self.sw_watch = ctk.CTkSwitch(
            body, text="Watch mode (re-check nama taken)", font=font(12),
            progress_color=ACCENT, button_color=TEXT, button_hover_color=TEXT,
            text_color=TEXT, command=self._toggle_watch,
        )
        self.sw_watch.pack(anchor="w", pady=(0, 12))
        if self.cfg.get("watch_mode", True):
            self.sw_watch.select()

        ctk.CTkLabel(body, text="Claim status", font=font(10, "bold"),
                     text_color=TEXT3).pack(anchor="w")
        self.sniper_log_box = LogView(body, height=8)
        self.sniper_log_box.pack(fill="both", expand=True, pady=(4, 0))

        watch = Card(tab, "Watch List", "target yang sedang dipantau")
        watch.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(2, 10))
        wbody = watch.content()

        wrow = ctk.CTkFrame(wbody, fg_color="transparent")
        wrow.pack(fill="x", pady=(0, 8))
        self.ent_watch = ctk.CTkEntry(wrow, placeholder_text="username untuk di-watch",
                                      height=36, corner_radius=9, fg_color=CARD,
                                      border_color=BORDER, font=font(12))
        self.ent_watch.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(wrow, text="Watch", width=90, height=36, corner_radius=9,
                      fg_color=ACCENT, hover_color="#00cfdd", text_color="#04222b",
                      font=font(11, "bold"), command=self._add_watch).pack(side="left")

        self.watch_box = ListPane(wbody, height=10, color=WARN)
        self.watch_box.pack(fill="both", expand=True)

        live = Card(tab, "Live Activity", "available, claim, dan error terbaru")
        live.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 2))
        lbody = live.content()
        self.activity_box = LogView(lbody, height=10)
        self.activity_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Tab: Accounts
    # ------------------------------------------------------------------ #
    def _tab_accounts(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        add = Card(tab, "Tambah Akun Microsoft", "login langsung — tanpa Azure, tanpa OAuth2")
        add.grid(row=0, column=0, sticky="ew", pady=(2, 10))
        body = add.content()

        # Email/Password Microsoft login (alur launcher, client id bawaan)
        ep_row = ctk.CTkFrame(body, fg_color="transparent")
        ep_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(ep_row, text="Email", font=font(10, "bold"), text_color=TEXT3,
                     width=60, anchor="w").pack(side="left")
        self.ent_ep_email = ctk.CTkEntry(
            ep_row, placeholder_text="email@outlook.com", height=40, corner_radius=9,
            fg_color=CARD, border_color=BORDER, font=font(12),
        )
        self.ent_ep_email.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(ep_row, text="Password", font=font(10, "bold"), text_color=TEXT3,
                     width=70, anchor="w").pack(side="left")
        self.ent_ep_password = ctk.CTkEntry(
            ep_row, placeholder_text="password", height=40, corner_radius=9,
            fg_color=CARD, border_color=BORDER, font=font(12), show="•",
        )
        self.ent_ep_password.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(ep_row, text="🔑  Login Microsoft", width=150, height=40,
                      corner_radius=9, fg_color=OK, hover_color="#00d988",
                      text_color="#05231a", font=font(12, "bold"),
                      command=self._add_email_password_account).pack(side="left")

        lbl_row = ctk.CTkFrame(body, fg_color="transparent")
        lbl_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(lbl_row, text="Label", font=font(10, "bold"), text_color=TEXT3,
                     width=60, anchor="w").pack(side="left")
        self.ent_acc_label = ctk.CTkEntry(lbl_row, placeholder_text="nama akun (opsional)",
                                          height=36, corner_radius=9, fg_color=CARD,
                                          border_color=BORDER, font=font(12))
        self.ent_acc_label.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # Token login
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row2, text="Token", font=font(10, "bold"), text_color=TEXT3,
                     width=60, anchor="w").pack(side="left")
        self.ent_token = ctk.CTkEntry(
            row2, placeholder_text="mc token (eyJ…) / MS refresh (M.C…) / MS token (M.R…, eyJ…)",
            height=40, corner_radius=9, fg_color=CARD, border_color=BORDER,
            font=font(11),
        )
        self.ent_token.pack(side="left", fill="x", expand=True, padx=(0, 12), ipadx=8)
        self.opt_token_type = ctk.CTkOptionMenu(
            row2, values=["Auto-detect", "mc_token", "ms_token"], width=130, height=38,
            corner_radius=9, fg_color=CARD, button_color=CARD_HI, button_hover_color=BORDER_HI,
            dropdown_fg_color=PANEL, dropdown_hover_color=CARD_HI, font=font(11),
        )
        self.opt_token_type.set("Auto-detect")
        self.opt_token_type.pack(side="left")

        row3 = ctk.CTkFrame(body, fg_color="transparent")
        row3.pack(fill="x")
        ctk.CTkButton(row3, text="➕  Add via Token", width=170, height=40, corner_radius=9,
                      fg_color=ACCENT, hover_color="#00cfdd", text_color="#04222b",
                      font=font(12, "bold"),
                      command=self._add_token_account).pack(side="left", padx=(0, 8))
        self.lbl_acc_hint = ctk.CTkLabel(row3, text="", font=font(10), text_color=TEXT3)
        self.lbl_acc_hint.pack(side="left", padx=6)

        lst = Card(tab, "Akun Terdaftar", "status token & refresh")
        lst.grid(row=1, column=0, sticky="nsew", pady=(0, 2))
        lbody = lst.content()

        self.accounts_box = ListPane(lbody, height=9, color=TEXT)
        self.accounts_box.pack(fill="both", expand=True)

        btn_row = ctk.CTkFrame(lbody, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btn_row, text="🔄 Refresh Tokens", width=160, height=32,
                      corner_radius=9, fg_color=CARD, hover_color=CARD_HI,
                      text_color=TEXT2, border_width=1, border_color=BORDER,
                      font=font(11), command=self._refresh_all_tokens).pack(side="left")
        ctk.CTkButton(btn_row, text="Reload", width=100, height=32, corner_radius=9,
                      fg_color=CARD, hover_color=CARD_HI, text_color=TEXT2,
                      border_width=1, border_color=BORDER, font=font(11),
                      command=self._reload_accounts).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Clear All", width=110, height=32, corner_radius=9,
                      fg_color=CARD, hover_color="#33202a", text_color=BAD,
                      border_width=1, border_color="#43222c", font=font(11),
                      command=self._clear_all_accounts).pack(side="right")

        self._reload_accounts()

    # ------------------------------------------------------------------ #
    # Tab: Proxies
    # ------------------------------------------------------------------ #
    def _tab_proxies(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        ctrl = Card(tab, "Proxy Manager", "HTTP · SOCKS4 · SOCKS5")
        ctrl.grid(row=0, column=0, sticky="ew", pady=(2, 10))
        body = ctrl.content()

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="📁  Load proxies.txt", width=180, height=38,
                      corner_radius=9, fg_color=ACCENT, hover_color="#00cfdd",
                      text_color="#04222b", font=font(11, "bold"),
                      command=self._load_proxies).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🔍  Test All", width=130, height=38, corner_radius=9,
                      fg_color=CARD_HI, hover_color="#2c2c3d", text_color=ACCENT2,
                      border_width=1, border_color=BORDER_HI, font=font(11, "bold"),
                      command=self._test_proxies).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🧹  Clean Dead", width=130, height=38, corner_radius=9,
                      fg_color=CARD, hover_color=CARD_HI, text_color=TEXT2,
                      border_width=1, border_color=BORDER, font=font(11),
                      command=self._clean_proxies).pack(side="left")

        self.sw_proxy_rot = ctk.CTkSwitch(
            row, text="Auto rotate", font=font(11), progress_color=ACCENT,
            button_color=TEXT, button_hover_color=TEXT, text_color=TEXT2,
            command=lambda: self._save_setting("proxy_rotate", bool(self.sw_proxy_rot.get())),
        )
        self.sw_proxy_rot.pack(side="right")
        if self.cfg.get("proxy_rotate", True):
            self.sw_proxy_rot.select()

        self.lbl_proxy_stats = ctk.CTkLabel(body, text="belum ada proxy dimuat",
                                             font=font(10), text_color=TEXT3)
        self.lbl_proxy_stats.pack(anchor="w", pady=(10, 0))

        lst = Card(tab, "Proxy List", "host:port · http:host:port:user:pass · socks5://host:port")
        lst.grid(row=1, column=0, sticky="nsew", pady=(0, 2))
        lbody = lst.content()
        self.proxy_box = ListPane(lbody, height=12, color=TEXT2)
        self.proxy_box.pack(fill="both", expand=True)

        self._reload_proxies()

    # ------------------------------------------------------------------ #
    # Tab: Settings
    # ------------------------------------------------------------------ #
    def _tab_settings(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure((0, 1), weight=1, uniform="set")
        tab.grid_rowconfigure(1, weight=1)

        perf = Card(tab, "Performance", "kecepatan dan batas request")
        perf.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(2, 10))
        pbody = perf.content()

        self.sld_threads, self.lbl_threads = self._slider(pbody, "Threads", 1, 100,
                                                          int(self.cfg.get("threads", 15)))
        self.lbl_timeout = self._entry(pbody, "Timeout (detik)", str(self.cfg.get("timeout", 10.0)))

        behavior = Card(tab, "Behavior", "checker dan claim")
        behavior.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(2, 10))
        bbody = behavior.content()

        self.sw_stealth = self._switch(bbody, "Stealth headers", "stealth_mode", ACCENT2)
        self.sw_sound = self._switch(bbody, "Sound saat claim sukses", "sound_notifications", OK)
        self.sw_auto_claim_cfg = self._switch(bbody, "Auto claim", "auto_claim", OK)
        self.sw_watch_cfg = self._switch(bbody, "Watch mode", "watch_mode", WARN)

        notify = Card(tab, "Discord Notifications", "webhook untuk available & claimed")
        notify.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        nbody = notify.content()

        nrow = ctk.CTkFrame(nbody, fg_color="transparent")
        nrow.pack(fill="x")
        ctk.CTkLabel(nrow, text="Webhook URL", font=font(10, "bold"), text_color=TEXT3,
                     width=110, anchor="w").pack(side="left")
        self.ent_webhook = ctk.CTkEntry(nrow, placeholder_text="https://discord.com/api/webhooks/…",
                                        height=36, corner_radius=9, fg_color=CARD,
                                        border_color=BORDER, font=font(11))
        self.ent_webhook.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.ent_webhook.insert(0, self.cfg.get("discord_webhook_url", ""))

        trow = ctk.CTkFrame(nbody, fg_color="transparent")
        trow.pack(fill="x", pady=(10, 0))
        self.sw_discord = self._switch(trow, "Aktifkan webhook", "use_discord_webhook", ACCENT2)
        self.sw_notify_avail = self._switch(trow, "Notify available", "notify_on_available", ACCENT)
        self.sw_notify_claim = self._switch(trow, "Notify claimed", "notify_on_claimed", OK)

        save_row = ctk.CTkFrame(tab, fg_color="transparent")
        save_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        ctk.CTkButton(save_row, text="💾  Save Settings", width=200, height=44,
                      corner_radius=10, fg_color=ACCENT, hover_color="#00cfdd",
                      text_color="#04222b", font=font(13, "bold"),
                      command=self._save_all_settings).pack(side="left")
        self.lbl_saved = ctk.CTkLabel(save_row, text="", font=font(11), text_color=OK)
        self.lbl_saved.pack(side="left", padx=12)

    # -- settings helpers --------------------------------------------------
    def _labeled_row(self, parent: ctk.CTkFrame, label: str, widget: Any,
                     value: str = "") -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, font=font(11), text_color=TEXT2, width=130,
                     anchor="w").pack(side="left")
        widget.pack(in_=row, side="left", fill="x", expand=True)
        if value:
            widget.insert(0, value)
        return ctk.CTkLabel(row, text="", font=font(10), text_color=TEXT3)

    def _slider(self, parent: ctk.CTkFrame, label: str, lo: int, hi: int,
                value: int) -> tuple:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, font=font(11), text_color=TEXT2, width=130,
                     anchor="w").pack(side="left")
        slider = ctk.CTkSlider(row, from_=lo, to=hi, height=16, corner_radius=8,
                               button_color=ACCENT, button_hover_color="#00cfdd",
                               progress_color=ACCENT2, fg_color=CARD)
        slider.set(value)
        slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        value_lbl = ctk.CTkLabel(row, text=str(value), font=font(11, "bold"),
                                 text_color=ACCENT, width=38)
        value_lbl.pack(side="left")
        slider.configure(command=lambda v: value_lbl.configure(text=str(int(float(v)))))
        return slider, value_lbl

    def _entry(self, parent: ctk.CTkFrame, label: str, value: str) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, height=34, corner_radius=9, fg_color=CARD,
                             border_color=BORDER, font=font(12))
        self._labeled_row(parent, label, entry, value)
        return entry

    def _switch(self, parent: ctk.CTkFrame, label: str, key: str, color: str) -> ctk.CTkSwitch:
        sw = ctk.CTkSwitch(parent, text=label, font=font(11), progress_color=color,
                           button_color=TEXT, button_hover_color=TEXT, text_color=TEXT2,
                           command=lambda: self._save_setting(key, bool(sw.get())))
        if key == "discord_webhook_url":
            pass
        sw.pack(anchor="w", pady=3)
        if self.cfg.get(key):
            sw.select()
        return sw

    # ------------------------------------------------------------------ #
    # Tab: Stats
    # ------------------------------------------------------------------ #
    def _tab_stats(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure((0, 1, 2), weight=1, uniform="st")
        tab.grid_rowconfigure(2, weight=1)

        head = Card(tab, "Session Overview", "statistik sesi berjalan")
        head.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(2, 10))
        hbody = head.content()

        grid = ctk.CTkFrame(hbody, fg_color="transparent")
        grid.pack(fill="x")
        for idx, (key, label, color) in enumerate((
            ("st_checked", "Total Checked", TEXT),
            ("st_available", "Available", ACCENT),
            ("st_claimed", "Claimed", OK),
            ("st_taken", "Taken", TAKEN_C),
            ("st_errors", "Errors", BAD),
            ("st_rate", "Rate Limited", WARN),
        )):
            chip = StatChip(grid, label, "0", color, wide=True)
            chip.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=(0, 8), pady=4)
            grid.grid_columnconfigure(idx % 3, weight=1, uniform="stg")
            self.stats_labels[key] = chip  # type: ignore[assignment]

        detail = Card(tab, "Throughput", "kecepatan dan durasi")
        detail.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        dbody = detail.content()

        drow = ctk.CTkFrame(dbody, fg_color="transparent")
        drow.pack(fill="x")
        ctk.CTkLabel(drow, text="Success rate", font=font(11), text_color=TEXT2,
                     width=110, anchor="w").pack(side="left")
        self.st_success_bar = ctk.CTkProgressBar(drow, height=10, corner_radius=5,
                                                  progress_color=OK, fg_color=CARD)
        self.st_success_bar.set(0)
        self.st_success_bar.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.st_success_lbl = ctk.CTkLabel(drow, text="0.0%", font=font(11, "bold"),
                                            text_color=OK, width=60)
        self.st_success_lbl.pack(side="left")

        meta = ctk.CTkFrame(dbody, fg_color="transparent")
        meta.pack(fill="x", pady=(10, 0))
        self.st_meta_lbl = ctk.CTkLabel(meta, text="uptime 00:00:00   ·   0.00 checks/s",
                                         font=font(10), text_color=TEXT3)
        self.st_meta_lbl.pack(anchor="w")

        hist = Card(tab, "Claim History", "tersimpan di claim_history.json")
        hist.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 2))
        hbody2 = hist.content()
        self.history_box = ListPane(hbody2, height=8, color=OK)
        self.history_box.pack(fill="both", expand=True)
        self._reload_history()

    def _reload_history(self) -> None:
        rows = []
        for item in self.controller.claim_history[-200:][::-1]:
            rows.append(f"{item.get('time', '?')}   {item.get('name', '?'):<16} {item.get('account', '')}")
        self.history_box.replace(rows, prefix="✓")

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
        self.after(80, self._pump_events)

    def _handle_event(self, kind: str, payload: Any) -> None:
        if kind == "log":
            tag, text = payload
            self._log(tag, text)
            self.activity_box.write(tag, text)
        elif kind == "result":
            res: CheckResult = payload
            if res.status == NameStatus.AVAILABLE:
                self._log("avail", f"{res.name:<14} AVAILABLE ✓")
            elif res.status == NameStatus.TAKEN:
                self._log("taken", f"{res.name:<14} taken")
            else:
                self._log("bad", f"{res.name:<14} {res.status.value.lower()} {res.reason}")
        elif kind == "available":
            name = payload
            self.avail_box.append(name)
            self.avail_box.text.see("end")
            self.lbl_avail_count.configure(text=f"{self.avail_box.count} found")
            self.activity_box.write("avail", f"AVAILABLE  {name}")
            self._toast(f"Nama tersedia: {name}", ACCENT)
        elif kind == "claimed":
            name, acc = payload
            self.claimed_box.append(f"{name}  ·  {acc}")
            self.lbl_claimed_count.configure(text=f"{self.claimed_box.count} claimed")
            self.activity_box.write("claim", f"CLAIMED  {name}  via {acc}")
            self._reload_history()
            self._show_claim_modal(name, acc)
        elif kind == "status":
            running = "RUNNING" in str(payload)
            self.status_text.configure(text=str(payload))
            self.status_dot.configure(text_color=OK if running else WARN)
            self.side_status.configure(text=f"● {'RUNNING' if running else 'IDLE'}",
                                       text_color=OK if running else WARN)
            self.header_sub.configure(text=str(payload))
            self.btn_start.configure(state="disabled" if running else "normal")
            self.btn_stop.configure(state="normal" if running else "disabled")
            if running:
                self.progress.configure(mode="indeterminate")
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(0)

    def _log(self, tag: str, message: str) -> None:
        self.sniper_log_box.write(tag, message)

    def _tick_stats(self) -> None:
        stats = self.controller.stats.get_stats()
        queue_len = self.controller.queue_size()

        self.chips["checked"].set(stats["total_checked"])
        self.chips["available"].set(stats["available"])
        self.chips["claimed"].set(stats["claimed"])
        self.chips["queue"].set(queue_len)
        self.chips["threads"].set(int(self.cfg.get("threads", 15)) if self.controller.running else 0)

        self.side_uptime.configure(text=f"uptime  {stats['uptime']}")
        self.side_queue.configure(text=f"queue  {queue_len}")
        self.lbl_queue_total.configure(
            text=f"{queue_len} nama menunggu" + (" · berjalan" if self.controller.running else "")
        )

        for key in ("st_checked", "st_available", "st_claimed", "st_taken", "st_errors", "st_rate"):
            if key in self.stats_labels:
                mapping = {
                    "st_checked": stats["total_checked"],
                    "st_available": stats["available"],
                    "st_claimed": stats["claimed"],
                    "st_taken": stats["taken"],
                    "st_errors": stats["errors"],
                    "st_rate": stats["rate_limited"],
                }
                self.stats_labels[key].set(mapping[key])  # type: ignore[attr-defined]

        rate = float(stats["success_rate"])
        self.st_success_bar.set(max(0.0, min(rate / 100.0, 1.0)))
        self.st_success_lbl.configure(text=f"{rate:.1f}%")
        self.st_meta_lbl.configure(
            text=f"uptime {stats['uptime']}   ·   {stats['checks_per_sec']:.2f} checks/s"
                 f"   ·   {stats['taken']} taken"
        )

        alive = sum(1 for p in self.controller.proxies if getattr(p, "alive", False))
        self.foot_left.configure(
            text=f"{APP_NAME} {APP_VERSION}   ·   {'running' if self.controller.running else 'idle'}"
                 f"   ·   {len(self.controller.accounts)} akun"
        )
        self.foot_right.configure(
            text=f"checks/s {stats['checks_per_sec']:.2f}   ·   proxy {alive} alive"
                 f"   ·   discord {'on' if self.cfg.get('use_discord_webhook') else 'off'}"
        )

        # refresh daftar queue sesekali (murah, max 0.4/detik)
        if time.time() - self._last_queue_ui > 2.0:
            self._last_queue_ui = time.time()
            if self.active_tab == "Checker" and queue_len and queue_len <= 400:
                pass  # queue ditampilkan lewat counter agar tidak flicker

        self.after(500, self._tick_stats)

    def _tick_spinner(self) -> None:
        if self.controller.running:
            self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
            self.header_sub.configure(
                text=f"{self._spinner_frames[self._spinner_idx]} memeriksa {self.controller.queue_size()} nama…"
            )
        self.after(300, self._tick_spinner)

    # ------------------------------------------------------------------ #
    # Feedback
    # ------------------------------------------------------------------ #
    def _toast(self, message: str, color: str = ACCENT, ms: int = 3600) -> None:
        if self._toast_widget is not None:
            try:
                self._toast_widget.destroy()
            except Exception:  # noqa: BLE001
                pass
        toast = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10, border_width=1,
                             border_color=color)
        toast.place(relx=0.985, y=76, anchor="ne")
        ctk.CTkFrame(toast, width=4, fg_color=color, corner_radius=2).pack(
            side="left", fill="y", padx=(6, 0), pady=8
        )
        ctk.CTkLabel(toast, text=message, font=font(11, "bold"), text_color=color).pack(
            side="left", padx=12, pady=10
        )
        self._toast_widget = toast
        self.after(ms, lambda: self._dismiss_toast(toast))

    def _dismiss_toast(self, widget: ctk.CTkFrame) -> None:
        try:
            if widget.winfo_exists():
                widget.destroy()
        except Exception:  # noqa: BLE001
            pass
        if self._toast_widget is widget:
            self._toast_widget = None

    def _show_claim_modal(self, name: str, account: str) -> None:
        modal = ctk.CTkToplevel(self)
        modal.title("Claim Success")
        modal.configure(fg_color=BG)
        modal.geometry("440x260")
        modal.resizable(False, False)
        modal.attributes("-topmost", True)
        modal.transient(self)

        card = ctk.CTkFrame(modal, fg_color=PANEL, corner_radius=16, border_width=1,
                            border_color=OK)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(card, text="🎉", font=font(34)).pack(pady=(18, 0))
        ctk.CTkLabel(card, text="USERNAME CLAIMED", font=font(16, "bold"),
                     text_color=OK).pack()
        ctk.CTkLabel(card, text=name, font=font(26, "bold", MONO),
                     text_color=ACCENT).pack(pady=(4, 2))
        ctk.CTkLabel(card, text=f"via {account}", font=font(10), text_color=TEXT3).pack()
        ctk.CTkButton(card, text="Nice!", width=150, height=38, corner_radius=10,
                      fg_color=OK, hover_color="#00d988", text_color="#05231a",
                      font=font(12, "bold"), command=modal.destroy).pack(pady=14)

        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 440) // 2
        y = self.winfo_y() + (self.winfo_height() - 260) // 3
        modal.geometry(f"+{max(0, x)}+{max(0, y)}")

    # ------------------------------------------------------------------ #
    # Actions: checker
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
        if res.status == NameStatus.AVAILABLE:
            append_to_file(AVAILABLE_FILE, res.name)
            self.controller.stats.increment("total")
            self.controller.stats.increment("available")
            self.controller.emit("available", res.name)
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
            self._log("info", f"{name} ditambahkan ke queue")
            self.ent_check.delete(0, "end")
        else:
            self._toast(f"'{name}' tidak valid / sudah ada di queue", WARN, 2600)

    def _add_watch(self) -> None:
        name = self.ent_watch.get().strip().lower()
        if not name:
            return
        if self.controller.enqueue(name):
            self.watch_box.append(name)
            self._log("info", f"watch: {name}")
            self.ent_watch.delete(0, "end")
        else:
            self._toast(f"'{name}' sudah dipantau", WARN, 2400)

    def _load_txt(self) -> None:
        path = filedialog.askopenfilename(title="Pilih combo .txt",
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        names = load_names_from_file(path)
        added = self.controller.enqueue_many(names)
        self._log("ok", f"{added} nama dimuat dari {os.path.basename(path)}")
        self._toast(f"{added} nama masuk queue", OK, 2600)

    def _gen_names(self, length: int) -> None:
        names = generate_random(500, length)
        added = self.controller.enqueue_many(names)
        self._log("ok", f"generate {added} nama {length}L")
        self._toast(f"{added} nama {length}L ditambahkan", ACCENT, 2600)

    def _gen_full_3l(self) -> None:
        names = enumerate_ordered(3)
        added = self.controller.enqueue_many(names)
        self._log("ok", f"3L FULL: {added} kombinasi masuk queue (urut prioritas)")
        self._toast(f"3L FULL — {added} nama di queue", ACCENT, 3200)

    def _gen_smart(self) -> None:
        names = generate_smart_random(500, 3)
        added = self.controller.enqueue_many(names)
        self._log("ok", f"smart gen: {added} nama")
        self._toast(f"Smart gen — {added} nama", ACCENT, 2600)

    def _gen_pattern(self) -> None:
        pattern = self.ent_pattern.get().strip()
        if not pattern:
            self._toast("Isi pattern dulu, contoh: a_d atau aaa", WARN, 2600)
            return
        names = generate_pattern([pattern], 500)
        added = self.controller.enqueue_many(names)
        self._log("ok", f"pattern {pattern}: {added} nama")
        self._toast(f"Pattern {pattern} — {added} nama", ACCENT, 2600)

    def _clear_queue(self) -> None:
        if not messagebox.askyesno("Clear Queue", "Hapus semua nama yang menunggu di queue?"):
            return
        cleared = self.controller.clear_queue()
        self._toast(f"Queue dibersihkan ({cleared})", WARN, 2400)

    def _export(self, path: str) -> None:
        if not os.path.exists(path):
            self._toast(f"{path} belum ada", WARN, 2400)
            return
        target = filedialog.asksaveasfilename(defaultextension=".txt",
                                              initialfile=os.path.basename(path))
        if not target:
            return
        try:
            with open(path, "r", encoding="utf-8") as src, open(target, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            self._toast(f"Diexport ke {os.path.basename(target)}", OK, 2600)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Export gagal: {exc}", BAD, 3200)

    def _start(self) -> None:
        if self.controller.running:
            return
        self._save_all_settings_quiet()
        self.controller.start()
        self._log("ok", "engine dijalankan")

    def _stop(self) -> None:
        if not self.controller.running:
            return
        self.controller.stop()
        self._log("warn", "engine dihentikan")

    def _toggle_auto_claim(self) -> None:
        value = bool(self.sw_auto_claim.get())
        self._save_setting("auto_claim", value)
        if hasattr(self, "sw_auto_claim_cfg"):
            (self.sw_auto_claim_cfg.select if value else self.sw_auto_claim_cfg.deselect)()
        self._log("info", f"auto claim {'aktif' if value else 'nonaktif'}")

    def _toggle_watch(self) -> None:
        value = bool(self.sw_watch.get())
        self._save_setting("watch_mode", value)
        if hasattr(self, "sw_watch_cfg"):
            (self.sw_watch_cfg.select if value else self.sw_watch_cfg.deselect)()
        self._log("info", f"watch mode {'aktif' if value else 'nonaktif'}")

    # ------------------------------------------------------------------ #
    # Actions: accounts
    # ------------------------------------------------------------------ #
    def _add_token_account(self) -> None:
        token = self.ent_token.get().strip()
        email = self.ent_acc_label.get().strip()
        if not token:
            self._toast("Token belum diisi", WARN, 3000)
            return
        kind = self.opt_token_type.get()
        if kind == "Auto-detect":
            kind = clm.classify_token(token)
            if kind == "unknown":
                kind = "mc_token"
        self.lbl_acc_hint.configure(text=f"verifikasi {kind}…", text_color=WARN)
        self._log("info", f"menambahkan akun via {kind}…")

        def work() -> None:
            try:
                if kind == "ms_token":
                    acc = clm.login_with_ms_token(token, email)
                else:
                    acc = clm.login_with_mc_token(token, email)
                self.controller.accounts.append(acc)
                clm.save_accounts(self.controller.accounts)
                state = "verified" if acc.token_verified else "unverified (429)"
                self.after(0, lambda: self._toast(f"Akun ditambahkan: {acc.label()}", OK, 3200))
                self.after(0, lambda: self.ent_token.delete(0, "end"))
                self.after(0, lambda: self.lbl_acc_hint.configure(text="akun siap", text_color=OK))
                self.after(0, self._reload_accounts)
                self.after(0, lambda: self._log("ok", f"akun ditambahkan ({state}): {acc.label()}"))
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda m=msg: self._log("bad", f"token invalid: {m}"))
                self.after(0, lambda: self._toast(f"Token gagal: {msg}", BAD, 4600))
                self.after(0, lambda: self.lbl_acc_hint.configure(text="token invalid", text_color=BAD))

        threading.Thread(target=work, daemon=True).start()

    def _add_email_password_account(self) -> None:
        email = self.ent_ep_email.get().strip()
        password = self.ent_ep_password.get().strip()
        if not email or not password:
            self._toast("Email dan password wajib diisi", WARN, 3000)
            return
        self.lbl_acc_hint.configure(text="login Microsoft…", text_color=WARN)
        self._log("info", f"login microsoft via email: {email}…")

        def work() -> None:
            try:
                acc = clm.login_with_email_password(email, password)
                self.controller.accounts.append(acc)
                clm.save_accounts(self.controller.accounts)
                self.after(0, lambda: self._toast(f"Akun ditambahkan: {acc.label()}", OK, 3200))
                self.after(0, lambda: self.ent_ep_email.delete(0, "end"))
                self.after(0, lambda: self.ent_ep_password.delete(0, "end"))
                self.after(0, lambda: self.lbl_acc_hint.configure(text="akun siap", text_color=OK))
                self.after(0, self._reload_accounts)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                self.after(0, lambda m=msg: self._log("bad", f"login gagal: {m}"))
                self.after(0, lambda: self._toast(f"Login gagal: {msg}", BAD, 4600))
                self.after(0, lambda: self.lbl_acc_hint.configure(text="login gagal", text_color=BAD))

        threading.Thread(target=work, daemon=True).start()

    def _reload_accounts(self) -> None:
        self.controller.accounts = clm.load_accounts()
        rows = []
        for idx, acc in enumerate(self.controller.accounts, 1):
            token_state = "VALID" if acc.is_token_valid() else "EXPIRED"
            refresh = "refresh ✓" if getattr(acc, "refresh_token", None) else "token-only"
            rows.append(f"[{idx:02d}] {acc.label():<34} {token_state:<8} {refresh}")
        if not rows:
            rows = ["belum ada akun — login email+password atau tempel token"]
        self.accounts_box.replace(rows, prefix="›")

    def _refresh_all_tokens(self) -> None:
        if not self.controller.accounts:
            self._toast("Belum ada akun", WARN, 2400)
            return
        self._log("info", "refresh semua token…")

        def work() -> None:
            for acc in list(self.controller.accounts):
                try:
                    clm.refresh_account_tokens(acc)
                    self.after(0, lambda a=acc: self._log("ok", f"token refreshed: {a.label()}"))
                except Exception as exc:  # noqa: BLE001
                    self.after(0, lambda a=acc, e=exc: self._log("bad", f"refresh gagal {a.label()}: {e}"))
            clm.save_accounts(self.controller.accounts)
            self.after(0, self._reload_accounts)
            self.after(0, lambda: self._toast("Refresh token selesai", OK, 2600))

        threading.Thread(target=work, daemon=True).start()

    def _clear_all_accounts(self) -> None:
        if not messagebox.askyesno("Clear Accounts", "Hapus semua akun tersimpan?"):
            return
        self.controller.accounts = []
        clm.save_accounts([])
        self._reload_accounts()
        self._toast("Semua akun dihapus", WARN, 2400)

    # ------------------------------------------------------------------ #
    # Actions: proxies
    # ------------------------------------------------------------------ #
    def _load_proxies(self) -> None:
        path = filedialog.askopenfilename(title="Pilih proxies.txt",
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        proxies = ProxyManager.load_from_file(path)
        self.controller.proxies = proxies
        self.controller.proxy_manager.proxies = proxies
        self._save_setting("proxy_file", path)
        self._reload_proxies()
        self._log("ok", f"{len(proxies)} proxy dimuat")
        self._toast(f"{len(proxies)} proxy dimuat", OK, 2600)

    def _test_proxies(self) -> None:
        if not self.controller.proxies:
            self._toast("Belum ada proxy", WARN, 2400)
            return
        self.lbl_proxy_stats.configure(text="menguji proxy…", text_color=WARN)
        self._log("info", "test semua proxy…")

        def work() -> None:
            result = self.controller.proxy_manager.test_all()
            self.after(0, lambda: self.lbl_proxy_stats.configure(
                text=f"{result['alive']} alive · {result['dead']} dead · {result['total']} total",
                text_color=OK if result["alive"] else BAD))
            self.after(0, self._reload_proxies)
            self.after(0, lambda: self._toast(
                f"Proxy: {result['alive']} alive / {result['dead']} dead",
                OK if result["alive"] else WARN, 3000))

        threading.Thread(target=work, daemon=True).start()

    def _clean_proxies(self) -> None:
        removed = self.controller.proxy_manager.auto_clean()
        self.controller.proxies = self.controller.proxy_manager.proxies
        self._reload_proxies()
        self._log("warn", f"{removed} proxy buruk dihapus")
        self._toast(f"{removed} proxy dihapus", WARN, 2400)

    def _reload_proxies(self) -> None:
        rows = []
        for idx, proxy in enumerate(self.controller.proxies, 1):
            state = "ALIVE" if getattr(proxy, "alive", False) else "DEAD"
            rows.append(f"[{idx:03d}] {proxy.host:>15}:{proxy.port:<6} {proxy.proxy_type:<7} "
                        f"{state:<5} score {getattr(proxy, 'score', 0):>3.0f}")
        if not rows:
            rows = ["belum ada proxy — klik Load proxies.txt"]
        self.proxy_box.replace(rows, prefix="›")

    # ------------------------------------------------------------------ #
    # Actions: settings
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

        def as_int(entry: ctk.CTkEntry, fallback: int) -> int:
            try:
                return int(float(entry.get().strip()))
            except (ValueError, AttributeError):
                return fallback

        return {
            "threads": int(self.sld_threads.get()),
            "timeout": min(max(as_float(self.lbl_timeout, 10.0), 1.0), 60.0),
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
            logger.warning("save settings failed: %s", exc)

    def _save_all_settings(self) -> None:
        try:
            self.cfg.update(self._collect_settings())
            save_config(self.cfg)
            self.lbl_saved.configure(text="tersimpan ✓", text_color=OK)
            self.after(2500, lambda: self.lbl_saved.configure(text=""))
            self._log("ok", "settings disimpan")
            self._toast("Settings tersimpan", OK, 2400)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Gagal simpan: {exc}", BAD, 3400)

    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        try:
            if self.controller.running:
                self.controller.stop()
            self._save_all_settings_quiet()
        finally:
            self.destroy()


PremiumSniper = MCSniperApp


def main() -> int:
    try:
        app = MCSniperApp()
        app.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("fatal")
        try:
            messagebox.showerror("MC Sniper", f"Gagal menjalankan GUI:\n{exc}")
        except Exception:  # noqa: BLE001
            print(f"Fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
