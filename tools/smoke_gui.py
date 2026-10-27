#!/usr/bin/env python3
"""smoke_gui.py — buktikan GUI Varin Sniper benar-benar bisa dibuka.

Skrip ini menjalankan aplikasi dengan VARIN_SMOKE_TEST=1. Di mode itu aplikasi
membangun SELURUH GUI tanpa mainloop, membuka 7 halaman, menggambar live
wallpaper, mengganti bahasa EN -> ID -> EN, lalu menutup rapi dan menulis
laporan JSON (langkah + error). Skrip ini hanya menjalankan proses tersebut,
membaca laporannya, dan menerjemahkannya jadi exit code:

    0  semua langkah lulus                          -> GUI sehat
    0  gagal karena lingkungan (runner tanpa display) -> ::warning::
    1  gagal karena aplikasi (crash / exe rusak)      -> ::error::

Tanpa laporan sama sekali berarti aplikasi mati sebelum sempat membangun GUI —
persis bug "exe tanpa customtkinter" yang dulu lolos dari build.

Pemakaian:
    python tools/smoke_gui.py --source                        # periksa UI dari source
    python tools/smoke_gui.py --exe dist/Varin-Sniper.exe     # periksa exe hasil build
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXE = os.path.join("dist", "Varin-Sniper.exe")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Smoke test GUI Varin Sniper.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--source", action="store_true",
                        help="jalankan dari source: python varin_sniper.py")
    target.add_argument("--exe", default=None,
                        help=f"path exe hasil build (default: {DEFAULT_EXE})")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="batas waktu dalam detik (default: 120)")
    parser.add_argument("--report", default=None,
                        help="path laporan JSON (default: file sementara)")
    return parser.parse_args(argv)


def _print_report(report: dict) -> None:
    mode = "frozen" if report.get("frozen") else "source"
    print(f"[smoke] mode={mode} python={report.get('python')} "
          f"durasi={report.get('duration_s')}s")
    for step in report.get("steps", []):
        flag = "ok  " if step.get("ok") else "FAIL"
        detail = step.get("detail") or step.get("error") or ""
        millis = step.get("ms", 0) or 0
        print(f"[smoke] {flag} {str(step.get('step', '?')):<12} {millis:>8.1f} ms  {detail}")


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.source:
        entry = os.path.join(REPO_ROOT, "varin_sniper.py")
        command = [sys.executable, entry]
    else:
        entry = args.exe or DEFAULT_EXE
        if not os.path.isabs(entry):
            entry = os.path.join(REPO_ROOT, entry)
        command = [entry]

    if not os.path.exists(entry):
        print(f"::error::tidak ada file yang bisa dijalankan: {entry}")
        if not args.source:
            print("::error::build dulu: pyinstaller --clean --noconfirm Varin-Sniper.spec")
        return 1

    report_path = args.report or os.path.join(tempfile.gettempdir(),
                                              "varin_sniper_smoke.json")
    report_path = os.path.abspath(report_path)
    try:
        os.remove(report_path)
    except OSError:
        pass

    env = os.environ.copy()
    env["VARIN_SMOKE_TEST"] = "1"
    env["VARIN_SMOKE_REPORT"] = report_path
    env.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"[smoke] menjalankan {'source' if args.source else 'exe'}: {entry}")
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(command, cwd=REPO_ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"::error::gagal menjalankan {entry}: {exc}")
        return 1

    timed_out = False
    try:
        output, _ = proc.communicate(timeout=max(10.0, float(args.timeout)))
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        output, _ = proc.communicate()
    elapsed = time.perf_counter() - started

    for line in (output or "").splitlines()[-40:]:
        print(f"    | {line}")

    if timed_out:
        print(f"::error::GUI tidak selesai dalam {args.timeout:.0f}s - proses dihentikan "
              "(jendela kemungkinan menggantung saat dibangun).")
        return 1

    if not os.path.exists(report_path):
        print(f"::error::aplikasi keluar dengan kode {proc.returncode} tanpa menulis laporan "
              f"({report_path}) - GUI gagal dibuka sejak awal.")
        return 1

    try:
        with open(report_path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"::error::laporan tidak bisa dibaca ({report_path}): {exc}")
        return 1

    _print_report(report)
    print(f"[smoke] exit={proc.returncode} durasi proses={elapsed:.1f}s")

    if report.get("ok"):
        print("[smoke] LULUS: GUI terbuka, semua halaman, wallpaper, dan pergantian "
              "bahasa berjalan tanpa error.")
        return 0

    errors = report.get("errors") or ["(tanpa detail)"]
    if report.get("environmental"):
        print("::warning::GUI tidak bisa diuji di lingkungan ini (tanpa display): "
              + "; ".join(errors))
        return 0

    print("::error::GUI gagal diuji: " + "; ".join(errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
