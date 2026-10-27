#!/usr/bin/env python3
"""
Varin Sniper — icon generator (100% stdlib, tanpa Pillow).

Menghasilkan:
  assets/icon.png              256x256 ikon aplikasi
  assets/icon.ico              multi-size (16,24,32,48,64,128,256) untuk .exe
  assets/logo.png              128x128 logo sidebar (transparan)
  assets/icons/nav_*.png       ikon navigasi 24px  (varian "hi" & "dim")
  assets/icons/act_*.png       ikon tombol 18px    (varian "hi", "dim", "ink")

Semua ikon digambar prosedural sebagai vektor (SDF) lalu di-supersample 2-4x
sehingga tepinya halus tanpa perlu file gambar eksternal.

Jalankan dari root repo:  python tools/make_icons.py
"""
from __future__ import annotations

import math
import os
import struct
import sys
import zlib
from typing import Callable, Dict, List, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ui import theme as T  # noqa: E402  (palette saja; theme tidak impor ctk di top-level)

Color = Tuple[float, float, float]
ColorFn = Callable[[float, float], Color]


def _rgb(color: str) -> Color:
    return T.to_rgb(color)


def _mixf(a: str, b: str, t: float) -> Color:
    return T.to_rgb(T.mix(a, b, t))


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _b(v: float) -> int:
    return max(0, min(255, int(round(v * 255.0))))


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    pax, pay = px - ax, py - ay
    bax, bay = bx - ax, by - ay
    denom = bax * bax + bay * bay
    h = 0.0 if denom <= 0.0 else max(0.0, min(1.0, (pax * bax + pay * bay) / denom))
    return math.hypot(pax - bax * h, pay - bay * h)


# --------------------------------------------------------------------------- #
# Primitif SDF (semua koordinat unit 0..1, y ke bawah)
# --------------------------------------------------------------------------- #
class Shape:
    def __init__(self, color, alpha: float = 1.0, stroke: float = 0.0):
        self.color = color
        self.alpha = float(alpha)
        self.stroke = float(stroke)

    def rgb_at(self, u: float, v: float) -> Color:
        c = self.color
        if callable(c):
            return c(u, v)
        return c if isinstance(c, tuple) else _rgb(c)

    def bounds(self) -> Tuple[float, float, float, float]:
        return (0.0, 0.0, 1.0, 1.0)

    def _apply_stroke(self, d: float, S: int) -> float:
        if self.stroke > 0.0:
            return abs(d) - self.stroke * S / 2.0
        return d

    def dist(self, x: float, y: float, S: int) -> float:  # pragma: no cover - abstract
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, cx, cy, r, color, alpha: float = 1.0):
        super().__init__(color, alpha)
        self.cx, self.cy, self.r = cx, cy, r

    def bounds(self):
        return (self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r)

    def dist(self, x, y, S):
        return math.hypot(x - self.cx * S, y - self.cy * S) - self.r * S


class Ring(Shape):
    def __init__(self, cx, cy, r, w, color, alpha: float = 1.0):
        super().__init__(color, alpha)
        self.cx, self.cy, self.r, self.w = cx, cy, r, w

    def bounds(self):
        pad = self.r + self.w
        return (self.cx - pad, self.cy - pad, self.cx + pad, self.cy + pad)

    def dist(self, x, y, S):
        return abs(math.hypot(x - self.cx * S, y - self.cy * S) - self.r * S) - self.w * S / 2.0


class Arc(Shape):
    """Potongan ring antara sudut a0..a1 derajat (matematis, y ke atas)."""

    def __init__(self, cx, cy, r, w, a0, a1, color, alpha: float = 1.0):
        super().__init__(color, alpha)
        self.cx, self.cy, self.r, self.w = cx, cy, r, w
        self.a0, self.a1 = a0 % 360.0, a1 % 360.0

    def bounds(self):
        pad = self.r + self.w
        return (self.cx - pad, self.cy - pad, self.cx + pad, self.cy + pad)

    def _inside(self, ang: float) -> bool:
        if self.a0 <= self.a1:
            return self.a0 <= ang <= self.a1
        return ang >= self.a0 or ang <= self.a1

    def dist(self, x, y, S):
        dx, dy = x - self.cx * S, y - self.cy * S
        rho = math.hypot(dx, dy)
        band = abs(rho - self.r * S) - self.w * S / 2.0
        ang = math.degrees(math.atan2(-dy, dx)) % 360.0
        if self._inside(ang):
            return band
        best = 1e9
        for edge in (self.a0, self.a1):
            ex = self.r * S * math.cos(math.radians(edge))
            ey = -self.r * S * math.sin(math.radians(edge))
            best = min(best, math.hypot(dx - ex, dy - ey) - self.w * S / 2.0)
        return best


