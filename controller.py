"""
controller.py — mesin Varin Sniper (logika saja, tanpa satu pun widget).

Semua komunikasi ke GUI lewat `controller.events` (queue) sehingga GUI tetap
responsif dan mesin bisa diuji tanpa display. Teks log memakai kunci i18n
supaya ikut berubah saat bahasa diganti.

Event yang dikirim:
  ("log",       (tag, text))
  ("status",    ("running", threads) | ("stopped", None))
  ("result",    CheckResult)
  ("available", name)
  ("claimed",   (name, account_label))
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from checker import BulkLookup, Checker, CheckResult, NameStatus
from proxy import Proxy, ProxyManager
import claimer as clm
from scan_history import (
    ScanHistory, STATUS_AVAILABLE, STATUS_TAKEN, STATUS_ERROR, STATUS_RATE_LIMITED,
)
from ui.i18n import t as T
from utils import append_to_file, load_config, send_discord_webhook, StatsTracker

logger = logging.getLogger("VarinSniper.Engine")

AVAILABLE_FILE = "available.txt"
CLAIMED_FILE = "claimed.txt"
FAILED_FILE = "failed.txt"
HISTORY_FILE = "claim_history.json"


def now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


class DiscordNotifier:
    """Notifikasi webhook Discord (opsional, tidak pernah memblokir worker)."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def notify_available(self, name: str) -> None:
        self._send(T("checker.avail_title"), f"**{name}** is available to claim!",
                   0x00FF9F, "notify_on_available")

    def notify_claimed(self, name: str, account: str) -> None:
        self._send(T("checker.claimed_title"), f"**{name}** claimed via `{account}`",
                   0x00F0FF, "notify_on_claimed")

    def _send(self, title: str, desc: str, color: int, flag: str) -> None:
        if not self.config.get("use_discord_webhook") or not self.config.get(flag):
            return
        url = self.config.get("discord_webhook_url", "")
        if not url:
            return
        threading.Thread(target=send_discord_webhook, args=(url, title, desc, color),
                         daemon=True).start()


