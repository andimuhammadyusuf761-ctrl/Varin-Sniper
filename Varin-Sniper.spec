# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec untuk Varin Sniper (Windows .exe).
#
# Build:  pyinstaller --clean Varin-Sniper.spec
# Hasil:  dist/Varin-Sniper.exe
#
# Catatan:
# - customtkinter WAJIB dikoleksi lengkap (tema + aset) supaya GUI tidak blank.
# - Folder assets/ (ikon aplikasi, ikon nav/tombol) ikut dibundel dan dibaca
#   lewat ui/icons.resource_path() sehingga aman saat dijalankan sebagai exe.
# - Kalau customtkinter tidak ada di environment build, build DIGAGALKAN di
#   sini — lebih baik daripada mengirim exe yang crash saat dibuka.

import os
import sys
from PyInstaller.utils.hooks import collect_all

# --- Guard: tanpa customtkinter, exe akan crash saat dibuka. ----------------
try:
    import customtkinter
except ModuleNotFoundError as exc:
    raise SystemExit(
        "[SPEC] customtkinter tidak terpasang di environment build.\n"
        "       Jalankan dulu: python -m pip install -r requirements.txt\n"
        f"       Detail: {exc}"
    )

# Kumpulkan semua data, biner, dan hidden-import customtkinter
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")

if not ctk_hiddenimports and not ctk_datas:
    raise SystemExit(
        "[SPEC] customtkinter ada di environment, tapi collect_all tidak "
        "menghasilkan apa pun.\n"
        "       Exe tanpa customtkinter pasti crash saat dibuka — build dihentikan."
    )

print(f"[SPEC] customtkinter {getattr(customtkinter, '__version__', '?')}: "
      f"{len(ctk_datas)} data, {len(ctk_binaries)} binary, "
      f"{len(ctk_hiddenimports)} hidden import")

datas = list(ctk_datas)
binaries = list(ctk_binaries)
hiddenimports = list(ctk_hiddenimports)

# Pastikan customtkinter dan tkinter dapat diimpor saat frozen
hiddenimports += [
    "customtkinter",
    "customtkinter.widgets",
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
    # modul aplikasi sendiri (import dinamis tidak akan terdeteksi otomatis)
    "ui",
    "ui.theme",
    "ui.i18n",
    "ui.icons",
    "ui.wallpaper",
    "ui.widgets",
    "ui.app",
    "controller",
]

# --- Aset aplikasi (ikon app + set ikon GUI) -------------------------------- #
ASSETS_DIR = os.path.join(os.getcwd(), "assets")
if os.path.isdir(ASSETS_DIR):
    datas.append((ASSETS_DIR, "assets"))
    icon_count = 0
    for _root, _dirs, _files in os.walk(ASSETS_DIR):
        icon_count += sum(1 for f in _files if f.lower().endswith(".png"))
    print(f"[SPEC] assets/ dibundel: {icon_count} file PNG")
else:
    raise SystemExit(
        "[SPEC] folder assets/ tidak ditemukan.\n"
        "       Jalankan: python tools/make_icons.py"
    )

# Sertakan file suara optional jika ada di folder proyek
if os.path.exists("success.mp3"):
    datas.append(("success.mp3", "."))

# --- Tcl/Tk runtime DLLs (Windows) agar tkinter/customtkinter berjalan ----- #
def _tcltk_binaries():
    out = []
    try:
        import tkinter
        tk_path = os.path.dirname(tkinter.__file__)
        candidates = [
            os.path.join(sys.prefix, "DLLs"),
            os.path.join(sys.prefix, "Library", "bin"),
            tk_path,
        ]
        for dll in ("tcl86t.dll", "tk86t.dll"):
            for base in candidates:
                p = os.path.join(base, dll)
                if os.path.exists(p):
                    out.append((p, os.path.join("DLLs", os.path.basename(p))))
                    break
    except Exception:
        pass
    return out


binaries += _tcltk_binaries()

a = Analysis(
    ["varin_sniper.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.tix"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Varin-Sniper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
    version=None,
)
