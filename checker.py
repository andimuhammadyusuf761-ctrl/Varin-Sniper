"""
checker.py — Multi-source, proxyless, zero-false-flag Minecraft name checker.

Source chain (urutan prioritas, semua diverifikasi live terhadap API:

  1. playerdb.co               -> https://playerdb.co/api/player/minecraft/{name}
  2. Minecraft Services (resmi)-> https://api.minecraftservices.com/minecraft/profile/lookup/name/{name}
  3. Mojang legacy API         -> https://api.mojang.com/users/profiles/minecraft/{name}
  4. Ashcon (backend mcchecker)-> https://api.ashcon.app/mojang/v2/user/{name}
  5. NameMC                    -> scraping ketat (Cloudflare-aware)
  6. mcchecker.net             -> scraping ketat (Cloudflare-aware)

Kontrak API yang diverifikasi langsung (live test):

  playerdb.co     200 + success:true  + data.player.username == name -> TAKEN
                  400 + success:false + code "minecraft.invalid_username" -> AVAILABLE*
                  429 -> hormati Retry-After, cooldown
  minecraftservices lookup/name:
                  200 + {"id": ..., "name": ...} -> TAKEN
                  404 "Couldn't find any profile with name X" -> AVAILABLE
  api.mojang.com  200 -> TAKEN | 204 / 404 -> AVAILABLE | 429 -> cooldown
  ashcon          200 -> TAKEN | 404 -> AVAILABLE | 429 -> cooldown
  NameMC          profile page 200 -> TAKEN | 404 -> AVAILABLE | 403/503 -> BLOCKED
  mcchecker       POST /check, label `label-success` / `label-danger` | challenge -> BLOCKED

*) AVAILABLE dari playerdb TIDAK PERNAH final sendiri: playerdb itu cache,
   jadi harus dikonfirmasi dulu oleh sumber live (Minecraft Services /
   Mojang / Ashcon). Kalau semua sumber live sedang cooldown, hasilnya
   UNKNOWN + retry — TIDAK PERNAH menebak. Ini yang membunuh false flag.

Aturan bypass 429 tanpa proxy:
  - Pacing per-source (jarak minimal antar request ke sumber yang sama).
  - Cooldown per-source saat 429/challenge (Retry-After dihormati), traffic
    otomatis dipindah ke source sehat.
  - Semua sumber punya bucket limit sendiri -> total throughput tetap tinggi.
"""

import threading
import time
import json
import random
import re
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import requests

# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
PLAYERDB_URL = "https://playerdb.co/api/player/minecraft/{name}"
MS_LOOKUP_URL = "https://api.minecraftservices.com/minecraft/profile/lookup/name/{name}"
MOJANG_URL = "https://api.mojang.com/users/profiles/minecraft/{name}"
ASHCON_URL = "https://api.ashcon.app/mojang/v2/user/{name}"

NAMEMC_URL = "https://namemc.com/search?q={name}"
NAMEMC_PROFILE_URL = "https://namemc.com/profile/{name}"
MCCHECKER_URL = "https://mcchecker.net/check"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

API_HEADERS = {
    "User-Agent": "MC-Sniper/2.2 (Minecraft name checker; contact: local user)",
    "Accept": "application/json",
}

CF_MARKERS = (
    "just a moment",
    "_cf_chl_opt",
    "challenge-platform",
    "cf-browser-verification",
    "checking your browser",
    "attention required",
)


def _json_or_none(body: str):
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


class NameStatus(Enum):
    AVAILABLE = "AVAILABLE"
    TAKEN = "TAKEN"
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class CheckResult:
    def __init__(self, name: str, status: NameStatus, code: int = 0,
                 reason: str = "", info: Optional[dict] = None):
        self.name = name
        self.status = status
        self.code = code
        self.reason = reason
        self.info = info or {}
        self.timestamp = time.time()

    @property
    def response_code(self) -> int:
        return self.code

    def __repr__(self) -> str:
        return f"<CheckResult {self.name} {self.status.value}>"