class SniperController:
    """Mesin sniper: antrian, worker thread, claim, dan statistik."""

    def __init__(self) -> None:
        self.events: "queue.Queue[Any]" = queue.Queue()
        self.config = load_config()
        self.stop_event = threading.Event()
        self.names_queue: "queue.Queue[str]" = queue.Queue()
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
        self.scan_history = ScanHistory()
        self.bulk: Optional[BulkLookup] = None

    # -- persistence ------------------------------------------------------- #
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

    # -- events ------------------------------------------------------------ #
    def emit(self, kind: str, payload: Any = None) -> None:
        try:
            self.events.put((kind, payload), timeout=1)
        except Exception:  # noqa: BLE001
            pass

    # -- queue ------------------------------------------------------------- #
    def enqueue(self, name: str, force: bool = False) -> bool:
        """Masukkan nama ke antrian.

        force=True dipakai saat pengguna menempel daftar secara manual:
        nama yang sudah ada di riwayat tetap dicek ulang (status bisa berubah
        setelah akun rename), sedangkan duplikat di antrian tetap dilewati.
        """
        name = (name or "").strip().lower()
        if not (3 <= len(name) <= 16):
            return False
        if not all(ch.isalnum() or ch == "_" for ch in name):
            return False
        if not force:
            existing = self.scan_history.get_status(name)
            if existing and existing.get("status") in (STATUS_AVAILABLE, STATUS_TAKEN):
                return False
        with self._lock:
            if name in self.pending:
                return False
            if not force and name in self.taken:
                return False
            self.pending.add(name)
        self.names_queue.put(name)
        return True

    def enqueue_many(self, names: List[str], force: bool = False) -> int:
        added = 0
        for name in names:
            if self.enqueue(name, force=force):
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
        self.emit("log", ("info", T("log.queue_cleared", n=cleared)))
        return cleared

    def remove_from_queue(self, name: str) -> None:
        with self._lock:
            self.pending.discard(name)

    # -- lifecycle --------------------------------------------------------- #
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

        # Jalur cepat: 10 nama per request resmi. Kalau endpoint membatasi,
        # worker otomatis kembali ke pemeriksaan per-nama yang ketat.
        self.bulk = BulkLookup(timeout=float(self.config.get("timeout", 10.0)))

        self.workers = []
        for idx in range(n_threads):
            worker = threading.Thread(
                target=self._worker, args=(Checker(**checker_kwargs),),
                name=f"Checker-{idx}", daemon=True,
            )
            worker.start()
            self.workers.append(worker)

        if self.config.get("watch_mode", True) and not (
                self.watch_thread and self.watch_thread.is_alive()):
            self.watch_thread = threading.Thread(target=self._watch_loop, name="Watcher", daemon=True)
            self.watch_thread.start()

        self.emit("status", ("running", n_threads))
        self.emit("log", ("ok", T("log.engine_start", threads=n_threads)))

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.emit("status", ("stopped", None))
        self.emit("log", ("warn", T("log.engine_stopping")))
        for worker in self.workers:
            worker.join(timeout=1.5)
        self.workers = []

    # -- worker ------------------------------------------------------------ #
    def _take_batch(self, size: int, timeout: float) -> List[str]:
        """Ambil satu nama (menunggu), lalu sedot sisanya yang sudah antri."""
        try:
            batch = [self.names_queue.get(timeout=timeout)]
        except queue.Empty:
            return []
        while len(batch) < size:
            try:
                batch.append(self.names_queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _worker(self, checker: Checker) -> None:
        """Worker: satu request bulk menyelesaikan sampai 10 nama.

        Kalau bulk tidak tersedia (429/error), batch yang sama diproses
        per-nama lewat `checker.check()` yang ketat — tidak ada tebakan.
        """
        batch_size = self.bulk.batch_size if self.bulk else 1
        while not self.stop_event.is_set():
            batch = self._take_batch(batch_size, 0.3)
            if not batch:
                if not self.running:
                    break
                continue

            try:
                taken: set = set()
                resolved = False
                if self.bulk is not None:
                    taken, resolved = self.bulk.lookup(batch)

                for name in batch:
                    try:
                        if resolved:
                            if name in taken:
                                result = CheckResult(name, NameStatus.TAKEN, 200,
                                                     "bulk: profile ada")
                            else:
                                result = CheckResult(name, NameStatus.AVAILABLE, 200,
                                                     "bulk: tidak terdaftar")
                        else:
                            result = checker.check(name)
                        self._process_result(name, result)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("worker error")
                        self.stats.increment("total")
                        self.stats.increment("errors")
                        self.emit("log", ("bad", T("log.worker_error", name=name, error=exc)))
                        self._release(name)
            finally:
                for _name in batch:
                    self.names_queue.task_done()

    def _release(self, name: str) -> None:
        """Nama selesai diproses: selalu keluar dari antrian.

        Dulu AVAILABLE/ERROR tidak pernah di-discard, sehingga jumlah antrian
        membengkak dan nama itu tidak bisa dicek ulang. Sekarang semua jalur
        (available, taken, error) melepas nama dari `pending`.
        """
        with self._lock:
            self.pending.discard(name)

    def _process_result(self, name: str, result: CheckResult) -> None:
        try:
            self.stats.increment("total")
            status_map = {
                NameStatus.AVAILABLE: STATUS_AVAILABLE,
                NameStatus.TAKEN: STATUS_TAKEN,
                NameStatus.RATE_LIMITED: STATUS_RATE_LIMITED,
            }
            scan_status = status_map.get(result.status, STATUS_ERROR)
            self.scan_history.record(
                name, scan_status,
                result.reason.split(":")[0] if result.reason else "",
                result.reason or "",
            )

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
            else:
                self.stats.increment("errors")
                self.emit("log", ("warn", f"{name}: {result.reason or 'error'}"))

            self.emit("result", result)
        finally:
            self._release(name)

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
                self.emit("log", ("info", T("log.watch_recheck", n=added)))

    # -- claim ------------------------------------------------------------- #
    def try_claim(self, name: str) -> None:
        threading.Thread(target=self._do_claim, args=(name,), daemon=True).start()

    def _do_claim(self, name: str) -> None:
        try:
            if not self.accounts:
                self.emit("log", ("warn", T("log.claim_no_account", name=name)))
                return

            smart = clm.SmartClaimQueue(self.accounts)
            max_attempts = int(self.config.get("claim_max_accounts", 0)) or len(self.accounts)
            attempts = 0

            while attempts < max_attempts and not self.stop_event.is_set():
                acc = smart.get_next_account()
                if not acc:
                    break
                attempts += 1
                self.emit("log", ("info", T("log.claim_via", name=name, account=acc.label(),
                                            index=attempts, total=max_attempts)))

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
                    self.scan_history.mark_claimed(name)
                    self.emit("claimed", (name, acc.label()))
                    self.notifier.notify_claimed(name, acc.label())
                    if self.config.get("sound_notifications", False):
                        threading.Thread(target=self._play_sound, daemon=True).start()
                    return

                if result.status == clm.ClaimStatus.NAME_TAKEN:
                    append_to_file(FAILED_FILE, f"{name} | taken | {result.message} | {now_hms()}")
                    self.remove_from_queue(name)
                    self.emit("log", ("taken", T("log.claim_generic_fail", name=name,
                                                 account=acc.label(), message=result.message)))
                    return

                if result.status == clm.ClaimStatus.RATE_LIMITED:
                    time.sleep(3)
                    continue

                if result.status in (clm.ClaimStatus.NOT_ELIGIBLE, clm.ClaimStatus.COOLDOWN):
                    append_to_file(FAILED_FILE,
                                   f"{name} | not_eligible | {result.message} | {now_hms()}")
                    self.emit("log", ("warn", T("log.claim_not_eligible", name=name,
                                                account=acc.label(), message=result.message)))
                    continue

                append_to_file(FAILED_FILE,
                               f"{name} | {result.status.value} | {result.message} | {now_hms()}")
                self.emit("log", ("warn", T("log.claim_generic_fail", name=name,
                                            account=acc.label(), message=result.message)))

            self.emit("log", ("bad", T("log.claim_failed", name=name, n=attempts)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("claim error")
            self.emit("log", ("bad", T("log.claim_exception", name=name, error=exc)))

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