class EllipseRing(Shape):
    def __init__(self, cx, cy, rx, ry, w, color, alpha: float = 1.0):
        super().__init__(color, alpha)
        self.cx, self.cy, self.rx, self.ry, self.w = cx, cy, rx, ry, w

    def bounds(self):
        return (self.cx - self.rx - self.w, self.cy - self.ry - self.w,
                self.cx + self.rx + self.w, self.cy + self.ry + self.w)

    def dist(self, x, y, S):
        dx = (x - self.cx * S) / (self.rx * S)
        dy = (y - self.cy * S) / (self.ry * S)
        k = math.hypot(dx, dy) - 1.0
        scale = min(self.rx, self.ry) * S
        return abs(k * scale) - self.w * S / 2.0


class Line(Shape):
    def __init__(self, x1, y1, x2, y2, w, color, alpha: float = 1.0):
        super().__init__(color, alpha)
        self.x1, self.y1, self.x2, self.y2, self.w = x1, y1, x2, y2, w

    def bounds(self):
        pad = self.w
        return (min(self.x1, self.x2) - pad, min(self.y1, self.y2) - pad,
                max(self.x1, self.x2) + pad, max(self.y1, self.y2) + pad)

    def dist(self, x, y, S):
        return _seg_dist(x, y, self.x1 * S, self.y1 * S, self.x2 * S, self.y2 * S) - self.w * S / 2.0


class RBox(Shape):
    def __init__(self, cx, cy, hw, hh, r, color, alpha: float = 1.0, stroke: float = 0.0):
        super().__init__(color, alpha, stroke)
        self.cx, self.cy, self.hw, self.hh, self.r = cx, cy, hw, hh, r

    def bounds(self):
        pad = self.r + self.stroke
        return (self.cx - self.hw - pad, self.cy - self.hh - pad,
                self.cx + self.hw + pad, self.cy + self.hh + pad)

    def dist(self, x, y, S):
        rr = self.r * S
        px = abs(x - self.cx * S) - self.hw * S + rr
        py = abs(y - self.cy * S) - self.hh * S + rr
        d = math.hypot(max(px, 0.0), max(py, 0.0)) + min(max(px, py), 0.0) - rr
        return self._apply_stroke(d, S)


class Poly(Shape):
    def __init__(self, pts: Sequence[Tuple[float, float]], color, alpha: float = 1.0,
                 stroke: float = 0.0):
        super().__init__(color, alpha, stroke)
        self.pts = list(pts)

    def bounds(self):
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        pad = self.stroke + 0.01
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def dist(self, x, y, S):
        pts = [(px * S, py * S) for px, py in self.pts]
        n = len(pts)
        inside = False
        best = 1e9
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                x_cross = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
                if x < x_cross:
                    inside = not inside
            best = min(best, _seg_dist(x, y, xi, yi, xj, yj))
            j = i
        d = -best if inside else best
        return self._apply_stroke(d, S)


def glow(cx: float, cy: float, r: float, color: str, layers: int = 5,
         alpha: float = 0.075, spread: float = 0.26) -> List[Shape]:
    out: List[Shape] = []
    for i in range(layers, 0, -1):
        out.append(Circle(cx, cy, r + spread * (i / layers), color, alpha))
    return out


