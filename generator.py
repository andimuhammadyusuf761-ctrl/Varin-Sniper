"""Username generator untuk 3-char dan 4-char combos dengan priority scoring."""
import itertools
import random
import string
from typing import Dict, List, Optional, Set, Tuple

# Nama dari daftar 3name.xyz/list dan nama inappropriate tidak pernah
# dihasilkan (lihat blocklist.py untuk aturan dan daftarnya).
from blocklist import is_blocked

ALLOWED = string.ascii_lowercase + string.digits + "_"
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits

def random_combo(length: int) -> str:
    return "".join(random.choice(ALLOWED) for _ in range(length))

def enumerate_full(length: int, chars: str = LOWERCASE) -> List[str]:
    return ["".join(t) for t in itertools.product(chars, repeat=length)]

def _calculate_priority_score(name: str) -> int:
    """Calculate priority score - higher = more desirable"""
    score = 0
    length = len(name)

    # All same char (aaa, bbb) - highest priority
    if len(set(name)) == 1:
        score += 1000

    # Very few unique chars
    elif len(set(name)) == 2:
        score += 500
        # Check patterns
        if name[0] == name[1] or name[1] == name[2] or (length == 4 and (name[2] == name[3] or name[0] == name[2])):
            score += 100

    # Has repeated chars
    for i in range(len(name) - 1):
        if name[i] == name[i + 1]:
            score += 50

    # All letters (no numbers/underscore) slightly preferred
    if all(c.islower() for c in name):
        score += 30

    # Palindromes
    if name == name[::-1]:
        score += 80

    # Common patterns
    if length == 3:
        # x_x style less common but check
        if name[0] != name[1] and name[1] != name[2] and name[0] != name[2]:
            if any(c in 'aeiou' for c in name):  # has vowel
                score += 20
    elif length == 4:
        if name[0:2] == name[2:4]:  # abab, aabb
            score += 150
        elif name[0] == name[1] and name[2] == name[3]:  # aabb
            score += 200
        elif name[0] == name[2] and name[1] == name[3]:  # abab
            score += 180

    return score

def enumerate_ordered(length: int, use_all_chars: bool = False) -> List[str]:
    """Full enumeration ordered by priority"""
    chars = LOWERCASE if not use_all_chars else ALLOWED
    names = enumerate_full(length, chars)
    # daftar 3name.xyz/list & nama inappropriate tidak ikut dienumerasi penuh
    names = [n for n in names if not is_blocked(n)]
    # Sort by priority score desc, then alphabetically
    names.sort(key=lambda s: (-_calculate_priority_score(s), s))
    return names

def generate_random(count: int, length: int, allowed_chars: str = None,
                    exclude: Optional[Set[str]] = None) -> List[str]:
    if allowed_chars is None:
        allowed_chars = ALLOWED
    excluded = exclude or frozenset()
    seen: Set[str] = set()
    out: List[str] = []
    max_attempts = count * 100 + len(excluded) * 4
    attempts = 0
    while len(out) < count and attempts < max_attempts:
        name = "".join(random.choice(allowed_chars) for _ in range(length))
        if name not in seen and name not in excluded and 3 <= len(name) <= 16 and not is_blocked(name):
            seen.add(name)
            out.append(name)
        attempts += 1
    return out

def _make_underscore3():
    """Generate a random 3-char name with exactly one underscore."""
    slot = random.randrange(3)
    rest = "".join(random.choice(LOWERCASE) for _ in range(2))
    return rest[:slot] + "_" + rest[slot:]

def _make_underscore4():
    """Generate a random 4-char name with exactly one underscore."""
    slot = random.randrange(4)
    rest = "".join(random.choice(LOWERCASE) for _ in range(3))
    return rest[:slot] + "_" + rest[slot:]

