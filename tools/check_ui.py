#!/usr/bin/env python3
"""
check_ui.py — pemeriksaan statis untuk UI Varin Sniper (tanpa display / Tk).

Yang diperiksa:
  1. semua file Python bisa di-parse
  2. tidak ada nama global yang tak terdefinisi per modul (mirip pyflakes)
  3. setiap `from modul_lokal import nama` benar-benar ada
  4. semua kunci i18n yang dipakai ada di BAHASA INGGRIS dan INDONESIA
  5. semua ikon yang dirujuk kode tersedia di assets/ (hi/dim/ink)
  6. matematika wallpaper & helper warna tema berjalan benar

Jalankan dari root repo:  python tools/check_ui.py
Exit code != 0 kalau ada masalah (dipakai juga oleh GitHub Actions).
"""
from __future__ import annotations

import ast
import builtins
import os
import sys
from typing import Dict, List, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAILS: List[str] = []
NOTES: List[str] = []


def fail(message: str) -> None:
    FAILS.append(message)


def ok(message: str) -> None:
    NOTES.append(message)


def py_files() -> List[str]:
    out: List[str] = []
    for base, _dirs, files in os.walk(ROOT):
        if any(part in base for part in (".git", "__pycache__", "build", "dist", "assets")):
            continue
        for name in files:
            if name.endswith(".py"):
                out.append(os.path.join(base, name))
    return sorted(out)


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


# --------------------------------------------------------------------------- #
# 1 + 2 + 3. parse, nama global, dan import lokal
# --------------------------------------------------------------------------- #
def module_level_names(tree: ast.Module) -> Set[str]:
    names: Set[str] = set()

    def walk(body) -> None:
        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            names.add(sub.id)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                target = node.target
                if isinstance(target, ast.Name):
                    names.add(target.id)
            elif isinstance(node, (ast.If, ast.Try, ast.While, ast.For, ast.With)):
                for field in ("body", "orelse", "finalbody"):
                    walk(getattr(node, field, []) or [])
                for handler in getattr(node, "handlers", []) or []:
                    walk(handler.body)

    walk(tree.body)
    return names


ALLOWED_GLOBALS = {"__file__", "__name__", "__doc__", "__package__", "__builtins__", "annotations"}


def check_module(path: str, local_modules: Dict[str, Set[str]]) -> ast.Module:
    source = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(source, rel(path))
    except SyntaxError as exc:
        fail(f"{rel(path)}: syntax error -> {exc}")
        return ast.Module(body=[], type_ignores=[])

    # nama global yang dipakai vs yang didefinisikan
    try:
        import symtable
        table = symtable.symtable(source, rel(path), "exec")
    except Exception:  # noqa: BLE001
        table = None

    if table is not None:
        used: Set[str] = set()

        def collect(tbl) -> None:
            for symbol in tbl.get_symbols():
                if symbol.is_global() and symbol.is_referenced():
                    used.add(symbol.get_name())
            for child in tbl.get_children():
                collect(child)

        collect(table)

        # Semua nama yang PERNAH di-bind (scope mana pun) dianggap terdefinisi.
        # Ini sengaja longgar supaya variabel comprehension/loop tidak jadi
        # false positive, tapi tetap menangkap salah ketik nama global.
        defined = module_level_names(tree) | ALLOWED_GLOBALS
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                defined.add(node.id)
            elif isinstance(node, ast.arg):
                defined.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and node.name:
                defined.add(node.name)

        missing = sorted(n for n in used if n not in defined and not hasattr(builtins, n))
        if missing:
            fail(f"{rel(path)}: nama global tak terdefinisi -> {missing}")

    # import dari modul lokal
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in local_modules:
            exported = local_modules[node.module]
            for alias in node.names:
                if alias.name != "*" and alias.name not in exported:
                    fail(f"{rel(path)}:{node.lineno}: 'from {node.module} import {alias.name}' "
                         f"tidak ada di {node.module}.py")
    return tree


