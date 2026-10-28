"""
blocklist.py — nama yang harus dilewati generator dan antrian.

Dipakai BERSAMA oleh aplikasi desktop (`generator.py`, `controller.py`)
dan versi web (`webapp/server.py`), jadi perilakunya selalu sama.

Dua sumber:

1. Daftar 3NAME — https://3name.xyz/list
   Daftar publik 3-letter username yang sedang dipantau komunitas
   (Dropping + Dropping Soon). Snapshot tertanam supaya tetap berfungsi
   offline, lalu disegarkan di background kalau ada jaringan.

2. Kata inappropriate
   Kata kotor/sensor yang tidak boleh muncul di hasil generate. Dicocokkan
   setelah normalisasi leet, jadi `4ss`, `_ass`, dan `n1gga` ikut terdeteksi.
   Aturan per panjang kata supaya nama biasa tidak ikut kena:
     * <= 3 karakter  -> cocok persis        (ass, sex, kkk)
     * >= 4 karakter  -> cocok di awal nama  (fuck..., nazi...)
     * >= 5 karakter  -> cocok di mana saja  (...bitch..., ...pussy...)
   Kata yang bisa menjadi awal kata biasa (milf -> milford, spic -> spice,
   anal -> analog) sengaja hanya dicocokkan persis.

API:
    is_blocked(name)        -> bool
    blocked_reason(name)    -> "3name" | "inappropriate" | ""
    filter_names(names)     -> (bersih, jumlah_diblokir)
    three_name_count()      -> int
    start_refresh()         -> segarkan daftar 3NAME di background
"""
from __future__ import annotations

import re
import threading
import time
from typing import Iterable, List, Tuple

THREE_NAME_LIST_URL = "https://3name.xyz/list"
_REFRESH_INTERVAL = 6 * 3600          # detik antar penyegaran
_FETCH_TIMEOUT = 8.0

# Snapshot https://3name.xyz/list (Dropping 2 + Dropping Soon 22).
THREE_NAME_SNAPSHOT = frozenset("""
    2_b 2hn 49m 6fq 6x_ 9zx _sg die dxw ejc gjv h03
    ig2 ix9 qpy qvx r94 s4a ukl uwx vel vpo yi2 zs7
""".split())

# --- kata inappropriate ---------------------------------------------------- #

# <= 3 karakter: hanya cocok persis (agar "bass"/"asset" tidak kena).
INAPPROPRIATE_EXACT_3 = frozenset({
    "ass", "sex", "cum", "fag", "nig", "kkk", "tit", "hoe", "xxx", "kys",
    "nzi", "fck", "sht", "dck", "dic", "pns", "vgn", "gyp", "fap", "nip",
    "vag", "jiz", "sxe",
})

# >= 4 karakter yang TIDAK boleh dicocokkan sebagian (awal kata biasa).
INAPPROPRIATE_EXACT_4 = frozenset({
    "milf", "spic", "anal",
})

# >= 4 karakter: blokir kalau menjadi AWALAN nama (fuckboy, nazi4, shithead).
INAPPROPRIATE_PREFIX = frozenset({
    "fuck", "shit", "cunt", "cock", "dick", "nazi", "rape", "porn", "slut",
    "tits", "titt", "boob", "anus", "jizz", "horny", "fagot", "nsfw", "isis",
    "kike", "gook", "clit", "twat", "sext", "wank", "pedo", "bdsm",
})

# >= 5 karakter: blokir di posisi mana pun (bitch, pussy, hitler).
INAPPROPRIATE_CONTAINS = frozenset({
    "bitch", "whore", "penis", "vagin", "vulva", "nigg", "fagg", "semen",
    "dildo", "hentai", "retard", "chink", "hitler", "orgasm", "sperm",
    "blowjob", "slutty", "pussy", "gspot", "incest", "rapist", "faggit",
    "nymph", "testic",
})