def generate_smart_random(count: int, length: int,
                          allow_vowels: bool = True,
                          underscore: bool = False,
                          exclude: Optional[Set[str]] = None) -> List[str]:
    """Generate with higher chance for good patterns"""
    excluded = exclude or frozenset()
    seen: Set[str] = set()
    out: List[str] = []
    strategies_used = False
    letters = [c for c in (LOWERCASE if allow_vowels else LOWERCASE.replace("aeiou", "")) or LOWERCASE]
    weights = [max(0.05, LETTER_RARITY.get(c, 6.0)) ** 2 for c in letters]

    # Weight strategies based on length and underscore
    if length == 3:
        if underscore:
            # Balanced 3L: names with exactly one underscore (h_d, z_x, q_b)
            strategies = [
                (_make_underscore3, 0.3),  # one underscore
            ]
            strategy_weight_total = 0.3
        else:
            strategies = None
            strategy_weight_total = 0
    elif length == 4:
        if underscore:
            # 4L with one underscore: e.g., abc_d, x_y_z, etc.
            strategies = [
                (_make_underscore4, 0.3),  # one underscore
            ]
            strategy_weight_total = 0.3
        else:
            strategies = None
            strategy_weight_total = 0

    attempts = 0
    while len(out) < count and attempts < count * 200 + len(excluded) * 4:
        # Decide whether to use strategy or random combo
        if strategies and random.random() * (strategy_weight_total + 1.0) < strategy_weight_total:
            # Pick strategy
            r = random.random() * strategy_weight_total
            cum = 0
            for func, prob in strategies:
                cum += prob
                if r <= cum:
                    name = func()
                    strategies_used = True
                    break
            else:
                name = random_combo(length)
                strategies_used = False
        else:
            name = random_combo(length)
            strategies_used = False

        # When underscore mode is on, ensure exactly one underscore
        if underscore:
            if strategies_used:
                # Strategy already produces name with one underscore, verify/fix
                underscore_count = name.count('_')
                if underscore_count == 0:
                    # No underscore added by strategy - add one
                    slot = random.randrange(length)
                    name = name[:slot] + "_" + name[slot+1:]
                elif underscore_count > 1:
                    # Too many underscores - fix to exactly one
                    # Keep the first underscore and remove others
                    parts = name.split('_')
                    name = parts[0] + "_" + "".join(parts[1:])
            else:
                # Non-strategy path: add exactly one underscore
                slot = random.randrange(length)
                name = name[:slot] + "_" + name[slot+1:]

        if name not in seen and name not in excluded and all(c.isalnum() or c == '_' for c in name) and not is_blocked(name):
            seen.add(name)
            out.append((name, _calculate_priority_score(name)))
        attempts += 1

    # Sort by priority
    out.sort(key=lambda x: -x[1])
    return [n[0] for n in out]

def _underscore_combo(length: int, chars: str) -> str:
    """Generate a random name with exactly one underscore."""
    slot = random.randrange(length)
    rest = "".join(random.choice(chars) for _ in range(length - 1))
    return rest[:slot] + "_" + rest[slot:]

# --------------------------------------------------------------------------- #
# Kelangkaan (rarity) — dasar generate_rare()
# --------------------------------------------------------------------------- #

VOWELS = "aeiou"
_VOWEL_SET = frozenset(VOWELS)

# Bobot per huruf: makin besar = makin jarang dipakai orang.
LETTER_RARITY: Dict[str, float] = {
    "e": 1.8, "a": 2.0, "o": 2.4, "t": 2.6, "i": 2.8, "s": 3.2, "n": 3.4,
    "u": 3.5, "r": 3.8, "l": 4.2, "d": 4.5, "h": 4.6, "c": 5.0, "m": 5.5,
    "b": 6.5, "p": 6.6, "g": 6.8, "y": 7.0, "f": 7.5, "w": 8.0, "k": 9.0,
    "v": 9.5, "j": 10.5, "x": 11.0, "z": 11.5, "q": 12.0,
    "_": 8.4,          # underscore: pemisah jarang dipakai di nama OG
}

# Pasangan/triple huruf yang membuat nama terasa "biasa" di bahasa Inggris.
COMMON_BIGRAMS = frozenset("""
    th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng
    se ha as ou io le ve co me de hi ri ro ic ne ea ra ce li ch ll be ma si
    om ur ca el ta la ns di fo ho pe ec pr no ct us ac ot il tr ly nc et ut
    ss so rs un lo wa ge ie wh ee wi em ad ol rt po we na ul ni ts mo ow pa
    im mi ai sh ir su id osiv ia am fi ci vi pl ig tu ev ld ry
""".split())

COMMON_TRIGRAMS = frozenset("""
    the and ing his tha ere for ent ion ter was you ith ver all wit
    thi tio nde has men est ers eve sti rin not are but oul
    sch chr str thr spr shr spl scr sq tch ght nth rth
""".split())

# Pola yang justru sering dipakai orang lain — bukan "langka".
COMMON_SEQUENCES = frozenset({
    "abc", "xyz", "qwe", "asd", "zxc", "qaz", "wsx", "edc"
})

# Nama nyata/sensitif: lebih baik dilewati (pasti ditolak Minecraft).
BLOCKED_NAMES = frozenset({
    "ass", "cum", "gay", "sex", "fag", "nig", "dck", "fck", "sht", "wtf",
    "tit", "kkk", "nzi", "dic", "pns", "vgn", "gyp", "the", "and",
    "you", "for", "are", "but", "not", "all", "can", "had", "her", "was",
    "one", "our", "out", "day", "get", "has", "him", "how", "man", "new", "now",
    "old", "see", "two", "way", "who", "boy", "did", "its", "let", "put",
    "say", "she", "too", "use", "yes", "yet", "own", "off", "end", "few",
})