# --------------------------------------------------------------------------- #
# 4. kunci i18n
# --------------------------------------------------------------------------- #
def collect_i18n_keys(tree: ast.Module, path: str) -> Set[str]:
    keys: Set[str] = set()

    def from_node(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            keys.add(node.value)
        elif isinstance(node, ast.IfExp):
            from_node(node.body)
            from_node(node.orelse)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("t", "T") and node.args:
            from_node(node.args[0])
    return keys


# --------------------------------------------------------------------------- #
# 5. ikon
# --------------------------------------------------------------------------- #
def icon_refs(tree: ast.Module) -> Tuple[Set[str], Set[str]]:
    action: Set[str] = set()
    nav: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "icon" and isinstance(kw.value, ast.Constant) \
                    and isinstance(kw.value.value, str):
                action.add(kw.value.value)
        if isinstance(node.func, ast.Attribute) and node.args:
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            if node.func.attr == "nav_icon":
                nav.add(first.value)
            elif node.func.attr == "action_icon":
                action.add(first.value)
    return action, nav


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    files = py_files()
    if not files:
        fail("tidak ada file Python ditemukan")
        return 1

    modules: Dict[str, ast.Module] = {}
    local_exports: Dict[str, Set[str]] = {}
    for path in files:
        tree = check_module(path, {})  # pass 1: parse only (exports belum lengkap)
        modules[rel(path)] = tree
        name = os.path.basename(path)[:-3]
        local_exports[name] = module_level_names(tree)

    # pass 2: validasi import sekarang setelah semua export diketahui
    for path in files:
        check_module(path, local_exports)

    # -- i18n ---------------------------------------------------------------- #
    from ui import i18n

    gaps = i18n.missing_keys()
    if gaps:
        fail(f"i18n: kunci belum lengkap -> {gaps}")

    used: Set[str] = set()
    for key, tree in modules.items():
        if key.startswith("tools/"):
            continue
        used |= collect_i18n_keys(tree, key)

    missing_en = sorted(k for k in used if k not in i18n.TRANSLATIONS["en"])
    missing_id = sorted(k for k in used if k not in i18n.TRANSLATIONS["id"])
    if missing_en:
        fail(f"i18n: kunci dipakai tapi tidak ada di EN -> {missing_en}")
    if missing_id:
        fail(f"i18n: kunci dipakai tapi tidak ada di ID -> {missing_id}")

    # kunci dinamis (f-string) yang harus ada
    for page in ("checker", "sniper", "accounts", "proxies", "history", "settings", "stats"):
        if f"nav.{page}" not in i18n.TRANSLATIONS["en"]:
            fail(f"i18n: kunci dinamis nav.{page} tidak ada")
    for mode in ("rarest", "balanced", "random", "legacy"):
        for lang in i18n.LANGUAGES:
            if f"checker.gen_mode_{mode}" not in i18n.TRANSLATIONS[lang]:
                fail(f"i18n[{lang}]: kunci dinamis checker.gen_mode_{mode} tidak ada")
    ok(f"i18n: {len(used)} kunci dipakai, {len(i18n.TRANSLATIONS['en'])} tersedia per bahasa")

    # format placeholders tidak error
    for key, kwargs in (
        ("toast.gen", {"n": 1, "length": 3}),
        ("log.ready", {"name": "x", "version": "y", "accounts": 0, "proxies": 0}),
        ("st.meta", {"uptime": "00:00:00", "rate": 0.0, "taken": 0}),
        ("foot.right", {"rate": 0.0, "alive": 0, "discord": "off"}),
        ("proxy.result", {"alive": 0, "dead": 0, "total": 0}),
        ("head.progress_work", {"n": 0}),
        ("dlg.claim_via", {"account": "a"}),
        ("log.gen_rare", {"n": 0, "length": 3, "mode": "Rarest"}),
        ("toast.gen_rare", {"n": 0, "length": 3, "mode": "Rarest"}),
    ):
        for lang in i18n.LANGUAGES:
            i18n.t.set_lang(lang)
            rendered = i18n.t(key, **kwargs)
            if "??" in rendered or "{" in rendered:
                fail(f"i18n[{lang}]: format '{key}' gagal -> {rendered!r}")
    i18n.t.set_lang(i18n.DEFAULT_LANG)

    # -- ikon ---------------------------------------------------------------- #
    action_icons: Set[str] = set()
    nav_icons: Set[str] = set()
    for key, tree in modules.items():
        if key.startswith("tools/"):
            continue
        a, n = icon_refs(tree)
        action_icons |= a
        nav_icons |= n

    # ikon navigasi dipanggil dengan variabel (bukan literal), jadi daftarnya eksplisit
    nav_icons |= {"checker", "sniper", "accounts", "proxies", "history", "settings", "stats"}

    icons_dir = os.path.join(ROOT, "assets", "icons")
    for name in sorted(nav_icons):
        for variant in ("hi", "dim"):
            path = os.path.join(icons_dir, f"nav_{name}_{variant}.png")
            if not os.path.exists(path):
                fail(f"ikon hilang: assets/icons/nav_{name}_{variant}.png (dipakai kode)")
    for name in sorted(action_icons):
        for variant in ("hi", "dim", "ink"):
            path = os.path.join(icons_dir, f"act_{name}_{variant}.png")
            if not os.path.exists(path):
                fail(f"ikon hilang: assets/icons/act_{name}_{variant}.png (dipakai kode)")
    for name in ("icon.png", "icon.ico", "logo.png", "logo_small.png"):
        if not os.path.exists(os.path.join(ROOT, "assets", name)):
            fail(f"aset hilang: assets/{name}")
    ok(f"ikon: {len(nav_icons)} nav, {len(action_icons)} aksi direferensikan kode")

    # -- jalur simpan config -------------------------------------------------- #
    # GUI wajib memakai save_current_config(). utils.save_config(path, config)
    # butuh dua argumen; pemanggilan satu-argumen dulu hanya error saat runtime
    # (bahasa & setting tidak pernah tersimpan), jadi dijaga di sini.
    bad_calls: List[str] = []
    for key, tree in modules.items():
        if not key.startswith("ui/"):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "save_config"):
                bad_calls.append(f"{key}:{node.lineno}")
    if bad_calls:
        fail(f"config: ui/ harus memakai save_current_config(), bukan save_config() -> {bad_calls}")
    utils_tree = modules.get("utils.py")
    defined = {node.name for node in ast.walk(utils_tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))} if utils_tree else set()
    if "save_current_config" not in defined:
        fail("config: utils.save_current_config() tidak ada")
    ok("config: UI menyimpan setting lewat save_current_config()")

    # -- generator kelangkaan ------------------------------------------------ #
    from generator import (BLOCKED_NAMES, LETTER_RARITY, generate_random,
                           generate_rare, rarity_score)

    rare = generate_rare(300, 3, allow_vowels=True, seed=1234)
    if len(rare) != len(set(rare)):
        fail("generator: generate_rare menghasilkan nama duplikat")
    if any(len(name) != 3 for name in rare):
        fail("generator: generate_rare menghasilkan panjang salah")
    if rare != sorted(rare, key=lambda s: (-rarity_score(s), s)):
        fail("generator: hasil tidak urut dari yang paling langka")
    if any(name in BLOCKED_NAMES for name in rare):
        fail("generator: nama terblokir ikut terpilih")

    consonants = generate_rare(200, 3, allow_vowels=False, seed=7)
    if any(set(name) & set("aeiou") for name in consonants):
        fail("generator: mode konsonan masih memuat vokal")

    if generate_rare(50, 3, seed=99) != generate_rare(50, 3, seed=99):
        fail("generator: seed sama tapi hasil tidak deterministik")

    four = generate_rare(120, 4, allow_vowels=False, seed=5)
    if len(set(four)) != 120 or any(len(name) != 4 for name in four):
        fail(f"generator: sampling 4L tidak menghasilkan 120 nama unik ({len(set(four))})")

    # 4L harus jalan di semua mode (rarest, balanced, legacy), bukan hanya 3L,
    # dan kedua mode tidak boleh menghasilkan wilayah kelangkaan yang sama.
    rare4 = generate_rare(150, 4, band=0.45, seed=21)
    bal4 = generate_rare(150, 4, band=0.85, seed=21)
    for names4, label in ((rare4, "rarest"), (bal4, "balanced")):
        if len(names4) != 150 or any(len(n) != 4 for n in names4):
            fail(f"generator: mode {label} 4L tidak menghasilkan 150 nama unik")
    if rare4 == bal4:
        fail("generator: mode rarest & balanced 4L menghasilkan daftar identik")
    mean_rare = sum(rarity_score(n) for n in rare4) / len(rare4)
    mean_bal = sum(rarity_score(n) for n in bal4) / len(bal4)
    if mean_rare <= mean_bal:
        fail(f"generator: 4L rarest tidak lebih langka dari balanced ({mean_rare:.2f} vs {mean_bal:.2f})")
    random4 = generate_random(80, 4)
    if len(random4) != 80 or any(len(n) != 4 for n in random4):
        fail("generator: generate_random 4L tidak menghasilkan 80 nama")

    # Mode Random: a-z, 0-9 dan _ benar-benar dipakai (ig9, hg_, x7z).
    import random as _random
    _random.seed(4242)
    mixed = generate_random(400, 3)
    if len(mixed) != 400 or any(len(n) != 3 for n in mixed):
        fail("generator: random 3L tidak menghasilkan 400 nama 3 karakter")
    if not any(any(ch.isdigit() for ch in n) for n in mixed):
        fail("generator: random 3L tidak pernah memakai angka")
    if not any("_" in n for n in mixed):
        fail("generator: random 3L tidak pernah memakai underscore")

    # Balanced 3L: tepat satu underscore di setiap nama
    balanced = generate_rare(120, 3, band=0.85, underscore=True, seed=17)
    if len(balanced) != 120 or len(set(balanced)) != 120:
        fail(f"generator: balanced 3L underscore tidak unik ({len(set(balanced))})")
    if any(len(n) != 3 or n.count("_") != 1 for n in balanced):
        fail(f"generator: balanced 3L wajib 3 karakter dengan satu '_' -> {balanced[:5]}")
    if balanced != sorted(balanced, key=lambda s: (-rarity_score(s), s)):
        fail("generator: balanced 3L tidak urut dari yang paling langka")

    # Nama yang sudah dipindai tidak boleh muncul lagi di hasil generate
    seen_before = set(generate_rare(200, 3, seed=31))
    fresh = generate_rare(100, 3, seed=33, exclude=seen_before)
    if set(fresh) & seen_before:
        fail("generator: exclude tidak bekerja (nama lama masih muncul)")
    if len(fresh) != 100:
        fail(f"generator: exclude memotong hasil jadi {len(fresh)} (harus 100)")
    fresh4 = generate_rare(100, 4, seed=35, exclude=seen_before)
    if set(fresh4) & seen_before or len(fresh4) != 100:
        fail("generator: exclude gagal pada sampling 4L")
    if set(generate_random(40, 3, exclude=seen_before)) & seen_before:
        fail("generator: exclude gagal pada generate_random")

    order = [rarity_score(n) for n in ("zbx", "nfj", "ldm", "hda")]
    if order != sorted(order, reverse=True):
        fail(f"generator: urutan contoh tidak menurun sesuai kelangkaan -> {order}")
    if rarity_score("hda") <= rarity_score("the"):
        fail("generator: 'hda' seharusnya lebih langka daripada 'the'")
    if rarity_score("aaa") >= rarity_score("hda"):
        fail("generator: 'aaa' seharusnya lebih umum daripada 'hda'")
    if min(LETTER_RARITY.values()) <= 0:
        fail("generator: bobot huruf harus positif")
    ok(f"generator: {len(rare)} nama 3L terurut terlangka, {len(four)} nama 4L sampling")

    # -- bulk lookup (jalur cepat checker) ----------------------------------- #
    from checker import BulkLookup

    class _FakeResp:
        def __init__(self, status, payload, headers=None):
            self.status_code = status
            self._payload = payload
            self.headers = headers or {}

        def json(self):
            if isinstance(self._payload, Exception):
                raise self._payload
            return self._payload

    if BulkLookup.batch_size != 10:
        fail(f"checker: batch bulk harus 10 nama, bukan {BulkLookup.batch_size}")

    bulk = BulkLookup(timeout=1.0)
    sent_batches = []

    def _bulk_ok(url, json=None, timeout=None, headers=None):
        sent_batches.append(list(json or []))
        return _FakeResp(200, [{"name": "Abc"}, {"name": "zzq"}])

    bulk.session.post = _bulk_ok  # type: ignore[assignment]
    taken, resolved = bulk.lookup(["abc", "zzz", "qzxw"])
    if not resolved or taken != {"abc"}:
        fail(f"checker: bulk lookup salah parse -> {taken!r} resolved={resolved}")

    def _bulk_empty(url, json=None, timeout=None, headers=None):
        sent_batches.append(list(json or []))
        return _FakeResp(200, [])

    bulk.session.post = _bulk_empty  # type: ignore[assignment]
    bulk.lookup([f"name{i:02d}" for i in range(25)])
    if len(sent_batches[-1]) != 10:
        fail(f"checker: bulk tidak membatasi batch ke 10 -> {len(sent_batches[-1])}")

    limited = BulkLookup(timeout=1.0)
    limited.session.post = lambda *a, **k: _FakeResp(429, [], {"Retry-After": "5"})  # type: ignore[assignment]
    taken_429, resolved_429 = limited.lookup(["abc"])
    if resolved_429 or taken_429 or limited.healthy():
        fail("checker: 429 dari bulk harus jadi cooldown + fallback per-nama")

    broken = BulkLookup(timeout=1.0)
    broken.session.post = lambda *a, **k: _FakeResp(200, ValueError("bad json"))  # type: ignore[assignment]
    if broken.lookup(["abc"])[1]:
        fail("checker: body bulk tidak valid harus dianggap gagal resolve")
    ok("checker: bulk lookup 10 nama/request, 429 -> fallback per-nama")

    # -- matematika wallpaper + helper tema ---------------------------------- #
    from ui import theme as th
    from ui import wallpaper as wp

    for point in ((1.0, 2.0, 3.0), (-0.5, 0.25, 0.75)):
        rotated = wp.rotate_y([point], 0.7)[0]
        if abs(sum(v * v for v in rotated) ** 0.5 - sum(v * v for v in point) ** 0.5) > 1e-9:
            fail("wallpaper: rotate_y mengubah panjang vektor")
        rotated = wp.rotate_x([point], -1.3)[0]
        if abs(sum(v * v for v in rotated) ** 0.5 - sum(v * v for v in point) ** 0.5) > 1e-9:
            fail("wallpaper: rotate_x mengubah panjang vektor")

    projected = wp.project([(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)], 100.0, 50.0, 200.0, 2.0)
    if abs(projected[0][0] - 100.0) > 1e-6 or abs(projected[0][1] - 50.0) > 1e-6:
        fail(f"wallpaper: project titik origin salah -> {projected[0]}")
    if projected[1][0] != 100.0 or not projected[1][2] > projected[0][2]:
        fail(f"wallpaper: project kedalaman salah -> {projected[1]}")

    for depth in (2.0, 3.0, 4.5):
        color = wp.depth_color(depth, 2.0, 4.6, th.ACCENT)
        if len(color) != 7 or not color.startswith("#"):
            fail(f"wallpaper: depth_color tidak menghasilkan hex -> {color!r}")

    points = wp.vault_points()
    edges = wp.vault_edges()
    if len(set(edges)) != len(edges):
        fail("wallpaper: ada sisi vault yang duplikat")
    if max(max(edge) for edge in edges) >= len(points):
        fail("wallpaper: indeks sisi vault keluar dari daftar titik")
    ok(f"wallpaper: {len(points)} titik, {len(edges)} sisi, proyeksi & depth fog valid")

    for color in ("#000000", "#ffffff", "#b366ff", th.BG):
        if th.from_rgb(*th.to_rgb(color)) != color:
            fail(f"tema: konversi warna tidak bolak-balik untuk {color}")
    if th.mix("#000000", "#ffffff", 0.0) != "#000000" or th.mix("#000000", "#ffffff", 1.0) != "#ffffff":
        fail("tema: mix() salah di ujung rentang")
    mid = th.to_rgb(th.mix("#000000", "#ffffff", 0.5))[0]
    if not 0.45 < mid < 0.55:
        fail(f"tema: mix() 0.5 tidak di tengah -> {mid}")
    helpers = (
        ("ease_out_cubic", lambda: th.ease_out_cubic(0.5)),
        ("clamp", lambda: th.clamp(5.0, 0.0, 1.0)),
        ("lerp", lambda: th.lerp(1.0, 3.0, 0.5)),
        ("darken", lambda: th.darken("#b366ff", 0.3)),
        ("lighten", lambda: th.lighten("#b366ff", 0.3)),
    )
    for name, call in helpers:
        try:
            call()
        except Exception as exc:  # noqa: BLE001
            fail(f"tema: helper {name} error -> {exc}")
    ok("tema: konversi & helper warna valid")

    # -- spec PyInstaller ---------------------------------------------------- #
    spec_path = os.path.join(ROOT, "Varin-Sniper.spec")
    if os.path.exists(spec_path):
        try:
            ast.parse(open(spec_path, encoding="utf-8").read())
        except SyntaxError as exc:
            fail(f"Varin-Sniper.spec tidak bisa di-parse -> {exc}")
    else:
        fail("Varin-Sniper.spec tidak ditemukan")

    # -- ringkasan ----------------------------------------------------------- #
    for note in NOTES:
        print(f"  ok   {note}")
    if FAILS:
        print()
        for problem in FAILS:
            print(f"  FAIL {problem}")
        print(f"\ncheck_ui: {len(FAILS)} masalah ditemukan")
        return 1
    print("\ncheck_ui: semua pemeriksaan lulus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