# --------------------------------------------------------------------------- #
# Pacing: gerbang jarak-minimal per source (thread-safe)
# --------------------------------------------------------------------------- #
class _Pacer:
    """Menjamin jarak minimal >= interval antar request ke satu sumber."""

    def __init__(self, interval: float):
        self.interval = max(0.0, float(interval))
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.time()
            wait_for = self._next_slot - now
            if wait_for > 0:
                self._next_slot += self.interval
            else:
                self._next_slot = now + self.interval
                wait_for = 0.0
        if wait_for > 0:
            time.sleep(wait_for)

    def penalize(self, seconds: float) -> None:
        """Tahan semua request ke source ini selama X detik (cooldown 429)."""
        if seconds <= 0:
            return
        with self._lock:
            now = time.time()
            target = now + seconds
            if target > self._next_slot:
                self._next_slot = target


# --------------------------------------------------------------------------- #
# Source base
# --------------------------------------------------------------------------- #
class _Source:
    """Satu sumber kebenaran. fetch() mengembalikan verdict ketat:
    TAKEN / AVAILABLE / UNKNOWN / BLOCKED. Tidak pernah menebak."""

    name = "base"
    priority = 50
    live_available = True     # boleh jadi sumber final AVAILABLE
    min_interval = 0.25
    default_cooldown = 30.0

    def __init__(self):
        self.session = requests.Session()
        self.pacer = _Pacer(self.min_interval)
        self.cooldown_until = 0.0
        self.last_error = ""

    # -- infra ------------------------------------------------------------- #
    def healthy(self) -> bool:
        return time.time() >= self.cooldown_until

    def _cooldown(self, seconds: Optional[float] = None, retry_after=None) -> None:
        dur = seconds if seconds is not None else self.default_cooldown
        if retry_after is not None:
            try:
                ra = float(retry_after)
                if ra > 0:
                    dur = max(dur, ra)
            except (TypeError, ValueError):
                pass
        self.cooldown_until = time.time() + min(dur, 900.0)

    def _get(self, url: str, headers: Optional[dict] = None,
             timeout: float = 10.0) -> Tuple[int, str, Optional[dict]]:
        """GET dengan pacing. Return (status, body, retry_after)."""
        retry_after = None
        self.pacer.wait()
        resp = self.session.get(url, headers=headers or {}, timeout=timeout,
                                allow_redirects=True)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
        return resp.status_code, resp.text or "", retry_after

    def _post(self, url: str, data: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: float = 10.0) -> Tuple[int, str, Optional[dict]]:
        retry_after = None
        self.pacer.wait()
        resp = self.session.post(url, data=data or {}, headers=headers or {},
                                 timeout=timeout, allow_redirects=True)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
        return resp.status_code, resp.text or "", retry_after

    # -- deteksi Cloudflare / challenge page ------------------------------- #
    @staticmethod
    def _is_challenge(status: int, body: str) -> bool:
        lower = (body or "")[:4000].lower()
        if status in (403, 503):
            return True
        if "cf-mitigated" in lower and "challenge" in lower:
            return True
        return any(marker in lower for marker in CF_MARKERS)

    # -- verdict interface -------------------------------------------------- #
    def fetch(self, name: str) -> Tuple[str, int, str]:
        """Return (verdict, http_code, detail). verdict: TAKEN/AVAILABLE/UNKNOWN/BLOCKED."""
        raise NotImplementedError

    def safe_fetch(self, name: str) -> Tuple[str, int, str]:
        try:
            return self.fetch(name)
        except requests.exceptions.Timeout:
            return "UNKNOWN", 0, "timeout"
        except requests.exceptions.ConnectionError:
            return "UNKNOWN", 0, "connection error"
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)[:80]
            return "UNKNOWN", 0, self.last_error