# --------------------------------------------------------------------------- #
# Rasterizer + writer
# --------------------------------------------------------------------------- #
def render(size: int, shapes: Sequence[Shape], ss: int = 4) -> List[bytes]:
    S = size * ss
    R = [0.0] * (S * S)
    G = [0.0] * (S * S)
    B = [0.0] * (S * S)
    A = [0.0] * (S * S)

    for sh in shapes:
        if sh.alpha <= 0.0:
            continue
        x0, y0, x1, y1 = sh.bounds()
        ix0 = max(0, int(x0 * S))
        ix1 = min(S - 1, int(x1 * S) + 1)
        iy0 = max(0, int(y0 * S))
        iy1 = min(S - 1, int(y1 * S) + 1)
        for py_i in range(iy0, iy1 + 1):
            py = py_i + 0.5
            base = py_i * S
            for px_i in range(ix0, ix1 + 1):
                d = sh.dist(px_i + 0.5, py, S)
                if d >= 0.5:
                    continue
                cov = 1.0 if d <= -0.5 else (0.5 - d)
                cov *= sh.alpha
                if cov <= 0.0:
                    continue
                i = base + px_i
                keep = 1.0 - cov
                cr, cg, cb = sh.rgb_at((px_i + 0.5) / S, py / S)
                R[i] = cr * cov + R[i] * keep
                G[i] = cg * cov + G[i] * keep
                B[i] = cb * cov + B[i] * keep
                A[i] = cov + A[i] * keep

    rows: List[bytes] = []
    n = float(ss * ss)
    for oy in range(size):
        row = bytearray(size * 4)
        for ox in range(size):
            sr = sg = sb = sa = 0.0
            for sy in range(ss):
                base = (oy * ss + sy) * S + ox * ss
                for sx in range(ss):
                    i = base + sx
                    sr += R[i]
                    sg += G[i]
                    sb += B[i]
                    sa += A[i]
            if sa > 1e-6:
                row[ox * 4 + 0] = _b(sr / sa)
                row[ox * 4 + 1] = _b(sg / sa)
                row[ox * 4 + 2] = _b(sb / sa)
            row[ox * 4 + 3] = _b(sa / n)
        rows.append(bytes(row))
    return rows


def write_png(path: str, size: int, rows: Sequence[bytes]) -> None:
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(png)


def _bmp_blob(size: int, rows: Sequence[bytes]) -> bytes:
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
    xor = bytearray()
    for y in range(size - 1, -1, -1):
        row = rows[y]
        for x in range(size):
            i = x * 4
            xor += bytes((row[i + 2], row[i + 1], row[i], row[i + 3]))
    stride = ((size + 31) // 32) * 4
    return header + bytes(xor) + bytes(stride * size)


def write_ico(path: str, entries: Sequence[Tuple[int, Sequence[bytes]]]) -> None:
    count = len(entries)
    directory = b""
    blobs = b""
    offset = 6 + 16 * count
    for size, rows in entries:
        blob = _bmp_blob(size, rows)
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, count) + directory + blobs)


# --------------------------------------------------------------------------- #
# Definisi ikon
# --------------------------------------------------------------------------- #
PALETTES: Dict[str, Dict[str, object]] = {
    "hi": {"main": T.ACCENT_3, "soft": T.ACCENT, "glow": T.PLASMA, "track": "#4a3480",
           "ink": T.INK, "alpha": 1.0},
    "dim": {"main": "#8d7ac2", "soft": "#6d55a8", "glow": "#3a2170", "track": "#33265a",
            "ink": T.INK, "alpha": 1.0},
    "ink": {"main": T.INK, "soft": T.INK, "glow": T.INK, "track": "#3b2a63",
            "ink": T.INK, "alpha": 0.92},
}


def _bolt(c) -> List[Shape]:
    return glow(0.5, 0.5, 0.22, str(c["glow"]), 3, 0.05) + [
        Poly([(0.58, 0.05), (0.24, 0.55), (0.45, 0.55), (0.38, 0.95), (0.76, 0.44), (0.53, 0.44)],
             c["main"], float(c["alpha"])),
    ]


def _checker(c) -> List[Shape]:
    m = c["main"]
    return glow(0.5, 0.5, 0.24, str(c["glow"]), 3, 0.05) + [
        Ring(0.5, 0.5, 0.30, 0.055, m),
        Circle(0.5, 0.5, 0.058, m),
        Line(0.5, 0.05, 0.5, 0.17, 0.055, m),
        Line(0.5, 0.83, 0.5, 0.95, 0.055, m),
        Line(0.05, 0.5, 0.17, 0.5, 0.055, m),
        Line(0.83, 0.5, 0.95, 0.5, 0.055, m),
    ]


def _user(c) -> List[Shape]:
    m = c["main"]
    return [
        Circle(0.5, 0.32, 0.17, m),
        Arc(0.5, 0.88, 0.31, 0.062, 0.0, 180.0, m),
    ]


