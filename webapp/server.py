#!/usr/bin/env python3
"""
webapp/server.py — versi web Varin Sniper (stdlib, tanpa dependensi baru).

Arsitektur:
  * Satu ThreadingHTTPServer yang menyajikan UI statis + REST API.
  * Engine yang sama dengan aplikasi desktop dipakai ulang:
      - controller.SniperController  -> antrian, worker, watch mode, statistik
      - checker.Checker              -> pemeriksaan multi-source
      - scan_history.ScanHistory     -> riwayat SQLite
      - generator.generate_rare      -> generator kelangkaan
  * Komunikasi realtime memakai SSE (`GET /api/events`) yang membungkus
    queue event milik controller, jadi tidak ada polling berat dari browser.

Jalankan:
    python run_web.py                # http://localhost:3000
    python webapp/server.py --port 8080 --host 127.0.0.1
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ASSETS_DIR = os.path.join(ROOT, "assets")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    os.chdir(ROOT)          # file data (config.json, *.txt, scan_history.db) konsisten
except OSError:
    pass

from checker import Checker, CheckResult, NameStatus          # noqa: E402
from controller import SniperController                      # noqa: E402
from generator import (BLOCKED_NAMES, generate_pattern,      # noqa: E402
                       generate_random, generate_rare,
                       generate_smart_random)
import scan_history as sh                                    # noqa: E402
from ui import i18n                                          # noqa: E402
from utils import append_to_file, save_current_config         # noqa: E402
import claimer as clm                                        # noqa: E402
from webapp.discord_check import DiscordEngine               # noqa: E402
from checker import Checker, CheckResult, NameStatus as MinecraftNameStatus  # noqa: E402

WEB_BUILD = "4.5"
APP_PATH = "/app-v45/"    # URL baru: memaksa browser memuat dokumen & app.js baru

# Pengaturan sumber Discord. Token/API key TIDAK PERNAH dikirim ke browser,
# hanya status "sudah terisi / belum".
DG_SETTINGS_KEYS = ("dg_token", "dg_api_url", "dg_api_key")

# Pengaturan sumber Minecraft. Semua endpoint bebas proksi, tanpa token.
MC_SETTINGS_KEYS = ("mc_threads", "mc_timeout", "mc_stealth")
MCS_NAMES = ("minecraftservices", "mojang", "ashcon", "playerdb", "namemc", "mcchecker")
EXPORT_FILES = ("available.txt", "claimed.txt", "failed.txt", "discord_available.txt")
SETTINGS_KEYS = ("threads", "timeout", "watch_mode", "stealth_mode", "auto_claim",
                 "language", "gen_mode", "gen_consonants_only")
GEN_MODES = ("rarest", "balanced", "random")
MODE_ALIASES = {"legacy": "random"}  # config lama tetap jalan
STATUS_MAP = {
    NameStatus.AVAILABLE: sh.STATUS_AVAILABLE,
    NameStatus.TAKEN: sh.STATUS_TAKEN,
    NameStatus.RATE_LIMITED: sh.STATUS_RATE_LIMITED,
}
MCS_STATUS_MAP = {
    "AVAILABLE": "available",
    "TAKEN": "taken",
    "RATE_LIMITED": "rate_limited",
    "ERROR": "error",
    "UNKNOWN": "unknown",
}


def result_payload(result: CheckResult) -> Dict[str, Any]:
    return {
        "name": result.name,
        "status": result.status.value,
        "code": result.code,
        "reason": result.reason,
        "timestamp": result.timestamp,
    }


def split_names(raw: str) -> List[str]:
    """Pecah teks bebas menjadi daftar nama unik (koma/spasi/baris baru)."""
    names: List[str] = []
    seen = set()
    for token in (raw or "").replace(",", " ").replace(";", " ").split():
        name = token.strip().lower()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def count_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


# --------------------------------------------------------------------------- #
# Broadcast event controller -> semua klien SSE
# --------------------------------------------------------------------------- #
class EventHub:
    def __init__(self, engine: "WebEngine") -> None:
        self.engine = engine
        self._subs: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="EventHub", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=400)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _broadcast(self, event: str, data: Any) -> None:
        message = {"event": event, "data": data}
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(message)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except (queue.Empty, queue.Full):
                    pass

    def _run(self) -> None:
        last_stats = 0.0
        while True:
            try:
                kind, payload = self.engine.controller.events.get(timeout=0.2)
            except queue.Empty:
                kind, payload = None, None
            if kind:
                try:
                    self._broadcast(kind, self.engine.serialize(kind, payload))
                except Exception:  # noqa: BLE001
                    pass

            # Event mesin Discord memakai awalan `dg_` supaya frontend bisa
            # membedakannya dari engine Minecraft.
            while True:
                try:
                    dg_kind, dg_payload = self.engine.discord.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._broadcast(f"dg_{dg_kind}", dg_payload)
                except Exception:  # noqa: BLE001
                    break

            now = time.time()
            if now - last_stats >= 1.0:
                last_stats = now
                try:
                    self._broadcast("stats", self.engine.stats_snapshot())
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._broadcast("dg_state", self.engine.discord.state())
                except Exception:  # noqa: BLE001
                    pass


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class WebEngine:
    def __init__(self) -> None:
        self.controller = SniperController()
        self.config: Dict[str, Any] = self.controller.config
        i18n.set_language(self.config.get("language", "en"))
        self.discord = DiscordEngine(self.config)
        self.hub = EventHub(self)
        self.started_at = time.time()
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, tuple] = {}

    def start(self) -> None:
        self.hub.start()

    # -- util -------------------------------------------------------------- #
    def _cached(self, key: str, ttl: float, factory) -> Any:
        now = time.time()
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and now - entry[0] < ttl:
                return entry[1]
        value = factory()
        with self._cache_lock:
            self._cache[key] = (now, value)
        return value

    def stats_snapshot(self) -> Dict[str, Any]:
        return self.controller.stats.get_stats()

    def history_summary(self) -> Dict[str, Any]:
        counts = self.controller.scan_history.count_by_status()
        return {"total": sum(counts.values()), "by_status": counts}

    def public_config(self) -> Dict[str, Any]:
        return {key: self.config.get(key) for key in SETTINGS_KEYS}

    def state(self) -> Dict[str, Any]:
        accounts = self._cached("accounts", 8.0, lambda: len(clm.load_accounts()))
        proxies = self._cached("proxies", 8.0, lambda: count_lines("proxies.txt"))
        return {
            "running": bool(self.controller.running),
            "queue": {"size": self.controller.queue_size()},
            "stats": self.stats_snapshot(),
            "history": self.history_summary(),
            "config": self.public_config(),
            "accounts": accounts,
            "proxies": proxies,
            "version": WEB_BUILD,
            "build": WEB_BUILD,
            "server_uptime": round(time.time() - self.started_at, 1),
        }

    def serialize(self, kind: str, payload: Any) -> Any:
        try:
            if kind == "log":
                tag, text = payload
                return {"tag": tag, "text": text, "stamp": time.strftime("%H:%M:%S")}
            if kind == "result":
                return result_payload(payload)
            if kind == "status":
                state, threads = payload
                return {"state": state, "threads": threads}
            if kind == "claimed":
                name, account = payload
                return {"name": name, "account": account}
        except Exception:  # noqa: BLE001
            return str(payload)
        return payload if isinstance(payload, (dict, list, str, int, float, bool)) else str(payload)

    def known_names(self) -> set:
        """Nama yang sudah pernah dipindai (cache 3s untuk hindari query DB)."""
        return self._cached("known", 3.0,
                            lambda: set(self.controller.scan_history.distinct_names()))

    # -- queue ------------------------------------------------------------- #
    def add_names(self, raw: str) -> Dict[str, Any]:
        """Tambahkan daftar manual.

        force=True: nama yang sudah ada di riwayat tetap dicek ulang, karena
        pengguna menempel daftarnya secara eksplisit. Duplikat di antrian
        tetap dilewati, dan jumlahnya dilaporkan supaya tidak terkesan
        "hilang" begitu saja.
        """
        names = split_names(raw)
        known = self.known_names()
        already = sum(1 for n in names if n in known)
        added = self.controller.enqueue_many(names, force=True)
        sys.stderr.write(f"[web] queue/add requested={len(names)} added={added} "
                         f"known={already} queue={self.controller.queue_size()}\n")
        return {"requested": len(names), "added": added,
                "already_scanned": already,
                "skipped": max(0, len(names) - added),
                "queue": self.controller.queue_size()}

    def queue_snapshot(self) -> Dict[str, Any]:
        names = self.controller.queue_snapshot()
        return {"size": len(names), "names": names[:2000]}

    # -- engine lifecycle -------------------------------------------------- #
    def start_scan(self) -> Dict[str, Any]:
        self.controller.start()
        return {"running": True, "threads": int(self.config.get("threads", 15))}

    def stop_scan(self) -> Dict[str, Any]:
        self.controller.stop()
        return {"running": False}

    def check_one(self, name: str) -> Dict[str, Any]:
        name = (name or "").strip().lower()
        if not (3 <= len(name) <= 16) or not all(ch.isalnum() or ch == "_" for ch in name):
            return {"ok": False, "error": "invalid"}
        checker = Checker(timeout=float(self.config.get("timeout", 10.0)), max_retries=1)
        result = checker.check(name)
        source = result.reason.split(":")[0] if result.reason else ""
        self.controller.scan_history.record(
            name, STATUS_MAP.get(result.status, sh.STATUS_ERROR), source, result.reason or ""
        )
        if result.status == NameStatus.AVAILABLE:
            append_to_file("available.txt", name)
            self.controller.emit("available", name)
        self.controller.emit("result", result)
        return {"ok": True, "result": result_payload(result)}

    # -- generator --------------------------------------------------------- #
    def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Klien lama tidak mengirim length/mode -> dulu diam-diam jadi 3L.
        # Sekarang ditolak dengan pesan jelas supaya tidak menghasilkan
        # target yang salah tanpa disadari.
        if payload.get("length") is None or payload.get("mode") is None:
            raise ValueError(
                "UI lama: muat ulang halaman (Ctrl+F5) — reload the page, "
                "lalu pilih 3L/4L sebelum Generate")
        length = int(payload.get("length"))
        if length not in (3, 4):
            raise ValueError("length must be 3 or 4")
        count = max(1, min(int(payload.get("count", 500)), 5000))
        mode = str(payload.get("mode") or self.config.get("gen_mode", "rarest")).lower()
        mode = MODE_ALIASES.get(mode, mode)
        if mode not in GEN_MODES:
            mode = "rarest"
        consonants = bool(payload.get("consonants_only",
                                      self.config.get("gen_consonants_only", False)))
        known = self.known_names()
        underscore = mode == "balanced" and length == 3
        if mode == "random":
            # Random: a-z, 0-9 dan _ tanpa aturan pola -> ig9, hg_, x7z
            names = generate_random(count, length, exclude=known)
        else:
            names = generate_rare(count, length, allow_vowels=not consonants,
                                  band=0.45 if mode == "rarest" else 0.85,
                                  exclude=known, underscore=underscore)
        added = self.controller.enqueue_many(names) if payload.get("enqueue", True) else 0
        sys.stderr.write(
            f"[web] generate keys={sorted(payload)} "
            f"received_length={payload.get('length')!r} "
            f"received_mode={payload.get('mode')!r} -> length={length} mode={mode} "
            f"underscore={underscore} names={len(names)} added={added} "
            f"queue={self.controller.queue_size()}\n")
        self.config["gen_mode"] = mode
        self.config["gen_consonants_only"] = consonants
        save_current_config(self.config)
        return {"requested": count, "generated": len(names), "added": added,
                "sample": names[:14], "mode": mode, "length": length,
                "consonants_only": consonants, "underscore": underscore,
                "queue": self.controller.queue_size(),
                "received": {"length": payload.get("length"), "mode": payload.get("mode")}}

    def generate_from_pattern(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pattern = str(payload.get("pattern", "")).strip()
        if not pattern:
            raise ValueError("pattern required")
        count = max(1, min(int(payload.get("count", 500)), 5000))
        names = generate_pattern([pattern], count, exclude=self.known_names())
        added = self.controller.enqueue_many(names)
        return {"requested": count, "generated": len(names), "added": added,
                "sample": names[:14], "pattern": pattern}

    # -- history ----------------------------------------------------------- #
    def history(self, status: str = "", query: str = "", limit: int = 250) -> Dict[str, Any]:
        store = self.controller.scan_history
        limit = max(1, min(int(limit or 250), 1000))
        if query:
            rows = store.search(query, limit=limit)
        elif status:
            rows = store.list_by_status(status, limit=limit)
        else:
            rows = store.list_all(limit=limit)
        return {"rows": rows, "total": store.count()}

    def delete_history(self, name: str) -> Dict[str, Any]:
        removed = self.controller.scan_history.delete(name)
        return {"removed": removed, "total": self.controller.scan_history.count()}

    def clear_history(self) -> Dict[str, Any]:
        removed = self.controller.scan_history.clear()
        return {"removed": removed}

    def rescan_failed(self) -> Dict[str, Any]:
        names = self.controller.scan_history.names_needing_rescan()
        added = self.controller.enqueue_many(names)
        return {"found": len(names), "added": added}

    # -- settings ---------------------------------------------------------- #
    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        threads_before = int(self.config.get("threads", 15))
        if "threads" in payload:
            self.config["threads"] = max(1, min(int(payload["threads"]), 100))
        if "timeout" in payload:
            self.config["timeout"] = max(1.0, min(float(payload["timeout"]), 60.0))
        for key in ("watch_mode", "stealth_mode", "auto_claim"):
            if key in payload:
                self.config[key] = bool(payload[key])
        if payload.get("language") in i18n.LANGUAGES:
            self.config["language"] = payload["language"]
            i18n.set_language(payload["language"])
        req_mode = str(payload.get("gen_mode", "")).lower()
        req_mode = MODE_ALIASES.get(req_mode, req_mode)
        if req_mode in GEN_MODES:
            self.config["gen_mode"] = req_mode
        if "gen_consonants_only" in payload:
            self.config["gen_consonants_only"] = bool(payload["gen_consonants_only"])
        save_current_config(self.config)
        changed_threads = int(self.config.get("threads", 15)) != threads_before
        return {
            "config": self.public_config(),
            "restart_required": bool(self.controller.running and changed_threads),
        }

    def update_discord_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simpan sumber Discord. Token & API key tidak pernah ikut di-respons."""
        for key in DG_SETTINGS_KEYS:
            if key in payload:
                self.config[key] = str(payload.get(key) or "").strip()
        if "pace" in payload:
            try:
                pace = max(0.3, min(float(payload["pace"]), 10.0))
            except (TypeError, ValueError):
                pace = None
            if pace is not None:
                self.config["dg_pace"] = pace
                self.discord.checker.direct.min_interval = pace
                self.discord.checker.direct.pacer.interval = pace
        save_current_config(self.config)
        self.discord.checker.reload()
        return {"settings": self.discord.state()["settings"]}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def safe_join(base: str, relative: str) -> Optional[str]:
    relative = unquote(relative).lstrip("/")
    if not relative or ".." in relative.split("/"):
        return None
    target = os.path.normpath(os.path.join(base, relative))
    try:
        if os.path.commonpath([os.path.abspath(base), os.path.abspath(target)]) != os.path.abspath(base):
            return None
    except ValueError:
        return None
    return target if os.path.isfile(target) else None