# --------------------------------------------------------------------------- #
# 1. PlayerDB — https://playerdb.co/api/player/minecraft/$ID
# --------------------------------------------------------------------------- #
class PlayerDBSource(_Source):
    name = "playerdb"
    priority = 10
    live_available = False          # hasil cache -> wajib konfirmasi sumber live
    min_interval = 0.30
    default_cooldown = 8.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        status, body, retry_after = self._get(
            PLAYERDB_URL.format(name=name), headers=API_HEADERS)
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "playerdb 429"
        if self._is_challenge(status, body):
            self._cooldown(30.0)
            return "BLOCKED", status, "cloudflare challenge"

        if status == 200:
            data = _json_or_none(body)
            if not isinstance(data, dict):
                return "UNKNOWN", 200, "playerdb body tidak terduga"
            if data.get("success") is True:
                player = (data.get("data") or {}).get("player") or {}
                username = str(player.get("username", "")).lower()
                if username == name:
                    return "TAKEN", 200, "playerdb: profile ada"
                if username:
                    # nama sudah dipakai -> dipindah ke pemilik lain -> current name beda
                    return "TAKEN", 200, f"playerdb: dipakai oleh '{username}'"
                return "UNKNOWN", 200, "playerdb: success tanpa username"
            # success:false -> jatuh ke branch 400-style di bawah
            code = str(data.get("code", "")).lower()
            if code == "minecraft.invalid_username" or "invalid" in code:
                return "AVAILABLE", 400, "playerdb: username tidak terdaftar"
            if code == "minecraft.api_error":
                return "BLOCKED", 502, "playerdb: upstream mojang error"
            return "UNKNOWN", 200, f"playerdb: {code or 'success false'}"

        if status == 400:
            data = _json_or_none(body)
            code = str((data or {}).get("code", "")).lower()
            if code == "minecraft.invalid_username":
                return "AVAILABLE", 400, "playerdb: username tidak terdaftar"
            return "UNKNOWN", 400, f"playerdb 400: {code or body[:60]}"

        if status >= 500:
            self._cooldown(10.0)
            return "BLOCKED", status, f"playerdb {status}"

        return "UNKNOWN", status, f"playerdb http {status}"


# --------------------------------------------------------------------------- #
# 2. Minecraft Services — endpoint resmi launcher, LIVE (tanpa cache)
# --------------------------------------------------------------------------- #
class MSLookupSource(_Source):
    name = "minecraftservices"
    priority = 20
    live_available = True
    min_interval = 0.80
    default_cooldown = 45.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        status, body, retry_after = self._get(
            MS_LOOKUP_URL.format(name=name), headers=API_HEADERS)
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "minecraftservices 429"

        if status == 200:
            data = _json_or_none(body)
            if isinstance(data, dict) and data.get("id") and \
                    str(data.get("name", "")).lower() == name:
                return "TAKEN", 200, "minecraftservices: profile ada"
            return "UNKNOWN", 200, "msl 200 tanpa profile valid"

        if status == 404:
            # body resmi: {"path": ..., "errorMessage": "Couldn't find any
            # profile with name X"} -> status code dipercaya, BUKAN substring
            return "AVAILABLE", 404, "minecraftservices: tidak terdaftar"

        if status == 400:
            return "UNKNOWN", 400, "msl: nama tidak valid?"

        if self._is_challenge(status, body):
            self._cooldown(30.0)
            return "BLOCKED", status, "challenge page"

        if status >= 500:
            self._cooldown(10.0)
            return "BLOCKED", status, f"msl {status}"

        return "UNKNOWN", status, f"msl http {status}"


# --------------------------------------------------------------------------- #
# 3. Mojang legacy API
# --------------------------------------------------------------------------- #
class MojangSource(_Source):
    name = "mojang"
    priority = 30
    live_available = True
    min_interval = 1.05            # resmi: 600 req / 10 menit per IP
    default_cooldown = 120.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        status, body, retry_after = self._get(
            MOJANG_URL.format(name=name), headers=API_HEADERS)
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "mojang 429"
        if status == 200:
            data = _json_or_none(body)
            if isinstance(data, dict) and data.get("id") and \
                    str(data.get("name", "")).lower() == name:
                return "TAKEN", 200, "mojang: profile ada"
            return "UNKNOWN", 200, "mojang 200 tanpa profile valid"
        if status in (204, 404):
            return "AVAILABLE", status, "mojang: tidak terdaftar"
        if self._is_challenge(status, body):
            self._cooldown(30.0)
            return "BLOCKED", status, "challenge page"
        if status >= 500:
            self._cooldown(10.0)
            return "BLOCKED", status, f"mojang {status}"
        return "UNKNOWN", status, f"mojang http {status}"


