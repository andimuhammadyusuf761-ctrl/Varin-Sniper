# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec untuk Varin Sniper (Windows .exe).
#
# Build:  pyinstaller --clean Varin-Sniper.spec
# Hasil:  dist/Varin-Sniper.exe
#
# Catatan:
# - --collect-all customtkinter WAJIB, karena tema/bundel data CTk tidak
#   terdeteksi otomatis oleh PyInstaller (GUI jadi putih/error tanpa ini).
# - console=False -> tanpa jendela hitam; log sudah tampil di GUI.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

for pkg in ("customtkinter", "darkdetect"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += ["playsound3"]

# Sertakan file suara optional jika ada di folder proyek
from os.path import exists
if exists("success.mp3"):
    datas.append(("success.mp3", "."))

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