def _shield(c) -> List[Shape]:
    m, ink = c["main"], c["ink"]
    return glow(0.5, 0.5, 0.26, str(c["glow"]), 3, 0.045) + [
        Poly([(0.5, 0.04), (0.9, 0.19), (0.9, 0.5), (0.5, 0.96), (0.1, 0.5), (0.1, 0.19)], m),
        Line(0.34, 0.5, 0.45, 0.61, 0.075, ink),
        Line(0.45, 0.61, 0.68, 0.35, 0.075, ink),
    ]


def _clock(c) -> List[Shape]:
    m = c["main"]
    return [
        Ring(0.5, 0.5, 0.37, 0.055, m),
        Line(0.5, 0.5, 0.5, 0.25, 0.06, m),
        Line(0.5, 0.5, 0.69, 0.6, 0.055, m),
        Circle(0.5, 0.5, 0.05, m),
    ]


def _sliders(c) -> List[Shape]:
    m, track = c["main"], c["track"]
    return [
        Line(0.12, 0.27, 0.88, 0.27, 0.052, track),
        Line(0.12, 0.5, 0.88, 0.5, 0.052, track),
        Line(0.12, 0.73, 0.88, 0.73, 0.052, track),
        Circle(0.35, 0.27, 0.1, m),
        Circle(0.65, 0.5, 0.1, m),
        Circle(0.42, 0.73, 0.1, m),
    ]


def _bars(c) -> List[Shape]:
    m = c["main"]
    return [
        RBox(0.24, 0.77, 0.085, 0.15, 0.03, m),
        RBox(0.5, 0.68, 0.085, 0.24, 0.03, m),
        RBox(0.76, 0.58, 0.085, 0.34, 0.03, m),
    ]


def _play(c) -> List[Shape]:
    return glow(0.56, 0.5, 0.2, str(c["glow"]), 2, 0.05) + [
        Poly([(0.3, 0.13), (0.88, 0.5), (0.3, 0.87)], c["main"], float(c["alpha"])),
    ]


def _stop(c) -> List[Shape]:
    return [RBox(0.5, 0.5, 0.33, 0.33, 0.09, c["main"], float(c["alpha"]))]


def _save(c) -> List[Shape]:
    m = c["main"]
    return [
        RBox(0.5, 0.5, 0.42, 0.42, 0.11, m, stroke=0.055),
        RBox(0.5, 0.68, 0.21, 0.15, 0.03, m),
        RBox(0.5, 0.21, 0.17, 0.09, 0.03, m),
    ]


def _refresh(c) -> List[Shape]:
    m = c["main"]
    return [
        Arc(0.5, 0.5, 0.33, 0.06, 40.0, 320.0, m),
        Poly([(0.6, 0.2), (0.9, 0.26), (0.7, 0.48)], m),
    ]


def _export(c) -> List[Shape]:
    m = c["main"]
    return [
        RBox(0.5, 0.68, 0.4, 0.25, 0.09, m, stroke=0.055),
        Line(0.5, 0.1, 0.5, 0.48, 0.06, m),
        Poly([(0.32, 0.3), (0.5, 0.07), (0.68, 0.3)], m),
    ]


def _trash(c) -> List[Shape]:
    m, ink = c["main"], c["ink"]
    return [
        Line(0.12, 0.22, 0.88, 0.22, 0.058, m),
        Line(0.38, 0.12, 0.62, 0.12, 0.058, m),
        Poly([(0.19, 0.3), (0.81, 0.3), (0.72, 0.93), (0.28, 0.93)], m),
        Line(0.41, 0.44, 0.42, 0.8, 0.048, ink),
        Line(0.59, 0.44, 0.58, 0.8, 0.048, ink),
    ]


def _search(c) -> List[Shape]:
    m = c["main"]
    return [
        Ring(0.43, 0.43, 0.28, 0.06, m),
        Line(0.65, 0.65, 0.89, 0.89, 0.065, m),
    ]


def _folder(c) -> List[Shape]:
    return [
        Poly([(0.05, 0.2), (0.38, 0.2), (0.49, 0.33), (0.95, 0.33), (0.95, 0.85), (0.05, 0.85)],
             c["main"], float(c["alpha"])),
    ]


def _key(c) -> List[Shape]:
    m = c["main"]
    return [
        Ring(0.33, 0.5, 0.17, 0.06, m),
        Line(0.5, 0.5, 0.92, 0.5, 0.06, m),
        Line(0.72, 0.5, 0.72, 0.69, 0.06, m),
        Line(0.86, 0.5, 0.86, 0.65, 0.06, m),
    ]