# --------------------------------------------------------------------------- #
# 4. Ashcon — backend yang dipakai mcchecker.net untuk lookup
# --------------------------------------------------------------------------- #
class AshconSource(_Source):
    name = "ashcon"
    priority = 40
    live_available = True
    min_interval = 2.5
    default_cooldown = 180.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        status, body, retry_after = self._get(
            ASHCON_URL.format(name=name), headers=API_HEADERS)
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "ashcon 429"
        if status == 200:
            data = _json_or_none(body)
            user = (data or {}).get("user") or {} if isinstance(data, dict) else {}
            if str(user.get("username", "")).lower() == name:
                return "TAKEN", 200, "ashcon: profile ada"
            return "UNKNOWN", 200, "ashcon 200 tanpa username cocok"
        if status == 404:
            return "AVAILABLE", 404, "ashcon: tidak terdaftar"
        if self._is_challenge(status, body):
            self._cooldown(30.0)
            return "BLOCKED", status, "challenge page"
        return "UNKNOWN", status, f"ashcon http {status}"


# --------------------------------------------------------------------------- #
# 5. NameMC — scraping ketat, hanya sinyal terstruktur
# --------------------------------------------------------------------------- #
class NameMCSource(_Source):
    name = "namemc"
    priority = 50
    live_available = True          # 404 page = tidak terdaftar
    min_interval = 2.0
    default_cooldown = 120.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        # Halaman profil langsung: ada = TAKEN, 404 = AVAILABLE, challenge = BLOCKED
        status, body, retry_after = self._get(
            NAMEMC_PROFILE_URL.format(name=name), headers=BROWSER_HEADERS)

        if self._is_challenge(status, body):
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", status, "namemc: cloudflare challenge"
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "namemc 429"
        if status == 200:
            lower = body[:20000].lower()
            # struktur profil: <h1>nama</h1> + uuid 32-hex di halaman
            h1 = re.search(r"<h1[^>]*>\s*" + re.escape(name) + r"\s*</h1>",
                           body, re.IGNORECASE)
            uuid_hit = re.search(r"/profile/([0-9a-fA-F]{32})", body)
            if h1 and uuid_hit:
                return "TAKEN", 200, "namemc: halaman profil ada"
            if "look up a user" in lower or "not found" in lower:
                return "AVAILABLE", 404, "namemc: profil tidak ada"
            return "UNKNOWN", 200, "namemc: halaman ambigu"
        if status == 404:
            return "AVAILABLE", 404, "namemc: profil tidak ada"
        self._cooldown(retry_after=retry_after)
        return "BLOCKED", status, f"namemc http {status}"


