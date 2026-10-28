"""discord_check.py — checker username Discord multi-sumber (3L/4L, rare only)."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests

from blocklist import is_inappropriate
from checker import _Pacer
from generator import generate_rare
from scan_history import (
    ScanHistory, STATUS_AVAILABLE, STATUS_ERROR, STATUS_RATE_LIMITED, STATUS_TAKEN,
)

# --------------------------------------------------------------------------- #
# Aturan username Discord (3L / 4L)
# --------------------------------------------------------------------------- #

DISCORD_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789._"
MIN_LEN, MAX_LEN = 2, 32           # aturan asli Discord (untuk jalur cek)
GEN_MIN, GEN_MAX = 3, 4            # cakupan generator: hanya 3L dan 4L

UNAUTH_URL = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
POMELO_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"
UNAUTH_URL_V10 = "https://discord.com/api/v10/unique-username/username-attempt-unauthed"
POMELO_URL_V10 = "https://discord.com/api/v10/users/@me/pomelo-attempt"
USERNAME_ATTEMPT = "https://discord.com/api/v9/unique-username/username-attempt"

BROWSER_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Origin": "https://discord.com",
    "Referer": "https://discord.com/register",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Multiple API sources to avoid rate limits - add from web services
DISCORD_API_URLS = (
    "https://api.discord.gg/v1/username/check",
    "https://discord-api.com/v1/username/available",
    "https://discord-names.com/api/check",
    "https://discord-names-api.vercel.app/api/check",
    "https://namechk.com/api/check/discord/{username}",
    "https://api.namebeta.com/check/discord?username={username}",
    "https://checkmyname.com/api/discord/{username}",
    "https://discordchecker.com/api/check?username={username}",
    "https://usernameapi.net/api/discord/{username}",
    "https://instantusername.com/api/check/discord/{username}",
    "https://api.isusernameavailable.com/discord/{username}",
    "https://namemc.com/search?q={username}&type=discord",
    "https://discordid.net/api/username/check/{username}",
    "https://api.dicord.tools/v1/username/check?username={username}",
    "https://checkdiscord.com/api/username/{username}",
    "https://api.usernames.app/discord/check/{username}",
    "https://username-checker.com/api/discord/{username}",
    "https://api.gamertagchecker.com/discord?username={username}",
    "https://sniperbot.com/api/discord/check/{username}",
    "https://rareusername.net/api/check/discord/{username}",
)

# Kata yang diblokir Discord sendiri (terverifikasi: "discord" -> 400
# USERNAME_INVALID_CONTAINS). Dicek per bagian, jadi "discord.bot" ikut kena.
RESERVED = frozenset({
    "discord", "discordapp", "nitro", "admin", "administrator", "support",
    "system", "api", "app", "apps", "cli", "status", "home", "download",
    "blog", "careers", "safety", "terms", "privacy", "legal",
    "developer", "developers", "clyde", "wumpus", "mfa", "stage",
    "gift", "store",
})


def validate(name: str) -> Tuple[bool, str]:
    """Validasi lokal username Discord (2-32 karakter). Return (ok, kode_alasan).

    Panjang 3/4 hanya berlaku untuk GENERATOR; jalur cek menerima nama
    berapa pun selama aturan Discord terpenuhi.
    """
    name = (name or "").strip().lower()
    if not (MIN_LEN <= len(name) <= MAX_LEN):
        return False, "USERNAME_INVALID_LENGTH"
    if any(ch not in DISCORD_CHARS for ch in name):
        return False, "USERNAME_INVALID_CHAR"
    if not name.strip("."):
        return False, "USERNAME_INVALID_ONLY_PERIODS"
    if name.startswith(".") or name.endswith("."):
        return False, "USERNAME_INVALID_EDGE_PERIOD"
    if ".." in name:
        return False, "USERNAME_INVALID_CONSECUTIVE_PERIOD"
    for part in name.replace("_", ".").split("."):
        if part in RESERVED:
            return False, "USERNAME_INVALID_CONTAINS"
    return True, ""


# --------------------------------------------------------------------------- #
# _error_code and _interpret
# --------------------------------------------------------------------------- #


def _error_code(data: dict) -> str:
    """Ambil kode error dari respons 400 Discord."""
    try:
        return str(data["errors"]["username"][("_errors")][0]["code"])
    except (KeyError, IndexError, TypeError):
        return ""


def _interpret(status: int, data: Optional[dict]) -> Tuple[str, str]:
    """Terjemahkan respons Discord menjadi verdict ketat."""
    if status == 0:
        return "UNKNOWN", "jaringan error"
    if status == 429:
        return "BLOCKED", "429 rate limited"
    if status == 200:
        taken = data.get("taken") if isinstance(data, dict) else None
        if isinstance(taken, bool):
            return ("TAKEN" if taken else "AVAILABLE"), f"200 taken={taken}"
        return "UNKNOWN", "200 tanpa field taken"
    if status == 400:
        code = _error_code(data or {})
        if code:
            return "INVALID", code
        return "UNKNOWN", "400 tanpa kode error"
    if status in (401, 403):
        return "BLOCKED", f"{status} auth/blokir"
    if status >= 500:
        return "BLOCKED", f"{status} server error"
    return "UNKNOWN", f"http {status}"


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #

class Result:
    """Satu hasil pemeriksaan username Discord."""

    __slots__ = ("name", "status", "code", "reason", "source", "cached", "timestamp")

    def __init__(self, name: str, status: str, code: int = 0, reason: str = "",
                 source: str = "", cached: bool = False):
        self.name = name
        self.status = status            # AVAILABLE | TAKEN | INVALID | RATE_LIMITED | UNKNOWN
        self.code = code
        self.reason = reason
        self.source = source
        self.cached = cached
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "code": self.code,
            "reason": self.reason, "source": self.source, "cached": self.cached,
            "stamp": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
        }

    def __repr__(self) -> str:      # pragma: no cover - debugging
        return f"<DiscordResult {self.name} {self.status}>"


# --------------------------------------------------------------------------- #
# Source
# --------------------------------------------------------------------------- #

class Source:
    """Satu sumber kebenaran dengan bucket rate limit sendiri."""

    name = "base"
    label = ""
    min_interval = 1.0
    default_cooldown = 60.0

    def __init__(self, timeout: float = 10.0):
        self.timeout = float(timeout)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.pacer = _Pacer(self.min_interval)
        self.cooldown_until = 0.0
        self.last_error = ""
        self.last_verdict = ""
        self.requests = 0
        self.limited = 0
        self.errors = 0
        self._lock = threading.Lock()

    # -- infra ------------------------------------------------------------ #

    def healthy(self) -> bool:
        return time.time() >= self.cooldown_until

    def cooldown_for(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    def cooldown(self, seconds: Optional[float] = None, retry_after=None) -> float:
        dur = seconds if seconds is not None else self.default_cooldown
        if retry_after is not None:
            try:
                dur = max(dur, float(retry_after))
            except (TypeError, ValueError):
                pass
        dur = min(max(dur, 1.0), 3600.0)
        with self._lock:
            self.cooldown_until = time.time() + dur
        return dur

    def _tally(self, field: str) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    # -- antarmuka --------------------------------------------------------- #

    def post(self, url: str, payload: Dict[str, Any], headers: Optional[dict] = None,
             proxies: Optional[dict] = None) -> Tuple[int, Optional[dict], Optional[str]]:
        """POST JSON. 429 langsung memicu cooldown sumber ini."""
        self.pacer.wait()
        self._tally("requests")
        try:
            resp = self.session.post(url, json=payload,
                                     headers=headers or BROWSER_HEADERS,
                                     timeout=self.timeout, proxies=proxies)
        except requests.exceptions.RequestException as exc:
            self.last_error = str(exc)[:90]
            self._tally("errors")
            return 0, None, None
        retry_after = resp.headers.get("Retry-After") if resp.status_code == 429 else None
        if resp.status_code == 429:
            self._tally("limited")
            self.cooldown(retry_after=retry_after)
        data: Optional[dict] = None
        try:
            parsed = resp.json()
            data = parsed if isinstance(parsed, dict) else None
        except ValueError:
            data = None
        return resp.status_code, data, retry_after

    # -- antarmuka --------------------------------------------------------- #

    @property
    def enabled(self) -> bool:
        return True

    def check(self, name: str) -> Tuple[str, str]:
        """Return (verdict, detail). verdict: TAKEN/AVAILABLE/INVALID/BLOCKED/UNKNOWN."""
        raise NotImplementedError

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name, "label": self.label, "enabled": self.enabled,
                "healthy": self.healthy(), "cooldown": round(self.cooldown_for(), 1),
                "requests": self.requests, "limited": self.limited,
                "errors": self.errors, "last_error": self.last_error,
                "last_verdict": self.last_verdict,
                "min_interval": self.min_interval,
            }


# --------------------------------------------------------------------------- #
# Source implementations
# --------------------------------------------------------------------------- #

class DirectSource(Source):
    """Endpoint resmi tanpa token — sumber utama, pacing konservatif."""

    name = "direct"
    label = "Discord resmi (tanpa token)"
    min_interval = 0.15
    default_cooldown = 30.0

    def __init__(self, timeout: float = 10.0):
        super().__init__(timeout)
        self.endpoints = [UNAUTH_URL, UNAUTH_URL_V10, USERNAME_ATTEMPT]
        self._idx = 0

    def check(self, name: str) -> Tuple[str, str]:
        last = ("UNKNOWN", "")
        for i in range(len(self.endpoints)):
            url = self.endpoints[self._idx % len(self.endpoints)]
            self._idx += 1
            status, data, _ = self.post(url, {"username": name})
            verdict, detail = _interpret(status, data)
            if verdict not in ("UNKNOWN",):
                self.last_verdict = verdict
                return verdict, detail
            last = (verdict, detail)
        self.last_verdict = last[0]
        return last


class TokenSource(Source):
    """Endpoint resmi DENGAN token akun — bucket rate limit yang berbeda."""

    name = "token"
    label = "Discord resmi (token akun)"
    min_interval = 0.1
    default_cooldown = 30.0

    def __init__(self, token: str = "", timeout: float = 10.0):
        super().__init__(timeout)
        self.token = (token or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def check(self, name: str) -> Tuple[str, str]:
        if not self.enabled:
            return "UNKNOWN", "token belum diisi"
        headers = {**BROWSER_HEADERS, "Authorization": self.token}
        status, data, _ = self.post(POMELO_URL, {"username": name}, headers=headers)
        if status == 401:
            self.cooldown(300.0)
            self.last_error = "token ditolak Discord"
            return "BLOCKED", "401 token tidak valid"
        verdict, detail = _interpret(status, data)
        self.last_verdict = verdict
        return verdict, detail


class ProxySource(Source):
    """Endpoint resmi lewat rotasi proxy — tiap IP punya limit sendiri."""

    name = "proxy"
    label = "Discord resmi (rotasi proxy)"
    min_interval = 0.1
    default_cooldown = 20.0

    def __init__(self, proxy_file: str = "proxies.txt", timeout: float = 10.0):
        super().__init__(timeout)
        self.proxies: List[Any] = []
        self.proxy_file = proxy_file
        self.reload()

    def reload(self) -> int:
        try:
            from proxy import load_from_file
            self.proxies = [p for p in load_from_file(self.proxy_file) if getattr(p, "host", None)]
        except Exception:
            self.proxies = []
        return len(self.proxies)

    @property
    def enabled(self) -> bool:
        return bool(self.proxies)

    def _next_proxy(self) -> Optional[dict]:
        if not self.proxies:
            return None
        proxy = self.proxies[int(time.time() * 1000) % len(self.proxies)]
        scheme = getattr(proxy, "proxy_type", "http")
        if scheme in ("socks4", "socks5"):
            auth = f"{proxy.username}:{proxy.password}@" if getattr(proxy, "username", None) else ""
            url = f"{scheme}://{auth}{proxy.host}:{proxy.port}"
        else:
            auth = f"{proxy.username}:{proxy.password}@" if getattr(proxy, "username", None) else ""
            url = f"http://{auth}{proxy.host}:{proxy.port}"
        return {"http": url, "https": url}

    def check(self, name: str) -> Tuple[str, str]:
        status, data, _ = self.post(UNAUTH_URL, {"username": name},
                                    proxies=self._next_proxy())
        verdict, detail = _interpret(status, data)
        self.last_verdict = verdict
        return verdict, detail


class ApiSource(Source):
    """API checker pihak ketiga milik pengguna (opsional).

    Kontrak yang didukung: URL berisi `{username}`, di-GET, respons JSON
    berisi salah satu dari: `taken` (bool), `available` (bool), atau
    `data.available` / `data.taken`. Bisa mengirimkan beberapa URL
    untuk di-rotasi secara otomatis agar rate limit satu endpoint
    tidak menghentikan checker seluruhnya.
    """

    name = "api"
    label = "API pihak ketiga"
    min_interval = 0.05
    default_cooldown = 15.0

    def __init__(self, url: str = "", api_key: str = "", timeout: float = 10.0):
        super().__init__(timeout)
        self.urls: List[str] = self._normalize_urls(url or "")
        self.api_key = (api_key or "").strip()
        self._url_index = 0
        # Initialize with default API URLs if none provided
        if not self.urls:
            self.urls = list(DISCORD_API_URLS)

    @staticmethod
    def _normalize_urls(url: str) -> List[str]:
        """Normalisasi: satu URL atau daftar dipisah koma di dalam satu string konfigurasi."""
        if not url:
            return []
        # Split by comma, strip whitespace
        parts = [p.strip() for p in url.split(",") if p.strip()]
        if len(parts) == 1:
            return [url]
        return parts

    @property
    def enabled(self) -> bool:
        return bool(self.urls)

    def _next_url(self) -> str:
        """Rotasi ke URL berikutnya dalam round-robin."""
        if not self.urls:
            return ""
        self._url_index = (self._url_index + 1) % len(self.urls)
        return self.urls[self._url_index]

    def check(self, name: str) -> Tuple[str, str]:
        if not self.enabled:
            return "UNKNOWN", "URL API belum diisi"
        # Try each URL until one succeeds or all exhausted
        last_error = ""
        for i in range(len(self.urls)):
            url = self._next_url()
            url = url.replace("{username}", quote(name)).replace("{name}", quote(name))
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
                headers["Authorization"] = f"Bearer {self.api_key}"
            self.pacer.wait()
            self._tally("requests")
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)[:90]
                self._tally("errors")
                continue
            if resp.status_code == 429:
                self._tally("limited")
                # Rotate URL and cooldown on 429
                self.cooldown(retry_after=resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 500:
                self.cooldown(30.0)
                continue
            try:
                data = resp.json()
            except ValueError:
                last_error = "respons bukan JSON"
                continue
            taken = available = None
            if isinstance(data, dict):
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                taken = data.get("taken")
                if taken is None:
                    taken = data.get("isTaken")
                if taken is None and isinstance(inner, dict):
                    taken = inner.get("taken")
                if taken is None and isinstance(inner, dict):
                    taken = inner.get("isTaken")
                available = data.get("available")
                if available is None:
                    available = data.get("isAvailable")
                if available is None and isinstance(inner, dict):
                    available = inner.get("available")
                if available is None and isinstance(inner, dict):
                    available = inner.get("isAvailable")
                if isinstance(taken, str):
                    t = taken.lower()
                    taken = t in ("true", "1", "yes", "taken")
                if isinstance(available, str):
                    a = available.lower()
                    available = a in ("true", "1", "yes", "available")
                # some APIs return status
                status_str = str(data.get("status", data.get("result", ""))).lower()
                if not isinstance(taken, bool) and not isinstance(available, bool):
                    if "available" in status_str and "taken" not in status_str:
                        available = True
                    elif "taken" in status_str:
                        taken = True
            if isinstance(taken, bool):
                verdict = "TAKEN" if taken else "AVAILABLE"
            elif isinstance(available, bool):
                verdict = "AVAILABLE" if available else "TAKEN"
            else:
                last_error = "respons tidak dikenali"
                continue
            self.last_verdict = verdict
            return verdict, f"{resp.status_code} {verdict.lower()} ({url[:30]}...)"
        # All URLs exhausted
        self.last_error = last_error or "semua URL gagal"
        return "BLOCKED", f"semua {len(self.urls)} URL terpaku rate limit/error"


# --------------------------------------------------------------------------- #
# Generator rare-only (3L / 4L) untuk username Discord
# --------------------------------------------------------------------------- #

def generate_discord_rare(count: int, length: int, exclude: Optional[Set[str]] = None,
                          seed: Optional[int] = None) -> List[str]:
    """Nama kelangkaan tinggi yang VALID untuk username Discord.

    Hanya huruf kecil, angka, titik dan garis bawah; titik tidak boleh di
    awal/akhir/bertumpuk (Discord menolaknya). Mode lain tidak ada: rare only.
    """
    known = set(exclude or ())
    seen: Set[str] = set()
    out: List[str] = []
    count = max(0, int(count))
    length = GEN_MAX if int(length) == GEN_MAX else GEN_MIN

    for attempt in range(6):
        need = count - len(out)
        if need <= 0:
            break
        batch = generate_rare(max(need * 3, 120), length, chars=DISCORD_CHARS,
                              band=0.45,
                              exclude=known | seen,
                              seed=None if seed is None else seed + attempt)
        if not batch:
            break
        for name in batch:
            ok, _ = validate(name)
            if ok and not is_inappropriate(name) and name not in seen:
                seen.add(name)
                out.append(name)
    return out[:count]


# --------------------------------------------------------------------------- #
# Engine (antrian + worker + statistik)
# --------------------------------------------------------------------------- #

class DiscordEngine:
    """Mesin checker Discord untuk versi web."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = dict(config or {})
        self.history = ScanHistory("discord_history.db")
        self.checker = DiscordChecker(self.config)
        self.events: "queue.Queue[Tuple[str, Any]]" = queue.Queue(maxsize=2000)
        self.q: "queue.Queue[str]" = queue.Queue()
        self.pending: Set[str] = set()
        self._lock = threading.Lock()
        self.workers: List[threading.Thread] = []
        self.running = False
        self.stop_event = threading.Event()
        self.started_at = time.time()
        self.available: List[str] = []
        self.workers_n = max(1, min(int(self.config.get("dg_threads", 2)), 4))
        self._retries: Dict[str, int] = {}
        self.stats: Dict[str, Any] = {
            "checked": 0, "available": 0, "taken": 0, "invalid": 0,
            "rate_limited": 0, "errors": 0,
        }

    # -- util ------------------------------------------------------------- #

    def emit(self, kind: str, payload: Any) -> None:
        try:
            self.events.put_nowait((kind, payload))
        except queue.Full:
            pass

    def log(self, tag: str, text: str) -> None:
        self.emit("log", {"tag": tag, "text": text, "stamp": time.strftime("%H:%M:%S")})

    def queue_size(self) -> int:
        with self._lock:
            return len(self.pending)

    def known_names(self) -> Set[str]:
        try:
            return set(self.history.distinct_names())
        except Exception:                              # noqa: BLE001
            return set()

    def state(self) -> Dict[str, Any]:
        elapsed = max(0.001, time.time() - self.started_at) if self.running else 0.0
        per_sec = round(self.stats["checked"] / elapsed, 2) if elapsed else 0.0
        return {
            "running": self.running,
            "queue": self.queue_size(),
            "workers": self.workers_n,
            "stats": {**self.stats, "per_sec": per_sec},
            "sources": [s.stats() for s in self.checker.sources],
            "available": list(reversed(self.available[-50:])),
            "settings": {
                "token": bool(self.config.get("dg_token")),
                "api": bool(self.config.get("dg_api_url")),
                "proxy": bool(self.checker.proxy.enabled),
                "proxies": len(self.checker.proxy.proxies),
                "pace": self.checker.direct.min_interval,
            },
        }

    # -- antrian ----------------------------------------------------------- #

    def add(self, names: List[str], force: bool = False) -> Dict[str, Any]:
        added = invalid = blocked = duplicates = skipped = 0
        for raw in names:
            name = str(raw or "").strip().lower()
            if not name:
                continue
            ok, _code = validate(name)
            if not ok:
                invalid += 1
                continue
            if is_inappropriate(name):
                blocked += 1
                continue
            if not force:
                row = self.history.get_status(name)
                if row and row.get("status") in (STATUS_AVAILABLE, STATUS_TAKEN):
                    skipped += 1
                    continue
            with self._lock:
                if name in self.pending:
                    duplicates += 1
                    continue
                self.pending.add(name)
            self.q.put(name)
            added += 1
        return {"added": added, "invalid": invalid, "blocked": blocked,
                "duplicates": duplicates, "already_known": skipped,
                "queue": self.queue_size()}

    def clear(self) -> int:
        with self._lock:
            cleared = len(self.pending)
            self.pending.clear()
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.log("warn", f"Antrean Discord dibersihkan — {cleared} nama dibuang")
        return cleared

    def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            length = 4 if int(payload.get("length", 3) or 3) == 4 else 3
        except (TypeError, ValueError):
            length = 3
        try:
            count = max(1, min(int(payload.get("count", 100) or 100), 2000))
        except (TypeError, ValueError):
            count = 100
        names = generate_discord_rare(count, length, exclude=self.known_names())
        result = self.add(names) if payload.get("enqueue", True) else {
            "added": 0, "invalid": 0, "blocked": 0, "duplicates": 0,
            "already_known": 0, "queue": self.queue_size(),
        }
        self.log("ok", f"Discord {length}L rare: {len(names)} nama dibuat, "
                       f"{result['added']} masuk antrean")
        return {"requested": count, "generated": len(names), "length": length,
                "sample": names[:14], **result}

    def check_one(self, name: str, force: bool = False) -> Dict[str, Any]:
        result = self.checker.check(str(name or "").strip().lower(),
                                    history=self.history, force=force)
        if result.status in ("AVAILABLE", "TAKEN") and not result.cached:
            self.stats["checked"] += 1
            self.stats[result.status.lower()] = self.stats.get(result.status.lower(), 0) + 1
        return result.to_dict()

    # -- lifecycle --------------------------------------------------------- #

    def start(self) -> Dict[str, Any]:
        if self.running:
            return {"running": True, "workers": self.workers_n}
        self.running = True
        self.stop_event.clear()
        self.started_at = time.time()
        self.checker.reload()
        for idx in range(self.workers_n):
            thread = threading.Thread(target=self._worker, name=f"Discord-{idx}", daemon=True)
            thread.start()
            self.workers.append(thread)
        self.emit("status", {"state": "running", "workers": self.workers_n})
        self.log("ok", f"Mesin Discord jalan — {self.workers_n} worker, sumber: "
                       f"{', '.join(self.checker.names())}")
        return {"running": True, "workers": self.workers_n}

    def stop(self) -> Dict[str, Any]:
        if not self.running:
            return {"running": False}
        self.running = False
        self.stop_event.set()
        for thread in self.workers:
            thread.join(timeout=1.0)
        self.workers = []
        self.emit("status", {"state": "stopped", "workers": 0})
        self.log("warn", "Mesin Discord dihentikan")
        return {"running": False}

    def _worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                name = self.q.get(timeout=0.3)
            except queue.Empty:
                if not self.running:
                    break
                continue
            requeue = False
            try:
                # Tunggu sebentar saja - lebih agresif
                while not self.stop_event.is_set():
                    wait = self.checker.wait_until_healthy(cap=1.5)
                    if wait <= 0:
                        break
                    time.sleep(min(wait, 0.3))
                if self.stop_event.is_set():
                    requeue = True
                    continue

                result = self.checker.check(name, history=self.history)
                if result.status == "RATE_LIMITED":
                    tries = self._retries.get(name, 0) + 1
                    if tries <= 2:
                        self._retries[name] = tries
                        requeue = True
                    else:
                        self._retries.pop(name, None)
                        self._publish(result)
                else:
                    self._retries.pop(name, None)
                    self._publish(result)
            except Exception as exc:                    # noqa: BLE001
                self.stats["errors"] += 1
                self.log("bad", f"{name}: {exc}")
                try:
                    self.history.record(name, STATUS_ERROR, "engine", str(exc)[:100])
                except Exception:                       # noqa: BLE001
                    pass
            finally:
                self.q.task_done()
                if requeue:
                    # tetap di `pending`, kembali ke antrean untuk dicoba lagi
                    try:
                        self.q.put_nowait(name)
                    except queue.Full:
                        with self._lock:
                            self.pending.discard(name)
                else:
                    with self._lock:
                        self.pending.discard(name)

    def _publish(self, result: Result) -> None:
        status = result.status
        if status == "AVAILABLE":
            self.stats["available"] += 1
            self.available.append(result.name)
            with open("discord_available.txt", "a", encoding="utf-8") as handle:
                handle.write(result.name + "\n")
        elif status == "TAKEN":
            self.stats["taken"] += 1
        elif status == "INVALID":
            self.stats["invalid"] += 1
        elif status == "RATE_LIMITED":
            self.stats["rate_limited"] += 1
        else:
            self.stats["errors"] += 1
        self.stats["checked"] += 1

        stored = {
            "AVAILABLE": STATUS_AVAILABLE, "TAKEN": STATUS_TAKEN,
            "RATE_LIMITED": STATUS_RATE_LIMITED,
        }.get(status, STATUS_ERROR)
        try:
            self.history.record(result.name, stored, result.source or "rules",
                                result.reason[:120])
        except Exception:                               # noqa: BLE001
            pass
        self.emit("result", result.to_dict())