def _plus(c) -> List[Shape]:
    m = c["main"]
    return [
        RBox(0.5, 0.5, 0.37, 0.055, 0.05, m),
        RBox(0.5, 0.5, 0.055, 0.37, 0.05, m),
    ]


def _globe(c) -> List[Shape]:
    m = c["main"]
    return [
        Ring(0.5, 0.5, 0.38, 0.055, m),
        EllipseRing(0.5, 0.5, 0.17, 0.38, 0.048, m),
        Line(0.12, 0.5, 0.88, 0.5, 0.05, m),
    ]


def _sparkle(c) -> List[Shape]:
    m = c["main"]
    return glow(0.5, 0.5, 0.2, str(c["glow"]), 3, 0.05) + [
        Poly([(0.5, 0.05), (0.6, 0.4), (0.95, 0.5), (0.6, 0.6),
              (0.5, 0.95), (0.4, 0.6), (0.05, 0.5), (0.4, 0.4)], m),
        Circle(0.8, 0.2, 0.075, m, 0.9),
    ]


def _official(c) -> List[Shape]:
    """Ikon untuk tab History (database/arsip)."""
    m = c["main"]
    return [
        EllipseRing(0.5, 0.24, 0.34, 0.12, 0.05, m),
        Line(0.16, 0.24, 0.16, 0.76, 0.05, m),
        Line(0.84, 0.24, 0.84, 0.76, 0.05, m),
        Arc(0.5, 0.76, 0.34, 0.05, 180.0, 360.0, m),
        Arc(0.5, 0.5, 0.34, 0.045, 180.0, 360.0, m, 0.75),
    ]


NAV_ICONS = {
    "checker": _checker,
    "sniper": _bolt,
    "accounts": _user,
    "proxies": _shield,
    "history": _official,
    "settings": _sliders,
    "stats": _bars,
}

ACT_ICONS = {
    # ikon aksi
    "play": _play,
    "stop": _stop,
    "save": _save,
    "refresh": _refresh,
    "export": _export,
    "trash": _trash,
    "search": _search,
    "folder": _folder,
    "key": _key,
    "plus": _plus,
    "globe": _globe,
    "sparkle": _sparkle,
    "clock": _clock,
    # dipakai juga oleh kartu/heading supaya ikonnya konsisten dengan navigasi
    "checker": _checker,
    "sniper": _bolt,
    "accounts": _user,
    "proxies": _shield,
    "history": _official,
    "settings": _sliders,
    "stats": _bars,
}


# --------------------------------------------------------------------------- #
# App icon + logo
# --------------------------------------------------------------------------- #
def _hex_points(cx: float, cy: float, r: float, rotate: float = 0.0) -> List[Tuple[float, float]]:
    pts = []
    for i in range(6):
        ang = math.radians(60 * i + rotate)
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _app_icon_shapes() -> List[Shape]:
    def bg(u: float, v: float) -> Color:
        return _mixf(T.ICON_TOP, T.ICON_BOTTOM, _clamp01(0.15 + 0.85 * (0.45 * u + 0.75 * v)))

    def mark(u: float, v: float) -> Color:
        return _mixf(T.ICON_MARK_TOP, T.ICON_MARK_BOTTOM, _clamp01((v - 0.22) / 0.5))

    shapes: List[Shape] = [
        RBox(0.5, 0.5, 0.47, 0.47, 0.22, bg),
        Circle(0.5, 0.56, 0.42, "#000000", 0.18),
    ]
    # grid halus (kesan panel 3D)
    for frac in (0.34, 0.66):
        shapes.append(Line(frac, 0.08, frac, 0.92, 0.006, "#ffffff", 0.05))
        shapes.append(Line(0.08, frac, 0.92, frac, 0.006, "#ffffff", 0.05))
    shapes += glow(0.5, 0.54, 0.18, "#b366ff", 7, 0.085, 0.3)
    # hexagon + reticle
    shapes += [
        Poly(_hex_points(0.5, 0.54, 0.40, 30.0), "#c9a2ff", 0.5, stroke=0.016),
        Ring(0.5, 0.54, 0.29, 0.014, "#e7d3ff", 0.45),
        Line(0.5, 0.20, 0.5, 0.28, 0.02, "#e7d3ff", 0.5),
        Line(0.5, 0.80, 0.5, 0.88, 0.02, "#e7d3ff", 0.5),
        Line(0.16, 0.54, 0.24, 0.54, 0.02, "#e7d3ff", 0.5),
        Line(0.76, 0.54, 0.84, 0.54, 0.02, "#e7d3ff", 0.5),
        # monogram V dengan gradient
        Line(0.31, 0.32, 0.5, 0.76, 0.135, mark),
        Line(0.69, 0.32, 0.5, 0.76, 0.135, mark),
        # bevel highlight + shadow
        RBox(0.5, 0.5, 0.47, 0.47, 0.22, "#ffffff", 0.16, stroke=0.012),
        RBox(0.5, 0.5, 0.5, 0.5, 0.24, "#000000", 0.22, stroke=0.02),
    ]
    return shapes