class Handler(BaseHTTPRequestHandler):
    server_version = "VarinSniperWeb/4.0"
    protocol_version = "HTTP/1.0"

    # -- helpers ----------------------------------------------------------- #
    @property
    def engine(self) -> WebEngine:
        return self.server.engine  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        stamp = time.strftime("%H:%M:%S")
        sys.stderr.write(f"[{stamp}] [web] %s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def read_json(self) -> Dict[str, Any]:
        raw = self.read_body()
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8") or "{}")
        return data if isinstance(data, dict) else {}

    def read_body(self) -> bytes:
        """Baca body request, termasuk `Transfer-Encoding: chunked`.

        Proxy preview (dan beberapa reverse proxy) mengirim POST tanpa
        Content-Length memakai chunked. Tanpa decoder ini `rfile.read(0)`
        mengembalikan kosong, sehingga payload JSON hilang di jalan dan
        server jatuh ke default (3L/Rarest) — persis bug yang dilaporkan.
        """
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            raw = self.read_chunked()
        else:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > 2 * 1024 * 1024:
                raise ValueError("payload too large")
            raw = self.rfile.read(length) if length > 0 else b""

        path = self.path.split("?")[0]
        if not raw and path == "/api/generate":
            sys.stderr.write(
                f"[web] generate EMPTY body te={te!r} "
                f"cl={self.headers.get('Content-Length')!r}\n")
        return raw

    def read_chunked(self) -> bytes:
        chunks: List[bytes] = []
        total = 0
        while True:
            line = self.rfile.readline(65536)
            if not line:
                break
            token = line.strip().split(b";")[0]
            if not token:
                break
            try:
                size = int(token, 16)
            except ValueError:
                raise ValueError("bad chunk size")
            if size == 0:
                while True:  # buang trailer
                    trailer = self.rfile.readline(65536)
                    if trailer in (b"\r\n", b"\n", b""):
                        break
                break
            total += size
            if total > 2 * 1024 * 1024:
                raise ValueError("payload too large")
            chunks.append(self.rfile.read(size))
            self.rfile.read(2)  # CRLF setelah setiap chunk
        return b"".join(chunks)

    def serve_file(self, base: str, relative: str, download: bool = False) -> None:
        target = safe_join(base, relative)
        if not target:
            self.send_error_json("not found", 404)
            return
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        try:
            with open(target, "rb") as handle:
                data = handle.read()
        except OSError:
            self.send_error_json("not found", 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # no-store: perubahan UI langsung terlihat, tidak tertahan cache browser
        self.send_header("Cache-Control", "no-cache" if download else "no-store")
        if download:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(target)}"')
        self.end_headers()
        self.wfile.write(data)

    # -- GET --------------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        params = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                # Halaman lama yang masih terbuka tidak akan pernah memakai
                # app.js baru tanpa navigasi. Redirect ke URL baru memaksa
                # dokumen benar-benar dimuat ulang (bukan dari cache).
                self.send_response(302)
                self.send_header("Location", APP_PATH)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif path in (APP_PATH, APP_PATH.rstrip("/")):
                self.serve_file(STATIC_DIR, "index.html")
            elif path.startswith("/static/"):
                self.serve_file(STATIC_DIR, path[len("/static/"):])
            elif path.startswith("/assets/"):
                self.serve_file(ASSETS_DIR, path[len("/assets/"):])
            elif path == "/api/state":
                self.send_json(self.engine.state())
            elif path == "/api/queue":
                self.send_json(self.engine.queue_snapshot())
            elif path == "/api/settings":
                self.send_json({"config": self.engine.public_config()})
            elif path == "/api/history":
                self.send_json(self.engine.history(
                    status=(params.get("status") or [""])[0],
                    query=(params.get("q") or [""])[0],
                    limit=int((params.get("limit") or ["250"])[0] or 250),
                ))
            elif path == "/api/export":
                name = (params.get("file") or [""])[0]
                if name not in EXPORT_FILES:
                    self.send_error_json("file not allowed", 400)
                else:
                    self.serve_file(ROOT, name, download=True)
            elif path == "/api/mc/state":
                # Return Minecraft checker status
                checker = Checker(timeout=float(self.config.get("mc_timeout", 10.0)))
                # Quick test on a common name to check if sources are healthy
                test_name = "minecraft"
                test_result = checker.check(test_name)
                sources_status = {s.name: s.healthy() for s in checker.sources}
                self.send_json({
                    "running": bool(self.controller.running),
                    "mc_sources": sources_status,
                    "test_name": test_name,
                    "test_status": test_result.status.value,
                    "test_reason": test_result.reason,
                })
            elif path == "/api/dg/state":
                self.send_json(self.engine.discord.state())
            elif path == "/api/events":
                self.serve_events()
            else:
                self.send_error_json("not found", 404)
        except json.JSONDecodeError:
            self.send_error_json("invalid json", 400)
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(f"server error: {exc}", 500)

    # -- POST -------------------------------------------------------------- #
    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            payload = self.read_json()
            if path == "/api/queue/add":
                raw = payload.get("text")
                if raw is None:
                    names = payload.get("names") or []
                    raw = " ".join(str(n) for n in names)
                self.send_json({"ok": True, **self.engine.add_names(str(raw))})
            elif path == "/api/queue/clear":
                cleared = self.engine.controller.clear_queue()
                self.send_json({"ok": True, "cleared": cleared})
            elif path == "/api/queue/remove":
                name = str(payload.get("name", "")).strip().lower()
                self.engine.controller.remove_from_queue(name)
                self.send_json({"ok": True})
            elif path == "/api/scan/start":
                self.send_json({"ok": True, **self.engine.start_scan()})
            elif path == "/api/scan/stop":
                self.send_json({"ok": True, **self.engine.stop_scan()})
            elif path == "/api/check":
                self.send_json(self.engine.check_one(str(payload.get("name", ""))))
            elif path == "/api/mc/check":
                name = str(payload.get("name", "")).strip().lower()
                if not (3 <= len(name) <= 16) or not all(ch.isalnum() or ch == "_" for ch in name):
                    return self.send_error_json("invalid name", 400)
                checker = Checker(timeout=float(self.config.get("mc_timeout", 10.0)), max_retries=2)
                result = checker.check(name)
                source = result.reason.split(":")[0] if result.reason else ""
                self.controller.scan_history.record(
                    name, MCS_STATUS_MAP.get(result.status.value, "unknown"), source, result.reason or ""
                )
                if result.status.value == "available":
                    append_to_file("available.txt", name)
                self.controller.emit("result", result_payload(result))
                self.send_json({"ok": True, "result": result_payload(result)})
            elif path == "/api/generate":
                self.send_json({"ok": True, **self.engine.generate(payload)})
            elif path == "/api/generate/pattern":
                self.send_json({"ok": True, **self.engine.generate_from_pattern(payload)})
            elif path == "/api/settings":
                self.send_json({"ok": True, **self.engine.update_settings(payload)})
            elif path == "/api/history/delete":
                self.send_json({"ok": True,
                                **self.engine.delete_history(str(payload.get("name", "")))})
            elif path == "/api/history/clear":
                self.send_json({"ok": True, **self.engine.clear_history()})
            elif path == "/api/history/rescan":
                self.send_json({"ok": True, **self.engine.rescan_failed()})
            # -- Discord checker/generator (3L/4L, rare only) ---------------- #
            elif path == "/api/dg/generate":
                self.send_json({"ok": True, **self.engine.discord.generate(payload)})
            elif path == "/api/dg/queue/add":
                raw = payload.get("text")
                if raw is None:
                    names = payload.get("names") or []
                    raw = " ".join(str(n) for n in names)
                self.send_json({"ok": True,
                                **self.engine.discord.add(split_names(str(raw)))})
            elif path == "/api/dg/queue/clear":
                self.send_json({"ok": True, "cleared": self.engine.discord.clear()})
            elif path == "/api/dg/start":
                self.send_json({"ok": True, **self.engine.discord.start()})
            elif path == "/api/dg/stop":
                self.send_json({"ok": True, **self.engine.discord.stop()})
            elif path == "/api/dg/check":
                self.send_json(self.engine.discord.check_one(
                    str(payload.get("name", "")), force=bool(payload.get("force"))))
            elif path == "/api/dg/settings":
                self.send_json({"ok": True,
                                **self.engine.update_discord_settings(payload)})
            else:
                self.send_error_json("not found", 404)
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except json.JSONDecodeError:
            self.send_error_json("invalid json", 400)
        except Exception as exc:  # noqa: BLE001
            self.send_error_json(f"server error: {exc}", 500)

    # -- SSE --------------------------------------------------------------- #
    def serve_events(self) -> None:
        q = self.engine.hub.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            self.write_event("hello", self.engine.state())
            while True:
                try:
                    message = q.get(timeout=15.0)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.write_event(message["event"], message["data"])
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.engine.hub.unsubscribe(q)

    def write_event(self, event: str, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str)
        self.wfile.write(f"event: {event}\ndata: {body}\n\n".encode("utf-8"))
        self.wfile.flush()


class SniperHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(host: str = "0.0.0.0", port: int = 3000) -> SniperHTTPServer:
    # Segarkan daftar 3name.xyz/list di background supaya web & desktop
    # memakai daftar blokir yang sama dan selalu up to date.
    try:
        from blocklist import start_refresh
        start_refresh()
    except Exception:  # noqa: BLE001
        sys.stderr.write("[web] blocklist refresh tidak tersedia\n")
    engine = WebEngine()
    engine.start()
    httpd = SniperHTTPServer((host, port), Handler)
    httpd.engine = engine  # type: ignore[attr-defined]
    return httpd


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Varin Sniper — web version")
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=3000, help="port (default 3000)")
    parser.add_argument("--open", action="store_true", help="buka browser setelah start")
    args = parser.parse_args(argv)

    httpd = build_server(args.host, args.port)
    url = f"http://localhost:{args.port}"
    print(f"[web] Varin Sniper web di {url} (bind {args.host}:{args.port})")
    print("[web] tekan Ctrl+C untuk berhenti")
    if args.open:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] dihentikan")
    finally:
        try:
            httpd.engine.controller.stop()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        try:
            httpd.engine.discord.stop()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
