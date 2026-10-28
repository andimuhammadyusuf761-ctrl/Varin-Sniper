#!/usr/bin/env python3
"""Entry point versi web Varin Sniper.

    python run_web.py                 # http://localhost:3000
    python run_web.py --port 8080     # port lain
    python run_web.py --open          # buka browser otomatis

Backend memakai engine yang sama dengan aplikasi desktop (checker multi-source,
scan history SQLite, generator kelangkaan) di atas http.server stdlib — tidak
ada dependensi tambahan di luar requirements.txt.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from webapp.server import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
