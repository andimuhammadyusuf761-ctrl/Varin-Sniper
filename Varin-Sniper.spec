# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec untuk Varin Sniper (Windows .exe).
#
# Build:  pyinstaller --clean Varin-Sniper.spec
# Hasil:  dist/Varin-Sniper.exe
#
# Catatan:
# - customtkinter WAJIB dikoleksi lengkap (tema, aset, dan Tcl/Tk DLL)
#   agar GUI tidak putih / gagal diimpor setelah dibekukan.
# - console=False -> tanpa jendela hitam; log sudah tampil di GUI.

import os
import sys
from PyInstaller.utils.hooks import collect_all

# --- Guard: tanpa customtkinter, exe akan crash saat dibuka. ----------------
# Lebih baik build GAGAL di sini daripada mengirim exe yang tidak bisa start.
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
]

# Sertakan file suara optional jika ada di folder proyek
if os.path.exists("success.mp3"):
    datas.append(("success.mp3", "."))

# --- Tcl/Tk runtime DLLs (Windows) agar tkinter/customtkinter berjalan ---
def _tcltk_binaries():
    out = []
    try:
        import tkinter
        tk_path = os.path.dirname(tkinter.__file__)
        # Cari tcl86t.dll dan tk86t.dll di sekitar instalasi Python
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
    icon=None,   # ganti: icon="varin_icon.ico" jika punya file ikon
    version=None,
)