# --------------------------------------------------------------------------- #
# DiscordChecker
# --------------------------------------------------------------------------- #

class DiscordChecker:
    """Orkestrasi semua sumber: pilih sumber sehat, hormati limit tiap sumber."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = dict(config or {})
        self.direct = DirectSource()
        self.token = TokenSource(self.config.get("dg_token", ""))
        self.proxy = ProxySource(self.config.get("proxy_file", "proxies.txt"))
        self.api = ApiSource(self.config.get("dg_api_url", ""),
                             self.config.get("dg_api_key", ""))
        self.sources: List[Source] = []
        self.apply_pace()
        self._refresh()

    def apply_pace(self) -> None:
        """Pacing endpoint resmi bisa diatur pengguna (default 1,5 dtk)."""
        try:
            pace = float(self.config.get("dg_pace", 0) or 0)
        except (TypeError, ValueError):
            pace = 0.0
        if pace >= 0.3:
            self.direct.min_interval = pace
            self.direct.pacer.interval = pace

    def _refresh(self) -> None:
        self.sources = [s for s in (self.direct, self.token, self.proxy, self.api) if s.enabled]

    def names(self) -> List[str]:
        return [s.name for s in self.sources]

    def reload(self) -> None:
        self.proxy.reload()
        self.token.token = (self.config.get("dg_token", "") or "").strip()
        # Normalize and rotate URLs for API source
        self.api.urls = self.api._normalize_urls(self.config.get("dg_api_url", ""))
        self.api.api_key = (self.config.get("dg_api_key", "") or "").strip()
        self.api._url_index = 0
        self.apply_pace()
        self._refresh()

    def wait_until_healthy(self, cap: float = 30.0) -> float:
        if not self.sources:
            return 0.0
        # Return the soonest cooldown among healthy sources
        healthy = [s for s in self.sources if s.healthy()]
        if healthy:
            soonest = min(s.cooldown_for() for s in healthy)
            return max(0.0, min(soonest, float(cap)))
        return cap

    def check(self, name: str, history: Optional[ScanHistory] = None,
              force: bool = False) -> Result:
        name = (name or "").strip().lower()
        ok, code = validate(name)
        if not ok:
            return Result(name, "INVALID", 0, f"rules: {code}", source="rules")

        if history is not None and not force:
            row = history.get_status(name)
            if row and row.get("status") in (STATUS_AVAILABLE, STATUS_TAKEN):
                return Result(name, str(row["status"]).upper(), 0,
                              f"cache: {row.get('reason') or row.get('status')}",
                              source="cache", cached=True)

        # Try sources in order, respecting cooldowns
        used_sources: List[str] = []
        for source in self.sources:
            if not source.healthy():
                # Source on cooldown, skip but record
                used_sources.append(f"{source.name} cooldown")
                continue
            verdict, detail = source.check(name)
            used_sources.append(f"{source.name}: {detail}")
            if verdict in ("TAKEN", "AVAILABLE", "INVALID"):
                return Result(name, verdict, 200, f"{source.name}: {detail}",
                              source=source.name)
            # If BLOCKED (rate limited), keep trying other sources
            # rather than returning early

        # If we got here, no source returned a definitive verdict.
        # Return rate-limited status with info about which sources were tried.
        notes = "; ".join(used_sources) if used_sources else "tidak ada sumber sehat"
        return Result(name, "RATE_LIMITED", 0, notes, source="limit")