def rarity_score(name: str) -> float:
    """Skor kelangkaan: makin tinggi = makin jarang dijumpai orang.

    Heuristik, bukan data pemakaian nyata:
      * huruf jarang (q, x, z, j, v, k) menaikkan skor;
      * huruf berbeda, tanpa vokal, dan tanpa pasangan huruf umum menaikkan;
      * pola berulang (aaa, aba), urutan papan ketik (qwe/abc), dan kata
        nyata/terblokir menurunkannya.
    """
    if not name:
        return 0.0
    low = name.lower()
    n = len(low)

    weights = [LETTER_RARITY.get(c, 6.0) for c in low]
    score = (sum(weights) / n - 1.5) * 1.5

    score += 3.0 * (len(set(low)) - 1)          # makin banyak huruf berbeda

    vowels = sum(1 for c in low if c in _VOWEL_SET)
    if vowels == 0:
        score += 4.0
    elif vowels == 1:
        score += 1.5
    else:
        score -= 2.0 * (vowels - 1)

    bigrams = sum(1 for i in range(n - 1) if low[i:i + 2] in COMMON_BIGRAMS)
    trigrams = sum(1 for i in range(n - 2) if low[i:i + 3] in COMMON_TRIGRAMS)
    score -= 3.0 * bigrams + 5.0 * trigrams

    if low in COMMON_SEQUENCES:
        score -= 12.0
    if low in BLOCKED_NAMES:
        score -= 100.0
    return round(score, 3)


_POOL_LIMIT = 60000
_POOL_CACHE: Dict[Tuple[int, bool, str, bool], Tuple[str, ...]] = {}

def _underscore_combos(length: int, chars: str) -> List[str]:
    """Semua kombinasi `length` karakter dengan tepat satu '_'."""
    out: List[str] = []
    for slot in range(length):
        for rest in itertools.product(chars, repeat=length - 1):
            out.append("".join(rest[:slot]) + "_" + "".join(rest[slot:]))
    return out

def rare_pool(length: int = 3, allow_vowels: bool = True,
              chars: str = LOWERCASE,
              underscore: bool = False) -> Tuple[str, ...]:
    """Semua kombinasi `length` terurut dari yang paling langka.

    `underscore=True` membatasi pool ke nama dengan tepat satu '_'
    (dipakai mode Balanced 3L: h_d, z_x, q_b).

    Kosong kalau ruang kombinasinya terlalu besar (mis. 4L = 456.976
    kombinasi); pemanggil memakai sampling berbobot sebagai gantinya.
    """
    key = (int(length), bool(allow_vowels), chars, bool(underscore))
    cached = _POOL_CACHE.get(key)
    if cached is not None:
        return cached

    size = int(length)
    space = size * len(chars) ** (size - 1) if underscore else len(chars) ** size
    if space > _POOL_LIMIT:
        return ()

    if underscore:
        combos = _underscore_combos(size, chars)
    else:
        combos = ["".join(t) for t in itertools.product(chars, repeat=size)]
    if not allow_vowels:
        combos = [c for c in combos if not (_VOWEL_SET & set(c))]
    combos = [c for c in combos if c not in BLOCKED_NAMES and not is_blocked(c)]
    combos.sort(key=lambda s: (-rarity_score(s), s))

    pool = tuple(combos)
    _POOL_CACHE[key] = pool
    return pool

def _sample_rare(count: int, length: int, allow_vowels: bool, chars: str,
                 rng: random.Random, exclude: Optional[Set[str]] = None,
                 underscore: bool = False, band: float = 0.45) -> List[str]:
    """Sampling berbobot untuk ruang kombinasi besar (4L ke atas).

    Oversampling dulu, urutkan, baru ambil dari porsi `band` teratas — jadi
    mode Rarest (0.45) dan Balanced (0.85) benar-benar menghasilkan wilayah
    kelangkaan berbeda, persis seperti jalur pool untuk 3L.
    """
    letters = [c for c in chars if allow_vowels or c not in _VOWEL_SET] or list(chars)
    weights = [max(0.05, LETTER_RARITY.get(c, 6.0)) ** 2 for c in letters]
    excluded = exclude or frozenset()
    band = max(0.0, min(1.0, float(band)))

    target = max(count * 3 + 200, 400)
    seen: Set[str] = set()
    out: List[str] = []
    attempts = 0
    limit = target * 40 + len(excluded) * 4
    while len(out) < target and attempts < limit:
        body = "".join(rng.choices(letters, weights=weights,
                                   k=length - 1 if underscore else length))
        attempts += 1
        if underscore:
            slot = rng.randrange(length)
            name = body[:slot] + "_" + body[slot:]
        else:
            name = body
        if name in seen or name in BLOCKED_NAMES or name in excluded or is_blocked(name):
            continue
        seen.add(name)
        out.append(name)

    if not out:
        return []
    out.sort(key=lambda s: (-rarity_score(s), s))
    take = min(count, len(out))
    band_size = max(take, int(len(out) * band))
    picked = rng.sample(out[:band_size], take)
    picked.sort(key=lambda s: (-rarity_score(s), s))
    return picked

