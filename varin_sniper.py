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

Mode smoke test (dipakai CI & tools/smoke_gui.py):
    VARIN_SMOKE_TEST=1 python varin_sniper.py
atau
    python varin_sniper.py --smoke-test

Di mode ini GUI dibangun penuh TANPA mainloop, seluruh halaman dibuka,
wallpaper digambar, bahasa diganti EN -> ID -> EN, lalu aplikasi menutup
sendiri. Hasilnya ditulis sebagai JSON ke VARIN_SMOKE_REPORT sehingga exe
yang "sukses dibuild" tapi tidak bisa membuka jendela tidak lagi lolos.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import traceback
from typing import Any, Callable, Dict, List

SMOKE_FLAG = "--smoke-test"
_SMOKE_ENV_TRUTHY = {"1", "true", "yes", "on"}

# Error yang menandakan masalah LINGKUNGAN (mesin tanpa display/session), bukan
# aplikasi. Dianggap peringatan supaya build tidak merah hanya karena runner CI
# tidak punya desktop, tapi tetap terlihat di log.
_HEADLESS_HINTS = (
    "no display name",
    "no display environment variable",
    "couldn't connect to display",
    "could not connect to display",
    "can't find a usable init.tcl",
    "application-specific initialization failed",
    "this probably means that tk wasn't installed properly",
)


def smoke_requested() -> bool:
    if SMOKE_FLAG in sys.argv[1:]:
        return True
    return os.environ.get("VARIN_SMOKE_TEST", "").strip().lower() in _SMOKE_ENV_TRUTHY


def smoke_report_path() -> str:
    return os.path.abspath(os.environ.get("VARIN_SMOKE_REPORT") or "smoke_report.json")


def _emits_like_headless(text: str) -> bool:
    low = (text or "").lower()
    return any(hint in low for hint in _HEADLESS_HINTS)