# --------------------------------------------------------------------------- #
# 6. mcchecker.net — scraping ketat (form POST /check + honeypot kosong)
# --------------------------------------------------------------------------- #
class McCheckerSource(_Source):
    name = "mcchecker"
    priority = 60
    live_available = True
    min_interval = 2.5
    default_cooldown = 180.0

    def fetch(self, name: str) -> Tuple[str, int, str]:
        form = {
            "search": name,
            "hide": "",
            # honeypot anti-bot HARUS kosong
            "totot": "", "flowstate": "", "ChefsKiss": "",
            "Bubble": "", "LilBroski": "",
        }
        status, body, retry_after = self._post(
            MCCHECKER_URL, data=form,
            headers={**BROWSER_HEADERS, "Referer": "https://mcchecker.net"})

        if self._is_challenge(status, body):
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", status, "mcchecker: cloudflare challenge"
        if status == 429:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", 429, "mcchecker 429"
        if status != 200:
            self._cooldown(retry_after=retry_after)
            return "BLOCKED", status, f"mcchecker http {status}"

        # Result label terstruktur pada halaman hasil.
        # Ambil hanya label yang berdekatan dengan nama yang dicek, dan
        # pastikan tidak ambigu (legend "Search Labels" di homepage juga
        # memuat kata AVAILABLE/PREMIUM, jadi hitungan ganda = UNKNOWN).
        results = re.findall(
            r'class="label label-(success|danger)">\s*'
            r'(AVAILABLE|PREMIUM|2-CHAR[^<]*)\s*</span>',
            body, re.IGNORECASE)
        has_name = re.search(re.escape(name), body, re.IGNORECASE)
        if not has_name:
            return "UNKNOWN", 200, "mcchecker: nama tidak muncul di halaman"
        if len(results) == 1:
            css, label = results[0]
            label = label.upper()
            if label.startswith("PREMIUM") or css == "danger":
                return "TAKEN", 200, f"mcchecker: {label}"
            if label == "AVAILABLE" or label.startswith("2-CHAR"):
                # 2-CHAR = tak bisa diklaim -> diperlakukan TAKEN untuk sniper
                if label.startswith("2-CHAR"):
                    return "TAKEN", 200, "mcchecker: 2-CHAR (tak bisa diklaim)"
                return "AVAILABLE", 200, "mcchecker: AVAILABLE"
        return "UNKNOWN", 200, "mcchecker: hasil ambigu"


_ALL_SOURCES = [
    PlayerDBSource(),
    MSLookupSource(),
    MojangSource(),
    AshconSource(),
    NameMCSource(),
    McCheckerSource(),
]


# --------------------------------------------------------------------------- #
# Checker
# --------------------------------------------------------------------------- #
class Checker:
    """Proxyless multi-source checker. Satu instance aman dipakai per-thread
    (pacing global per sumber dijaga lintas thread)."""

    def __init__(self, delay: float = 0.0, timeout: float = 10.0,
                 proxies=None, proxy_rotate: bool = False, stealth: bool = True,
                 adaptive: bool = False, max_retries: int = 2, **_ignored):
        # checker ini 100% proxyless — argumen proxy diabaikan sengaja
        self.timeout = float(timeout)
        self.max_retries = max(1, int(max_retries))
        self.sources = _ALL_SOURCES
        self._session = requests.Session()  # sesi netral (kompatibilitas lama)
        self._unknown_counts: Dict[str, int] = {}
        self._counts_lock = threading.Lock()

    @property
    def session(self) -> requests.Session:
        return self._session

    # ------------------------------------------------------------------ #
    def check(self, name: str) -> CheckResult:
        name = (name or "").strip().lower()
        if not name or not (3 <= len(name) <= 16):
            return CheckResult(name, NameStatus.ERROR, 0, "invalid name")

        seen_blocked = False
        seen_unknown = False
        round_no = 0

        while round_no <= self.max_retries:
            round_no += 1
            sources = sorted(self.sources, key=lambda s: s.priority)

            for source in sources:
                if not source.healthy():
                    continue

                verdict, code, detail = source.safe_fetch(name)

                if verdict == "TAKEN":
                    with self._counts_lock:
                        self._unknown_counts.pop(name, None)
                    return CheckResult(name, NameStatus.TAKEN, code, f"{source.name}: {detail}")

                if verdict == "AVAILABLE":
                    if source.live_available:
                        with self._counts_lock:
                            self._unknown_counts.pop(name, None)
                        return CheckResult(name, NameStatus.AVAILABLE, code,
                                           f"{source.name}: {detail}")
                    # playerdb cache -> konfirmasi pakai sumber live sebelum final
                    confirmed = self._confirm_live(name, skip=source.name)
                    if confirmed is True:
                        return CheckResult(name, NameStatus.AVAILABLE, code,
                                           f"{source.name} + live confirm")
                    if confirmed is False:
                        # cache playerdb basi -> nama ternyata sudah dipakai
                        return CheckResult(name, NameStatus.TAKEN, code,
                                           "live source bilang TAKEN")
                    seen_unknown = True

                elif verdict == "BLOCKED":
                    seen_blocked = True
                else:
                    seen_unknown = True

            # semua sumber dicoba: kalau masih ada yang cooling-down, tunggu
            # sebentar lalu satu round lagi (dibatasi) supaya verdict final
            # selalu berdasar data nyata, bukan tebakan.
            if any(s.healthy() for s in self.sources):
                break
            if round_no <= self.max_retries:
                time.sleep(min(1.5 + random.random(), 2.5))

        with self._counts_lock:
            tries = self._unknown_counts.get(name, 0) + 1
            self._unknown_counts[name] = tries
            exhausted = tries >= self.max_retries + 2
        if exhausted:
            with self._counts_lock:
                self._unknown_counts.pop(name, None)

        if seen_blocked and not seen_unknown:
            status, reason = NameStatus.RATE_LIMITED, "semua sumber kena limit/challenge"
        else:
            status, reason = NameStatus.UNKNOWN, "tidak ada sumber yang bisa memastikan"
        if exhausted:
            status, reason = NameStatus.ERROR, f"give up: {reason}"
        return CheckResult(name, status, 0, reason)

    # ------------------------------------------------------------------ #
    def _confirm_live(self, name: str, skip: str = "") -> Optional[bool]:
        """True=AVAILABLE terkonfirmasi live, False=TAKEN, None=tidak pasti."""
        for source in sorted(self.sources, key=lambda s: s.priority):
            if source.name == skip or not source.live_available or not source.healthy():
                continue
            verdict, _code, _detail = source.safe_fetch(name)
            if verdict == "AVAILABLE":
                return True
            if verdict == "TAKEN":
                return False
        return None

    # alias lama supaya kode lain tetap jalan
    check_name = check

    def pause(self) -> None:
        """Pacing sudah dihandle per-source — tidak ada jeda tambahan."""
        pass