def _logo_shapes() -> List[Shape]:
    def mark(u: float, v: float) -> Color:
        return _mixf(T.ICON_MARK_TOP, T.ICON_MARK_BOTTOM, _clamp01((v - 0.2) / 0.55))

    shapes: List[Shape] = glow(0.5, 0.5, 0.24, "#8b2be2", 6, 0.07, 0.3)
    shapes += [
        Ring(0.5, 0.5, 0.42, 0.03, "#a983f0", 0.85),
        Poly(_hex_points(0.5, 0.5, 0.33, 30.0), "#c9a2ff", 0.75, stroke=0.028),
        Line(0.5, 0.06, 0.5, 0.16, 0.032, "#e2c9ff"),
        Line(0.5, 0.84, 0.5, 0.94, 0.032, "#e2c9ff"),
        Line(0.06, 0.5, 0.16, 0.5, 0.032, "#e2c9ff"),
        Line(0.84, 0.5, 0.94, 0.5, 0.032, "#e2c9ff"),
        Line(0.34, 0.33, 0.5, 0.7, 0.115, mark),
        Line(0.66, 0.33, 0.5, 0.7, 0.115, mark),
    ]
    return shapes


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _assets_dir(*parts: str) -> str:
    return os.path.join(ROOT, "assets", *parts)


def build() -> List[str]:
    written: List[str] = []
    icons_dir = _assets_dir("icons")

    # app icon 256 + png
    app_rows = render(256, _app_icon_shapes(), ss=2)
    write_png(_assets_dir("icon.png"), 256, app_rows)
    written.append("assets/icon.png")

    ico_entries: List[Tuple[int, Sequence[bytes]]] = []
    for size, ss in ((16, 4), (24, 4), (32, 4), (48, 4), (64, 4), (128, 2), (256, 2)):
        ico_entries.append((size, render(size, _app_icon_shapes(), ss=ss)))
    write_ico(_assets_dir("icon.ico"), ico_entries)
    written.append("assets/icon.ico")

    write_png(_assets_dir("logo.png"), 128, render(128, _logo_shapes(), ss=3))
    written.append("assets/logo.png")
    write_png(_assets_dir("logo_small.png"), 64, render(64, _logo_shapes(), ss=4))
    written.append("assets/logo_small.png")

    for name, builder in NAV_ICONS.items():
        for variant in ("hi", "dim"):
            rows = render(24, builder(PALETTES[variant]), ss=4)
            path = os.path.join(icons_dir, f"nav_{name}_{variant}.png")
            write_png(path, 24, rows)
            written.append(f"assets/icons/nav_{name}_{variant}.png")

    for name, builder in ACT_ICONS.items():
        for variant in ("hi", "dim", "ink"):
            rows = render(18, builder(PALETTES[variant]), ss=4)
            path = os.path.join(icons_dir, f"act_{name}_{variant}.png")
            write_png(path, 18, rows)
            written.append(f"assets/icons/act_{name}_{variant}.png")

    return written


def main() -> int:
    written = build()
    total = 0
    for rel in written:
        total += os.path.getsize(os.path.join(ROOT, rel))
    print(f"[icons] {len(written)} file ditulis, total {total / 1024:.1f} KB")
    for rel in ("assets/icon.png", "assets/icon.ico", "assets/logo.png", "assets/logo_small.png"):
        print(f"        {rel:<20} {os.path.getsize(os.path.join(ROOT, rel)) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