_LEET = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
    "@": "a", "$": "s", "!": "i", "|": "i",
})

_RE_LIST_LINK = re.compile(r"/name/([a-z0-9_]{3})", re.IGNORECASE)

_lock = threading.Lock()
_three_names = set(THREE_NAME_SNAPSHOT)
_refresh_started = False
_last_refresh = 0.0
_last_refresh_ok = 0


def normalize(name: str) -> str:
    """Huruf kecil + leet (4->a, 1->i) + buang '_' -> bentuk untuk pencocokan."""
    return (name or "").strip().lower().translate(_LEET).replace("_", "")


def three_name_count() -> int:
    with _lock:
        return len(_three_names)


def is_three_name(name: str) -> bool:
    if not name:
        return False
    with _lock:
        return name.strip().lower() in _three_names


def is_inappropriate(name: str) -> bool:
    if not name:
        return False
    norm = normalize(name)
    if not norm:
        return False
    if norm in INAPPROPRIATE_EXACT_3 or norm in INAPPROPRIATE_EXACT_4:
        return True
    if len(norm) >= 4 and norm[:4] in INAPPROPRIATE_PREFIX:
        return True
    if len(norm) >= 5 and any(w in norm for w in INAPPROPRIATE_CONTAINS):
        return True
    return False


def blocked_reason(name: str) -> str:
    """"3name" | "inappropriate" | "" — alasan sebuah nama ditolak."""
    if is_three_name(name):
        return "3name"
    if is_inappropriate(name):
        return "inappropriate"
    return ""


def is_blocked(name: str) -> bool:
    return bool(blocked_reason(name))


def filter_names(names: Iterable[str]) -> Tuple[List[str], int]:
    """Pisahkan nama bersih dari nama yang diblokir. Return (bersih, jumlah_blokir)."""
    clean: List[str] = []
    blocked = 0
    for name in names:
        if blocked_reason(name):
            blocked += 1
        else:
            clean.append(name)
    return clean, blocked


# --- penyegaran background ------------------------------------------------- #
def refresh_once(timeout: float = _FETCH_TIMEOUT) -> int:
    """Ambil daftar terbaru dari 3name.xyz/list. Return jumlah nama yang ditemukan.

    Gagal/jaringan mati = 0, snapshot lama tetap dipakai. Daftar lama tidak
    pernah dihapus (nama yang sudah keluar daftar pun tetap dilewati).
    """
    global _last_refresh, _last_refresh_ok
    _last_refresh = time.time()
    try:
        import requests
        resp = requests.get(THREE_NAME_LIST_URL, timeout=timeout, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/126.0.0.0 Safari/537.36"),
        })
        if resp.status_code != 200:
            return 0
        # regex hanya menangkap tiga karakter yang valid untuk username 3L
        found = {m.group(1).lower() for m in _RE_LIST_LINK.finditer(resp.text)}
        if not found:
            return 0
        with _lock:
            _three_names.update(found)
            _last_refresh_ok = time.time()
        return len(found)
    except Exception:                            # noqa: BLE001
        return 0


def start_refresh() -> None:
    """Segarkan daftar 3NAME di background (sekali, daemon, tidak memblokir)."""
    global _refresh_started
    with _lock:
        if _refresh_started:
            return
        _refresh_started = True

    def _loop() -> None:
        while True:
            refresh_once()
            time.sleep(_REFRESH_INTERVAL)

    threading.Thread(target=_loop, name="3name-refresh", daemon=True).start()


if __name__ == "__main__":
    print(f"snapshot 3NAME : {len(THREE_NAME_SNAPSHOT)} nama")
    print(f"live 3NAME     : {three_name_count()} nama")
    for sample in ("s4a", "_sg", "9zx", "zbx", "ass", "4ss", "_a_s_s",
                   "fuck1", "n1gga", "milford", "bass", "grape"):
        print(f"  {sample:10s} -> {blocked_reason(sample) or 'lolos'}")
