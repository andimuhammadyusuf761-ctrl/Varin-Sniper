#!/usr/bin/env python3
"""
Varin Sniper — 3L/4L Minecraft Username Sniper (Premium GUI)

Tabs: Checker | Sniper | Accounts | Proxies | Settings | History | Stats

Aturan pemisahan:
  * SniperController  -> mesin (antrian, worker thread, claim, statistik)
  * ScanHistory       -> SQLite riwayat pemindaian (tidak bisa diubah ulang)
  * LogView / ListPane / StatChip / Card -> komponen GUI yang bisa dipakai ulang
  * VarinSniperApp    -> layout, navigasi, dan reaksi terhadap event controller

Semua update GUI dari thread lain dilewatkan queue `controller.events`
dan dipompa oleh `.after()` di thread utama, jadi GUI tetap responsif.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


def ensure_dependencies() -> None:
    """Install package requirements when the GUI dependency is missing."""
    try:
        import customtkinter  # noqa: F401
        return
    except ModuleNotFoundError:
        repo_root = os.path.dirname(os.path.abspath(__file__))
        requirements_path = os.path.join(repo_root, "requirements.txt")
        print("[Varin Sniper] Missing dependency 'customtkinter'. Installing requirements...", file=sys.stderr)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
            import customtkinter  # noqa: F401
            return
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Missing dependency 'customtkinter'. Install it with:\n"
                f"  {sys.executable} -m pip install -r \"{requirements_path}\"\n"
                f"Original error: {exc}"
            ) from exc


ensure_dependencies()

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
from scan_history import ScanHistory, STATUS_AVAILABLE, STATUS_TAKEN, STATUS_ERROR, STATUS_UNKNOWN, STATUS_RATE_LIMITED, STATUS_CLAIMED

logger = logging.getLogger("VarinSniper.GUI")
