"""
claimer.py — Auto Claim module: Microsoft OAuth login -> Xbox Live -> XSTS -> Minecraft API.

Login Microsoft resmi melalui Microsoft.com dengan OAuth2 authorization code flow
(client id bawaan Minecraft Launcher, tidak butuh registrasi Azure).
Token dan callback ditangani dengan aman; token yang valid tapi dianggap invalid
(dikarenakan verifikasi profil 429/401) sekarang ditangani dengan benar.

  * Email + Password -> login.microsoftonline.com (OAuth2, browser embedded)
  * Device code flow sebagai fallback (tidak butuh browser)
  * mc_token (eyJ…) / MS token (M.C.. / M.R.. / eyJ MS) dengan auto-detect
  * Refresh token otomatis via Microsoft token endpoint
  * Exp Minecraft token dibaca dari JWT claim `exp`
  * 429 saat verifikasi profil tidak lagi dianggap token invalid
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import webbrowser
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger("VarinSniper.Claimer")

# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
# Client id resmi Minecraft Launcher (publik, tidak butuh registrasi Azure).
BUILTIN_CLIENT_ID = "000000004C1D24EE"

# Microsoft OAuth2 resmi via Microsoft.com (login.microsoftonline.com)
MS_LOGIN_HOST = "https://login.microsoftonline.com"
AUTHORIZE_URL = f"{MS_LOGIN_HOST}/common/oauth2/v2.0/authorize"
TOKEN_URL = f"{MS_LOGIN_HOST}/common/oauth2/v2.0/token"
DEVICE_CODE_URL = f"{MS_LOGIN_HOST}/common/oauth2/v2.0/devicecode"
REDIRECT_URI = "http://localhost:8765/callback"
MS_SCOPE = "XboxLive.signin service::user.auth.xboxlive.com::MBI_SSL offline_access"

# XBL / XSTS / Minecraft
XBL_AUTH = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN = "https://api.minecraftservices.com/authentication/login_with_xbl"
MC_PROFILE = "https://api.minecraftservices.com/minecraft/profile"
MC_NAME_AVAILABILITY = "https://api.minecraftservices.com/minecraft/profile/nameavailability"
MC_NAME_CHANGE_INFO = "https://api.minecraftservices.com/minecraft/profile/namechange"

TOKEN_STORE = "ms_tokens.json"

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


class ClaimStatus(Enum):
    SUCCESS = "success"
    NAME_TAKEN = "name_taken"
    NOT_ELIGIBLE = "not_eligible"
    TOKEN_INVALID = "token_invalid"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    COOLDOWN = "cooldown"


class MMCLoginError(Exception):
    pass


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def _clean_token(raw: str) -> str:
    """Strip semua sampah yang sering ikut saat paste token."""
    tok = (raw or "").strip().strip('"').strip("'")
    tok = re.sub(r"^bearer\s+", "", tok, flags=re.IGNORECASE)
    tok = tok.replace("\r", "").replace("\n", "").replace(" ", "")
    return tok.strip()


def classify_token(raw: str) -> str:
    """'mc_token' | 'ms_token' | 'unknown'"""
    tok = _clean_token(raw)
    if not tok:
        return "unknown"
    if tok.startswith("eyJ"):
        return "mc_token"
    if tok.startswith("M."):
        return "ms_token"
    return "unknown"


# --------------------------------------------------------------------------- #
# Account
# --------------------------------------------------------------------------- #
class MMCAccount:
    def __init__(self, email: str = "", client_id: str = "",
                 refresh_token: str = "", mc_access_token: str = "",
                 mc_token_expiry: float = 0.0, profile_name: str = "",
                 token_verified: bool = False, token_type: str = "",
                 ms_access_token: str = "", ms_token_expiry: float = 0.0):
        self.email = email
        self.client_id = client_id or BUILTIN_CLIENT_ID
        self.refresh_token = refresh_token
        self.mc_access_token = mc_access_token
        self.mc_token_expiry = mc_token_expiry
        self.profile_name = profile_name
        self.token_verified = token_verified
        self.token_type = token_type
        self.ms_access_token = ms_access_token
        self.ms_token_expiry = ms_token_expiry
        self.failed_count = 0
        self.last_used = 0.0
        self.cooldown_until = 0.0
        self.enabled = True
        self._lock = threading.Lock()

    def label(self) -> str:
        if self.profile_name:
            return f"{self.email or 'token'} [{self.profile_name}]"
        return self.email or "token-account"

    def is_valid(self) -> bool:
        if not self.enabled:
            return False
        if self.cooldown_until > time.time():
            return False
        if self.failed_count >= 5:
            return False
        return True

    def is_token_valid(self) -> bool:
        if not self.mc_access_token:
            return False
        return self.mc_token_expiry > time.time() + 60

    def mark_failed(self):
        with self._lock:
            self.failed_count += 1
            self.last_used = time.time()
            if self.failed_count >= 3:
                self.cooldown_until = time.time() + 300

    def mark_success(self):
        with self._lock:
            self.failed_count = max(0, self.failed_count - 1)
            self.last_used = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email": self.email,
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "mc_access_token": self.mc_access_token,
            "mc_token_expiry": self.mc_token_expiry,
            "profile_name": self.profile_name,
            "token_verified": self.token_verified,
            "token_type": self.token_type,
            "ms_access_token": self.ms_access_token,
            "ms_token_expiry": self.ms_token_expiry,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MMCAccount":
        return cls(
            email=d.get("email", ""),
            client_id=d.get("client_id", ""),
            refresh_token=d.get("refresh_token", ""),
            mc_access_token=d.get("mc_access_token", ""),
            mc_token_expiry=float(d.get("mc_token_expiry", 0.0)),
            profile_name=d.get("profile_name", ""),
            token_verified=bool(d.get("token_verified", False)),
            token_type=d.get("token_type", ""),
            ms_access_token=d.get("ms_access_token", ""),
            ms_token_expiry=float(d.get("ms_token_expiry", 0.0)),
        )


class ClaimResult:
    def __init__(self, name: str, account: Optional[MMCAccount], status: ClaimStatus, message: str = ""):
        self.name = name
        self.account = account
        self.status = status
        self.message = message
        self.timestamp = time.time()

    def __repr__(self) -> str:
        label = self.account.label() if self.account else "?"
        return f"{self.name!r} ({label}) -> {self.status.value}: {self.message}"


def load_accounts(path: str = TOKEN_STORE) -> List[MMCAccount]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [MMCAccount.from_dict(d) for d in data]
    except Exception as e:
        logger.error(f"load_accounts failed: {e}")
        return []


def save_accounts(accounts: List[MMCAccount], path: str = TOKEN_STORE) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in accounts], f, indent=2)
    except Exception as e:
        logger.error(f"save_accounts failed: {e}")


# --------------------------------------------------------------------------- #
# XBL -> XSTS -> Minecraft
# --------------------------------------------------------------------------- #
def _mc_token_from_ms(ms_access_token: str, session: requests.Session) -> Dict[str, Any]:
    hdr = {"Content-Type": "application/json", "Accept": "application/json"}

    def _xbl(ticket_prefix: str) -> Dict[str, Any]:
        r = session.post(XBL_AUTH, headers=hdr, json={
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"{ticket_prefix}={ms_access_token}",
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        }, timeout=30)
        if r.status_code != 200:
            raise MMCLoginError(f"XBL auth failed: HTTP {r.status_code}")
        return r.json()

    try:
        xbl = _xbl("d")
    except MMCLoginError:
        xbl = _xbl("t")
    xbl_token = xbl["Token"]

    r = session.post(XSTS_AUTH, headers=hdr, json={
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    }, timeout=30)
    if r.status_code != 200:
        raise MMCLoginError(f"XSTS auth failed: HTTP {r.status_code}")
    xsts = r.json()
    xsts_token = xsts["Token"]
    uhs = xsts["DisplayClaims"]["xui"][0]["uhs"]

    r = session.post(MC_LOGIN, headers={"Content-Type": "application/json"},
                     json={"identityToken": f"XBL3.0 x={uhs};{xsts_token}"}, timeout=30)
    if r.status_code != 200:
        raise MMCLoginError(f"MC login failed: HTTP {r.status_code}")
    time.sleep(0.2)
    return r.json()


def _jwt_exp(token: str) -> float:
    """Baca claim `exp` dari JWT Minecraft/MS token. 0.0 kalau tidak bisa."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get("exp", 0.0))
    except Exception:  # noqa: BLE001
        return 0.0


