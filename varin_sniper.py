#!/usr/bin/env python3
"""
Varin Sniper — 3L/4L Minecraft Username Sniper (entry point).

File ini sengaja tipis: tugasnya hanya menyiapkan dependency, menyetel tema,
lalu menjalankan GUI. Logikanya ada di:
  * controller.py   — mesin (antrian, worker, claim, notifikasi)
  * ui/app.py       — layout, sidebar, navigasi, sub-tab, event mesin
  * ui/widgets.py   — komponen 3D (kartu, chip, log, segmented tab, toast)
  * ui/wallpaper.py — live wallpaper 3D hemat CPU
  * ui/i18n.py      — English (default) + Indonesia
  * ui/theme.py     — palette dark purple gradient + helper gradient/3D
  * ui/icons.py     — set ikon (assets/ hasil tools/make_icons.py)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys


def _show_startup_error(message: str) -> None:
    """Tampilkan error fatal tanpa bergantung pada customtkinter/tkinter."""
    try:
        print(f"[Varin Sniper] {message}", file=sys.stderr)
    except Exception:  # noqa: BLE001  (exe tanpa konsol: sys.stderr = None)
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Varin Sniper - gagal start", 0x10)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _root = _tk.Tk()
        _root.withdraw()
        _mb.showerror("Varin Sniper", message)
        _root.destroy()
    except Exception:  # noqa: BLE001
        pass


def ensure_dependencies() -> None:
    """Pastikan customtkinter tersedia sebelum GUI diimpor.

    Menjalankan dari source: requirements.txt boleh dipasang otomatis.
    Menjalankan sebagai .exe (frozen): dependency WAJIB sudah dibundel saat
    build. `pip install` dari dalam exe tidak mungkin berhasil karena
    sys.executable menunjuk ke exe itu sendiri, dan percobaan itu hanya
    membuat aplikasi gagal start dengan "unhandled exception" sebelum
    jendela sempat muncul.
    """
    try:
        import customtkinter  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    if getattr(sys, "frozen", False):
        _show_startup_error(
            "GUI tidak bisa dibuka: file .exe ini tidak memuat dependency "
            "'customtkinter'.\n\n"
            "Artinya exe dibangun tanpa memasang requirements (mis. build lokal "
            "tanpa `pip install -r requirements.txt`), sehingga komponen GUI "
            "ikut terlewat.\n\n"
            "Solusi: unduh ulang Varin-Sniper.exe dari build terbaru di GitHub "
            "Actions, atau jalankan build.bat setelah dependency terpasang."
        )
        raise SystemExit(1)

    repo_root = os.path.dirname(os.path.abspath(__file__))
    requirements_path = os.path.join(repo_root, "requirements.txt")
    print("[Varin Sniper] Missing dependency 'customtkinter'. Installing requirements...",
          file=sys.stderr)
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_path])
        import customtkinter  # noqa: F401
        return
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Missing dependency 'customtkinter'. Install it with:\n"
            f"  {sys.executable} -m pip install -r \"{requirements_path}\"\n"
            f"Original error: {exc}"
        ) from exc


def main() -> int:
    ensure_dependencies()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("VarinSniper")

    try:
        from ui import theme
        theme.apply_appearance()
        theme.set_effects(True)
        from ui.app import VarinSniperApp
        from ui.i18n import t
    except Exception as exc:  # noqa: BLE001
        logger.exception("gagal memuat UI")
        _show_startup_error(f"Gagal memuat komponen GUI:\n{exc}")
        return 1

    try:
        app = VarinSniperApp()
        app.mainloop()
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("fatal")
        try:
            from tkinter import messagebox
            messagebox.showerror("Varin Sniper", t("dlg.fatal_msg", error=exc))
        except Exception:  # noqa: BLE001
            _show_startup_error(f"{t('dlg.fatal_msg', error=exc)}")
        return 1


PremiumSniper = None  # alias historis; kelas sebenarnya ada di ui.app


if __name__ == "__main__":
    raise SystemExit(main())