def generate_rare(count: int, length: int = 3, allow_vowels: bool = True,
                  chars: str = LOWERCASE, band: float = 0.45,
                  seed: Optional[int] = None,
                  exclude: Optional[Set[str]] = None,
                  underscore: bool = False) -> List[str]:
    """Hasilkan nama dari wilayah terlangka, urut dari yang paling langka.

    band = porsi kandidat teratas yang boleh diambil (0.45 = 45% terlangka).
    Sampling acak di dalam band membuat klik berikutnya tidak mengulang nama
    yang sama, sementara urutan hasil tetap dari terlangka ke lebih umum.

    exclude = nama yang sudah pernah dipindai; dilewati supaya setiap
    generate menghasilkan target baru, bukan mengulang yang sudah diketahui.
    underscore = mode Balanced 3L: tepat satu '_' di setiap nama.
    """
    count = int(max(0, count))
    if count == 0:
        return []

    rng = random.Random(seed)
    excluded = exclude or frozenset()
    pool = rare_pool(length, allow_vowels, chars, underscore)
    if pool:
        candidates = [n for n in pool if n not in excluded and not is_blocked(n)]
        if not candidates:
            return []
        take = min(count, len(candidates))
        band = max(0.0, min(1.0, float(band)))
        band_size = max(take, int(len(candidates) * band))
        picked = rng.sample(candidates[:band_size], take)
        picked.sort(key=lambda s: (-rarity_score(s), s))
        return picked

    return _sample_rare(count, int(length), allow_vowels, chars, rng,
                        excluded, underscore, band)

def pattern_combo(pattern: str) -> str:
    """Generate from pattern: x=letter, d=digit, u/_=underscore, a=any"""
    out = []
    for ch in pattern.lower():
        if ch == 'x':
            out.append(random.choice(LOWERCASE))
        elif ch == 'd':
            out.append(random.choice(DIGITS))
        elif ch in ('u', '_'):
            out.append('_')
        elif ch == 'a':
            out.append(random.choice(ALLOWED))
        elif ch.isalpha():
            out.append(random.choice(LOWERCASE) if ch.islower() else ch.lower())
        elif ch.isdigit():
            out.append(ch)
        else:
            continue
    return ''.join(out)

def generate_pattern(patterns: List[str], count: int,
                     exclude: Optional[Set[str]] = None) -> List[str]:
    excluded = exclude or frozenset()
    seen: Set[str] = set()
    out: List[str] = []
    valid_patterns = [p for p in patterns if p.strip()]
    if not valid_patterns:
        return out
    attempts = 0
    while len(out) < count and attempts < count * 50 + len(excluded) * 4:
        p = random.choice(valid_patterns)
        name = pattern_combo(p)
        if name and 3 <= len(name) <= 16 and name not in seen and name not in excluded \
                and all(c.isalnum() or c == '_' for c in name) \
                and not is_blocked(name):
            seen.add(name)
            out.append(name)
        attempts += 1
    return out

def get_pattern_examples() -> List[str]:
    return ["_dd", "x_x", "xd_", "_x_", "dd_", "xxx", "x_d", "a_a", "xx_", "__d"]

if __name__ == "__main__":
    print("Smart 3L:", generate_smart_random(10, 3))
    print("Smart 4L:", generate_smart_random(10, 4))
    print("Pattern _dd:", generate_pattern(["_dd"], 5))
    print("Full 3L ordered first 5:", enumerate_ordered(3)[:5])
    print("Rarest 3L (vokal boleh):", generate_rare(10, 3, seed=1))
    print("Rarest 3L (konsonan):", generate_rare(10, 3, allow_vowels=False, seed=1))
    print("Balanced 3L (underscore):", generate_rare(10, 3, band=0.85, underscore=True, seed=1))
    print("Rarest 4L:", generate_rare(10, 4, allow_vowels=False, seed=1))