# --------------------------------------------------------------------------- #
# Microsoft OAuth2 via Microsoft.com (login.microsoftonline.com)
# --------------------------------------------------------------------------- #
def _pick_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_callback_server(port: str, result_holder: Dict[str, Any]) -> Any:
    """HTTP server kecil untuk menangani OAuth callback di http://localhost:PORT/callback."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import urllib.parse

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/callback":
                qs = urllib.parse.parse_qs(parsed.query)
                if "code" in qs:
                    result_holder["code"] = qs["code"][0]
                    result_holder["state"] = qs.get("state", [""])[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Login Berhasil</h2>"
                                     b"<p>Anda bisa menutup jendela ini dan kembali ke aplikasi.</p>"
                                     b"<script>window.close()</script></body></html>")
                elif "error" in qs:
                    result_holder["error"] = qs["error"][0]
                    result_holder["error_description"] = qs.get("error_description", [""])[0]
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h2>Login Gagal</h2>"
                                     b"<p>%s</p></body></html>" % qs.get("error_description", [""])[0].encode())
            else:
                self.send_response(404)
                self.end_headers()
        def log_message(self, fmt, *args):
            pass

    server = HTTPServer(("127.0.0.1", int(port)), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def login_with_oauth(email: str = "", password: str = "",
                     client_id: str = "", scope: str = MS_SCOPE,
                     session: Optional[requests.Session] = None,
                     headless: bool = True) -> MMCAccount:
    """
    Login Microsoft resmi via Microsoft.com (OAuth2 authorization code flow).

    - Jika headless=True: coba device code flow (tidak butuh browser interaktif).
    - Jika headless=False: buka browser ke halaman login Microsoft, tangani callback
      di http://localhost:PORT/callback, tukar code dengan access_token + refresh_token.
    """
    s = session or _make_session()
    cid = (client_id or "").strip() or BUILTIN_CLIENT_ID
    result: Dict[str, Any] = {}

    if not headless:
        # Alur browser interaktif via Microsoft.com
        port = _pick_free_port()
        redirect = f"http://127.0.0.1:{port}/callback"
        state = os.urandom(16).hex()
        server = _start_callback_server(port, result)
        try:
            auth_url = (f"{AUTHORIZE_URL}?client_id={cid}"
                        f"&response_type=code&redirect_uri={redirect}"
                        f"&scope={requests.utils.quote(scope)}"
                        f"&state={state}&prompt=select_account")
            if email:
                auth_url += f"&login_hint={requests.utils.quote(email)}"
            logger.info("Membuka browser login Microsoft: %s", auth_url)
            webbrowser.open(auth_url)
            # Tunggu callback (maksimal 5 menit)
            deadline = time.time() + 300
            while time.time() < deadline:
                if result.get("code") or result.get("error"):
                    break
                time.sleep(0.5)
        finally:
            server.shutdown()

        if result.get("error"):
            raise MMCLoginError(f"Microsoft OAuth error: {result.get('error')} "
                                f"{result.get('error_description','')}")
        code = result.get("code", "")
        if not code:
            raise MMCLoginError("Tidak menerima authorization code dari Microsoft")
        # Tukar code
        try:
            tr = s.post(TOKEN_URL, data={
                "client_id": cid,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "scope": scope,
            }, timeout=30)
        except Exception as exc:  # noqa: BLE001
            raise MMCLoginError(f"Token exchange gagal: {str(exc)[:100]}")
        try:
            data = tr.json()
        except ValueError:
            raise MMCLoginError(f"Token exchange invalid: HTTP {tr.status_code}")
        if "access_token" not in data:
            err = data.get("error", "unknown")
            desc = (data.get("error_description", "") or "")[:100]
            raise MMCLoginError(f"Token exchange gagal: {err} {desc}".strip())
    else:
        # Device code flow (headless) via Microsoft.com
        try:
            dc = s.post(DEVICE_CODE_URL, data={
                "client_id": cid,
                "scope": scope,
            }, timeout=30)
        except Exception as exc:  # noqa: BLE001
            raise MMCLoginError(f"Device code request gagal: {str(exc)[:100]}")
        try:
            dc_data = dc.json()
        except ValueError:
            raise MMCLoginError(f"Device code invalid: HTTP {dc.status_code}")
        if "error" in dc_data:
            raise MMCLoginError(f"Device code error: {dc_data.get('error_description', dc_data['error'])}")

        user_code = dc_data["user_code"]
        device_code = dc_data["device_code"]
        verification_uri = dc_data.get("verification_uri", "https://microsoft.com/devicelogin")
        interval = int(dc_data.get("interval", 5))
        expires_in = int(dc_data.get("expires_in", 900))

        logger.info("Device code: %s — buka %s", user_code, verification_uri)
        try:
            webbrowser.open(verification_uri)
        except Exception:  # noqa: BLE001
            pass

        deadline = time.time() + expires_in
        while time.time() < deadline:
            try:
                tr = s.post(TOKEN_URL, data={
                    "client_id": cid,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                }, timeout=30)
            except Exception as exc:  # noqa: BLE001
                raise MMCLoginError(f"Token poll gagal: {str(exc)[:100]}")
            try:
                data = tr.json()
            except ValueError:
                time.sleep(interval)
                continue
            if "access_token" in data:
                break
            err = data.get("error", "")
            if err in ("authorization_pending",):
                time.sleep(interval)
                continue
            if err in ("slow_down",):
                time.sleep(interval + 5)
                continue
            if err in ("expired_token",):
                raise MMCLoginError("Device code expired — buat kode baru")
            raise MMCLoginError(f"Device code gagal: {err} {data.get('error_description','')}")
        else:
            raise MMCLoginError("Device code timeout — silakan coba lagi")
        # data sudah berisi access_token / refresh_token

    # Simpan token Microsoft
    ms_access_token = data["access_token"]
    ms_refresh_token = data.get("refresh_token", "")
    ms_expires_in = int(data.get("expires_in", 3600))
    ms_token_expiry = time.time() + ms_expires_in - 60

    acc = MMCAccount(email=email, client_id=cid,
                     refresh_token=ms_refresh_token,
                     ms_access_token=ms_access_token,
                     ms_token_expiry=ms_token_expiry,
                     token_type="ms_oauth")

    # Konversi MS access token -> Minecraft access token via XBL/XSTS
    try:
        mc = _mc_token_from_ms(ms_access_token, s)
    except MMCLoginError as exc:
        raise MMCLoginError(f"Gagal mengonversi token Microsoft ke Minecraft: {exc}")

    acc.mc_access_token = mc["access_token"]
    acc.mc_token_expiry = _jwt_exp(acc.mc_access_token) or \
        (time.time() + mc.get("expires_in", 86400) - 600)

    # Verifikasi profil Minecraft (429 tidak dianggap invalid)
    try:
        verify_mc_token(acc, s)
        acc.token_verified = True
    except MMCLoginError:
        acc.token_verified = False
        logger.warning("%s: profil tidak bisa diverifikasi — token tetap disimpan", acc.label())

    logger.info("%s: login Microsoft OAuth sukses", acc.label())
    return acc


# --------------------------------------------------------------------------- #
# Token login
# --------------------------------------------------------------------------- #
def refresh_account_tokens(acc: MMCAccount, session: Optional[requests.Session] = None) -> bool:
    """Refresh Microsoft access token via refresh_token (OAuth2)."""
    s = session or _make_session()
    acc.client_id = acc.client_id or BUILTIN_CLIENT_ID
    if not acc.refresh_token:
        raise MMCLoginError(f"{acc.label()}: tidak ada refresh token "
                            f"(tambahkan ulang akun via login Microsoft)")
    try:
        r = s.post(TOKEN_URL, data={
            "client_id": acc.client_id,
            "grant_type": "refresh_token",
            "refresh_token": acc.refresh_token,
            "scope": MS_SCOPE,
        }, timeout=30)
        data = r.json()
        if "access_token" not in data:
            err = data.get("error", "unknown")
            if err == "invalid_grant":
                raise MMCLoginError(f"{acc.label()}: refresh token invalid/expired "
                                    f"— login ulang via Microsoft OAuth")
            raise MMCLoginError(f"{acc.label()}: refresh gagal: {err}")
        acc.refresh_token = data.get("refresh_token", acc.refresh_token)
        ms_access_token = data["access_token"]
        acc.ms_access_token = ms_access_token
        acc.ms_token_expiry = time.time() + int(data.get("expires_in", 3600)) - 60
        # Konversi ke Minecraft token
        mc = _mc_token_from_ms(ms_access_token, s)
        acc.mc_access_token = mc["access_token"]
        acc.mc_token_expiry = _jwt_exp(acc.mc_access_token) or \
            (time.time() + mc.get("expires_in", 86400) - 600)
        acc.enabled = True
        logger.info("%s: token refreshed (OAuth)", acc.label())
        return True
    except MMCLoginError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Token refresh failed for %s: %s", acc.label(), exc)
        raise MMCLoginError(f"{acc.label()}: refresh exception {str(exc)[:80]}")


def ensure_valid_token(acc: MMCAccount, session: Optional[requests.Session] = None) -> bool:
    if acc.is_token_valid():
        return True
    if acc.refresh_token:
        try:
            return refresh_account_tokens(acc, session)
        except MMCLoginError:
            return False
    return False


def login_with_refresh_token(ms_refresh_token: str, client_id: str = "",
                             email: str = "",
                             session: Optional[requests.Session] = None) -> MMCAccount:
    rt = _clean_token(ms_refresh_token)
    if not rt:
        raise MMCLoginError("Refresh token kosong")
    acc = MMCAccount(email=email, client_id=(client_id or "").strip() or BUILTIN_CLIENT_ID,
                     refresh_token=rt, token_type="ms_refresh")
    s = session or _make_session()
    refresh_account_tokens(acc, s)
    try:
        verify_mc_token(acc, s)
        acc.token_verified = True
    except MMCLoginError:
        acc.token_verified = False
    return acc


def login_with_ms_token(ms_token: str, email: str = "",
                        session: Optional[requests.Session] = None) -> MMCAccount:
    """Token Microsoft: M.C.. = refresh token, lainnya = access token (d= XBL)."""
    tok = _clean_token(ms_token)
    if not tok:
        raise MMCLoginError("Token kosong")
    s = session or _make_session()
    if tok.startswith("M.C"):
        return login_with_refresh_token(tok, "", email, s)
    acc = MMCAccount(email=email, client_id=BUILTIN_CLIENT_ID, token_type="ms_access",
                     ms_access_token=tok, ms_token_expiry=time.time() + 86400 - 600)
    try:
        mc = _mc_token_from_ms(tok, s)
    except MMCLoginError as exc:
        raise MMCLoginError(f"MS access token ditolak Xbox Live: {exc}")
    acc.mc_access_token = mc["access_token"]
    acc.mc_token_expiry = _jwt_exp(acc.mc_access_token) or (time.time() + 86400 - 600)
    try:
        verify_mc_token(acc, s)
        acc.token_verified = True
    except MMCLoginError:
        acc.token_verified = False
    return acc


def login_with_mc_token(mc_access_token: str, email: str = "",
                        session: Optional[requests.Session] = None) -> MMCAccount:
    """Minecraft access token (eyJ...). Verifikasi KETAT — invalid = error jelas."""
    tok = _clean_token(mc_access_token)
    if not tok:
        raise MMCLoginError("Token kosong")

    s = session or _make_session()
    acc = MMCAccount(email=email, mc_access_token=tok, token_type="mc_token")

    if not tok.startswith("eyJ"):
        raise MMCLoginError("Format token tidak dikenal (harus eyJ… / M.C… / M.R…)")

    exp = _jwt_exp(tok)
    try:
        verify_mc_token(acc, s)
        acc.token_verified = True
        acc.mc_token_expiry = exp or (time.time() + 3600 * 23)
        return acc
    except MMCLoginError as exc:
        msg = str(exc)
        if "429" in msg:
            # rate limit pada profil BUKAN bukti token invalid — terima saja
            logger.warning("%s: profil tidak bisa diverifikasi (429) — token diterima tanpa verifikasi",
                           email or "token")
            acc.token_verified = False
            acc.mc_token_expiry = exp or (time.time() + 3600 * 2)
            return acc
        if "401" in msg:
            # mungkin ini MS access token, bukan MC token — coba rantai XBL
            try:
                return login_with_ms_token(tok, email, s)
            except MMCLoginError:
                pass
        raise MMCLoginError(f"Invalid Minecraft token: {msg}")


# --------------------------------------------------------------------------- #
# Verifikasi profil
# --------------------------------------------------------------------------- #
def verify_mc_token(acc: MMCAccount, session: Optional[requests.Session] = None) -> str:
    s = session or _make_session()
    r = s.get(MC_PROFILE, headers={"Authorization": f"Bearer {acc.mc_access_token}"},
              timeout=30)
    if r.status_code == 429:
        # rate limit bukan berarti token invalid — retry sekali, lalu terima
        time.sleep(3.0)
        r = s.get(MC_PROFILE, headers={"Authorization": f"Bearer {acc.mc_access_token}"},
                  timeout=30)
        if r.status_code == 429:
            logger.warning("%s: verifikasi profil kena 429 — token dianggap OK", acc.label())
            return ""
    if r.status_code == 401:
        raise MMCLoginError("Token invalid or expired (401)")
    if r.status_code != 200:
        raise MMCLoginError(f"Profile check failed: HTTP {r.status_code}")
    try:
        data = r.json()
        acc.profile_name = data.get("name", "")
        return acc.profile_name
    except ValueError:
        raise MMCLoginError("Invalid profile response")


# --------------------------------------------------------------------------- #
# Info name change
# --------------------------------------------------------------------------- #
def get_name_change_info(acc: MMCAccount, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    s = session or _make_session()
    if not ensure_valid_token(acc, s):
        return {}
    try:
        r = s.get(MC_NAME_CHANGE_INFO,
                  headers={"Authorization": f"Bearer {acc.mc_access_token}"}, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return {}


def _name_availability_status(acc: MMCAccount, name: str,
                              session: Optional[requests.Session] = None) -> str:
    """'AVAILABLE' | 'TAKEN' | 'RATE_LIMITED' | 'ERROR' (endpoint 20 req/5 menit per akun)."""
    s = session or _make_session()
    if not ensure_valid_token(acc, s):
        return "ERROR"
    try:
        r = s.get(f"{MC_NAME_AVAILABILITY}/{name}",
                  headers={"Authorization": f"Bearer {acc.mc_access_token}"}, timeout=30)
        if r.status_code == 429:
            return "RATE_LIMITED"
        if r.status_code != 200:
            return "ERROR"
        return (r.json().get("status", "") or "").upper() or "ERROR"
    except Exception:  # noqa: BLE001
        return "ERROR"


def check_name_available(acc: MMCAccount, name: str, session: Optional[requests.Session] = None) -> bool:
    return _name_availability_status(acc, name, session) == "AVAILABLE"


# --------------------------------------------------------------------------- #
# Claim
# --------------------------------------------------------------------------- #
def claim_name(acc: MMCAccount, name: str, session: Optional[requests.Session] = None) -> ClaimResult:
    s = session or _make_session()
    if not acc.is_valid():
        return ClaimResult(name, acc, ClaimStatus.TOKEN_INVALID, "Account invalid/cooldown")

    if not ensure_valid_token(acc, s):
        acc.mark_failed()
        return ClaimResult(name, acc, ClaimStatus.TOKEN_INVALID,
                           "Token refresh gagal — akun perlu login ulang via Microsoft OAuth")

    headers = {"Authorization": f"Bearer {acc.mc_access_token}",
               "Content-Type": "application/json"}

    try:
        pre = _name_availability_status(acc, name, s)
        if pre == "TAKEN":
            return ClaimResult(name, acc, ClaimStatus.NAME_TAKEN, "Pre-check: unavailable")
        if pre == "RATE_LIMITED":
            return ClaimResult(name, acc, ClaimStatus.RATE_LIMITED, "429 pada pre-check")

        nc_info = get_name_change_info(acc, s)
        if nc_info.get("changeAllowedAt"):
            try:
                allowed_at = datetime.fromisoformat(
                    nc_info["changeAllowedAt"].replace("Z", "+00:00"))
                if allowed_at.timestamp() > time.time():
                    remaining = int(allowed_at.timestamp() - time.time())
                    return ClaimResult(name, acc, ClaimStatus.NOT_ELIGIBLE,
                                       f"Cooldown: {remaining // 3600}h "
                                       f"{(remaining % 3600) // 60}m remaining")
            except Exception:  # noqa: BLE001
                pass

        time.sleep(0.4)
        r = s.post(MC_PROFILE, headers=headers, json={"profileName": name}, timeout=30)

        if r.status_code == 200:
            acc.mark_success()
            try:
                prof = s.get(MC_PROFILE, headers=headers, timeout=30)
                if prof.status_code == 200:
                    actual = prof.json().get("name", name)
                    return ClaimResult(name, acc, ClaimStatus.SUCCESS,
                                       f"Claimed as '{actual}'")
            except Exception:  # noqa: BLE001
                pass
            return ClaimResult(name, acc, ClaimStatus.SUCCESS, "Successfully claimed")
        if r.status_code == 400:
            acc.mark_failed()
            return ClaimResult(name, acc, ClaimStatus.NAME_TAKEN, "400: Taken or invalid")
        if r.status_code == 403:
            acc.mark_failed()
            detail_status = ""
            try:
                detail_status = str((r.json().get("detail") or {}).get("status", "")).upper()
            except Exception:  # noqa: BLE001
                pass
            if detail_status == "DUPLICATE":
                return ClaimResult(name, acc, ClaimStatus.NAME_TAKEN, "403: DUPLICATE")
            try:
                nc_info = get_name_change_info(acc, s)
                if nc_info.get("changeAllowedAt"):
                    return ClaimResult(name, acc, ClaimStatus.NOT_ELIGIBLE,
                                       "403: name change cooldown aktif")
            except Exception:  # noqa: BLE001
                pass
            return ClaimResult(name, acc, ClaimStatus.NOT_ELIGIBLE,
                               "403: Not eligible/cooldown")
        if r.status_code == 401:
            acc.mark_failed()
            return ClaimResult(name, acc, ClaimStatus.TOKEN_INVALID,
                               "401: Token invalid — refresh atau login ulang via Microsoft OAuth")
        if r.status_code == 429:
            acc.mark_failed()
            return ClaimResult(name, acc, ClaimStatus.RATE_LIMITED,
                               "429: Rate limited (coba akun lain / tunggu)")
        acc.mark_failed()
        return ClaimResult(name, acc, ClaimStatus.ERROR,
                           f"HTTP {r.status_code}: {r.text[:50]}")

    except Exception as e:
        acc.mark_failed()
        return ClaimResult(name, acc, ClaimStatus.ERROR, f"Exception: {str(e)[:100]}")


class SmartClaimQueue:
    def __init__(self, accounts: List[MMCAccount]):
        self.accounts = accounts
        self._lock = threading.Lock()
        self._index = 0

    def get_next_account(self) -> Optional[MMCAccount]:
        with self._lock:
            valid_accounts = [a for a in self.accounts if a.is_valid() and a.is_token_valid()]
            if not valid_accounts:
                for a in self.accounts:
                    if a.enabled and a.refresh_token and a.cooldown_until < time.time():
                        try:
                            ensure_valid_token(a)
                            if a.is_token_valid():
                                valid_accounts.append(a)
                        except Exception:  # noqa: BLE001
                            pass
            if not valid_accounts:
                return None
            acc = valid_accounts[self._index % len(valid_accounts)]
            self._index += 1
            return acc

    def get_account_count(self) -> int:
        return len([a for a in self.accounts if a.is_valid()])


if __name__ == "__main__":
    print("Use GUI (varin_sniper.py) for authentication")