# ---------------------------------------------------------------------- #
# Helper sekuensial (tanpa GUI)
# ---------------------------------------------------------------------- #
def run_file(combo_path: str, checker: Optional[Checker] = None,
             on_hit: Optional[Callable[[str], None]] = None,
             open_namemc: bool = False, stop_event: Optional[threading.Event] = None):
    import webbrowser

    checker = checker or Checker(delay=0.0)
    hits: List[str] = []
    stop_event = stop_event or threading.Event()

    with open(combo_path, "r", encoding="utf-8", errors="ignore") as fh:
        names = [line.strip() for line in fh if line.strip()]

    for name in names:
        if stop_event.is_set():
            break
        result = checker.check(name)
        if result.status == NameStatus.AVAILABLE:
            hits.append(result.name)
            print(f"[+] {result.name}  ({result.reason})")
            if open_namemc:
                webbrowser.open(NAMEMC_URL.format(name=result.name))
            if on_hit:
                on_hit(result.name)
        elif result.status == NameStatus.TAKEN:
            print(f"[-] {result.name}")
        else:
            print(f"[!] {result.name}  ({result.status.value}: {result.reason})")
        checker.pause()

    return hits


if __name__ == "__main__":
    import sys
    import json as _json

    if len(sys.argv) < 2:
        print("usage: python checker.py <name|combo.txt>")
        raise SystemExit(1)

    target = sys.argv[1]
    if target.lower().endswith(".txt"):
        found = run_file(target)
        print(f"\n{len(found)} available -> hits.txt")
        with open("hits.txt", "a", encoding="utf-8") as fh:
            for n in found:
                fh.write(n + "\n")
    else:
        res = Checker().check(target)
        print(f"{res.name} -> {res.status.value}  [{res.reason}]")
        if res.info:
            print(_json.dumps(res.info, indent=2))