def _emit(message: str) -> None:
    """Tulis pesan ke stderr/stdout; exe tanpa konsol boleh menolaknya."""
    for name in ("stderr", "stdout"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.write(message + "\n")
            stream.flush()
            return
        except Exception:  # noqa: BLE001
            continue


def _show_startup_error(message: str) -> None:
    """Tampilkan error fatal tanpa bergantung pada customtkinter/tkinter."""
    _emit(f"[Varin Sniper] {message}")
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


# --------------------------------------------------------------------------- #
# Laporan smoke test
# --------------------------------------------------------------------------- #
def _smoke_base_report() -> Dict[str, Any]:
    return {
        "ok": False,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "meipass": getattr(sys, "_MEIPASS", None),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "steps": [],
        "errors": [],
        "environmental": False,
        "duration_s": 0.0,
    }


def _write_smoke_report(path: str, report: Dict[str, Any]) -> None:
    report["report_path"] = path
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        _emit(f"[smoke] gagal menulis laporan {path}: {exc}")


def _fail_smoke(report: Dict[str, Any], step: str, text: str) -> int:
    report["errors"] = [f"{step}: {text}"]
    report["environmental"] = _emits_like_headless(text)
    _write_smoke_report(smoke_report_path(), report)
    _emit(f"[smoke] FAIL {step} -> {text}")
    return 1


def ensure_dependencies(smoke: bool = False) -> None:
    """Pastikan customtkinter tersedia sebelum GUI diimpor.

    Menjalankan dari source: requirements.txt boleh dipasang otomatis.
    Menjalankan sebagai .exe (frozen): dependency WAJIB sudah dibundel saat
    build. `pip install` dari dalam exe tidak mungkin berhasil karena
    sys.executable menunjuk ke exe itu sendiri, dan percobaan itu hanya
    membuat aplikasi gagal start dengan "unhandled exception" sebelum
    jendela sempat muncul.

    Di mode smoke, kegagalan TIDAK memunculkan dialog (dialog akan
    menggantung di CI) melainkan ditulis ke laporan JSON.
    """
    try:
        import customtkinter  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    if getattr(sys, "frozen", False):
        message = (
            "GUI tidak bisa dibuka: file .exe ini tidak memuat dependency "
            "'customtkinter'.\n\n"
            "Artinya exe dibangun tanpa memasang requirements (mis. build lokal "
            "tanpa `pip install -r requirements.txt`), sehingga komponen GUI "
            "ikut terlewat.\n\n"
            "Solusi: unduh ulang Varin-Sniper.exe dari build terbaru di GitHub "
            "Actions, atau jalankan build.bat setelah dependency terpasang."
        )
        if smoke:
            _fail_smoke(_smoke_base_report(), "dependencies",
                        "exe ini tidak memuat 'customtkinter'")
            raise SystemExit(1)
        _show_startup_error(message)
        raise SystemExit(1)

    repo_root = os.path.dirname(os.path.abspath(__file__))
    requirements_path = os.path.join(repo_root, "requirements.txt")
    _emit("[Varin Sniper] Missing dependency 'customtkinter'. Installing requirements...")
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


# --------------------------------------------------------------------------- #
# Smoke test GUI (bounded, tanpa mainloop)
# --------------------------------------------------------------------------- #
def _run_smoke_test(app: Any) -> int:
    """Buka GUI di luar mainloop, periksa semua halaman lalu tutup rapi."""
    from ui import icons as icons_mod
    from ui.app import PAGES
    from ui.i18n import t

    report = _smoke_base_report()
    steps: List[Dict[str, Any]] = report["steps"]
    started = time.perf_counter()

    def require(condition: Any, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def pump(seconds: float = 0.25) -> int:
        """Jalankan event loop Tk sebentar supaya callback `after` benar-benar jalan."""
        deadline = time.perf_counter() + max(0.0, float(seconds))
        frames = 0
        while time.perf_counter() < deadline:
            try:
                app.update()
            except Exception:  # noqa: BLE001  (jendela hilang / display putus)
                break
            frames += 1
            time.sleep(0.006)
        return frames

    def record(name: str, worker: Callable[[], Any]) -> None:
        entry: Dict[str, Any] = {"step": name, "ok": False, "ms": 0.0, "detail": "", "error": None}
        begin = time.perf_counter()
        try:
            detail = worker()
            entry["ok"] = True
            entry["detail"] = "" if detail is None else str(detail)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["ms"] = round((time.perf_counter() - begin) * 1000.0, 1)
        steps.append(entry)
        suffix = "" if entry["ok"] else f" -> {entry['error']}"
        _emit(f"[smoke] {'ok  ' if entry['ok'] else 'FAIL'} {name} ({entry['ms']} ms){suffix}")

    # -- langkah-langkah ---------------------------------------------------- #
    def check_window() -> str:
        pump(0.3)
        require(app.winfo_exists(), "jendela tidak ada")
        require(app.winfo_ismapped(), "jendela tidak terlihat (belum di-map)")
        width, height = app.winfo_width(), app.winfo_height()
        require(width >= 800 and height >= 500, f"ukuran jendela terlalu kecil: {width}x{height}")
        return f"{width}x{height} title={app.title()!r}"

    def check_assets() -> str:
        icon = icons_mod.resource_path("assets", "icon.png")
        ico = icons_mod.resource_path("assets", "icon.ico")
        nav = icons_mod.resource_path("assets", "icons", "nav_checker_hi.png")
        for path in (icon, ico, nav):
            require(os.path.exists(path), f"aset tidak ada: {path}")
        return os.path.dirname(icon)

    def check_icons() -> str:
        missing = [name for name in PAGES if icons_mod.nav_icon(name, True) is None]
        require(not missing, f"ikon nav gagal dimuat: {', '.join(missing)}")
        require(icons_mod.logo("small") is not None, "logo_small.png gagal dimuat Tk")
        require(icons_mod.app_icon_photo() is not None, "icon.png gagal dimuat Tk")
        require(icons_mod.set_window_icon(app), "ikon jendela gagal dipasang")
        return f"{len(PAGES)} ikon nav + logo + ikon jendela"

    def check_pages() -> str:
        require(len(app.pages) == len(PAGES),
                f"jumlah halaman {len(app.pages)} != {len(PAGES)}")
        for page in PAGES:
            app._switch_page(page, animate=False)
            pump(0.16)
            require(app.active == page, f"halaman {page} tidak menjadi aktif")
            require(app.pages[page].winfo_manager() == "grid",
                    f"halaman {page} tidak terdaftar di layout")
        return f"{len(PAGES)} halaman dibuka"

    def check_wallpaper() -> str:
        wall = getattr(app, "_hero_wall", None)
        require(wall is not None, "wallpaper 3D tidak dibuat")
        items = len(wall.canvas.find_all())
        require(items >= 28, f"item kanvas hanya {items}")
        angle = wall._angle
        app._resume_wallpaper()
        pump(0.5)
        if wall._angle <= angle:      # bisa ter-pause kalau jendela kehilangan fokus
            app._resume_wallpaper()
            pump(0.5)
        require(wall._angle > angle, "wallpaper tidak beranimasi (angle tidak bertambah)")
        return f"{items} item kanvas, angle {angle:.2f} -> {wall._angle:.2f}"

    def check_language() -> str:
        # Judul jendela diterjemahkan dan pasti berbeda antar bahasa, jadi ini
        # bukti nyata bahwa UI dibangun ulang memakai bahasa baru.
        app._set_language("en")
        pump(0.3)
        en_title = app.title()
        require(en_title == t("app.window_title"), f"judul jendela bahasa en: {en_title!r}")

        app._set_language("id")
        pump(0.35)
        id_title = app.title()
        require(id_title == t("app.window_title"),
                f"judul jendela tidak mengikuti bahasa id: {id_title!r}")
        require(id_title != en_title, "judul jendela tidak berubah saat bahasa diganti")
        require(len(app.pages) == len(PAGES), "UI gagal dibangun ulang untuk bahasa id")
        for page in PAGES:
            label = app._nav_items[page]["btn"].cget("text").strip()
            require(label == t(f"nav.{page}"),
                    f"label nav {page} bahasa id: {label!r}")

        app._set_language("en")
        pump(0.3)
        require(app.title() == en_title, f"bahasa tidak kembali ke en: {app.title()!r}")
        return f"{en_title!r} -> {id_title!r} -> {en_title!r}"

    def check_engine_loop() -> str:
        pump(0.8)
        footer = (app.foot_left.cget("text") or "").strip()
        require(footer, "footer kosong: loop _tick tidak berjalan")
        return footer

    def check_close() -> str:
        app._on_close()
        # Setelah destroy(), Tk menolak perintah "winfo" (TclError). Itu justru
        # bukti jendelanya sudah hilang, jadi diperlakukan sebagai tertutup.
        try:
            alive = bool(app.winfo_exists())
        except Exception:  # noqa: BLE001
            alive = False
        require(not alive, "jendela masih hidup setelah _on_close()")
        return "ditutup rapi"

    for name, worker in (
        ("window", check_window),
        ("assets", check_assets),
        ("icons", check_icons),
        ("pages", check_pages),
        ("wallpaper", check_wallpaper),
        ("language", check_language),
        ("engine_loop", check_engine_loop),
        ("close", check_close),
    ):
        record(name, worker)

    failures = [step for step in steps if not step["ok"]]
    report["ok"] = not failures
    report["errors"] = [f"{step['step']}: {step['error']}" for step in failures]
    report["environmental"] = bool(failures) and all(
        _emits_like_headless(step["error"] or "") for step in failures
    )
    report["duration_s"] = round(time.perf_counter() - started, 2)
    _write_smoke_report(smoke_report_path(), report)
    _emit(f"[smoke] {'LULUS' if report['ok'] else 'GAGAL'} dalam {report['duration_s']}s "
          f"({len(steps) - len(failures)}/{len(steps)} langkah)")
    for text in report["errors"]:
        _emit(f"[smoke]   - {text}")
    return 0 if report["ok"] else 1


def main() -> int:
    smoke = smoke_requested()

    try:
        ensure_dependencies(smoke=smoke)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        if smoke:
            return _fail_smoke(_smoke_base_report(), "dependencies",
                               f"{type(exc).__name__}: {exc}")
        _show_startup_error(f"{exc}")
        return 1

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
        if smoke:
            return _fail_smoke(_smoke_base_report(), "import_ui",
                               f"gagal memuat komponen GUI: {type(exc).__name__}: {exc}")
        _show_startup_error(f"Gagal memuat komponen GUI:\n{exc}")
        return 1

    try:
        app = VarinSniperApp()
    except Exception as exc:  # noqa: BLE001
        logger.exception("fatal saat membangun GUI")
        if smoke:
            report = _smoke_base_report()
            report["traceback"] = traceback.format_exc()
            return _fail_smoke(report, "construct",
                               f"{type(exc).__name__}: {exc}")
        try:
            from tkinter import messagebox
            messagebox.showerror("Varin Sniper", t("dlg.fatal_msg", error=exc))
        except Exception:  # noqa: BLE001
            _show_startup_error(f"{t('dlg.fatal_msg', error=exc)}")
        return 1

    if smoke:
        return _run_smoke_test(app)

    try:
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
