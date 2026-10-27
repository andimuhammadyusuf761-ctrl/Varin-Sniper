"""
wallpaper.py — live wallpaper 3D untuk Varin Sniper (pengganti animasi galaxy).

Gambaran: sebuah "vault" wireframe 3D (dua cincin heksagon + inti bercahaya)
yang berputar pelan dengan kedalaman warna (depth fog), ditambah partikel
bintang yang bergerak mendekat kamera. Semua digambar di SATU Canvas dengan
jumlah item yang sudah dibuat sekali di awal, lalu tiap frame hanya
`coords()`/`itemconfigure()` — jadi tidak ada item yang dibuat/dihapus terus
menerus dan CPU tetap rendah.

Anti-lag:
  * target 30 FPS, dengan penyesuaian otomatis (turun ke 20 FPS) kalau frame
    terasa mahal — jadi tidak pernah "menarik" sisa aplikasi.
  * pause otomatis saat jendela tidak fokus / di-minimize.
  * bisa dimatikan total dari Settings/sidebar (0% CPU).
"""
from __future__ import annotations

import math
import random
import time
from typing import List, Optional, Sequence, Tuple

from ui import theme as T

Point3 = Tuple[float, float, float]
Projected = Tuple[float, float, float]  # screen x, screen y, depth


# --------------------------------------------------------------------------- #
# Matematika murni (diuji tanpa display)
# --------------------------------------------------------------------------- #
def rotate_y(points: Sequence[Point3], ang: float) -> List[Point3]:
    ca, sa = math.cos(ang), math.sin(ang)
    return [(x * ca + z * sa, y, -x * sa + z * ca) for x, y, z in points]


def rotate_x(points: Sequence[Point3], ang: float) -> List[Point3]:
    ca, sa = math.cos(ang), math.sin(ang)
    return [(x, y * ca - z * sa, y * sa + z * ca) for x, y, z in points]


def project(points: Sequence[Point3], cx: float, cy: float, fov: float,
            cam_z: float) -> List[Projected]:
    """Proyeksi perspektif sederhana. cam_z = jarak kamera dari origin."""
    out: List[Projected] = []
    for x, y, z in points:
        depth = z + cam_z
        if depth < 0.15:  # di belakang kamera -> hindari distorsi
            depth = 0.15
        k = fov / depth
        out.append((cx + x * k, cy + y * k, depth))
    return out


def depth_color(depth: float, near: float, far: float, color: str) -> str:
    """Warna makin gelap saat makin jauh (depth fog)."""
    span = max(1e-6, far - near)
    t = (depth - near) / span
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return T.mix(color, T.BG, 0.15 + 0.7 * t)


HEX6: List[Tuple[float, float]] = [
    (math.cos(math.radians(60 * i)), math.sin(math.radians(60 * i))) for i in range(6)
]


def vault_edges(inner_scale: float = 0.52) -> List[Tuple[int, int]]:
    """Sisi-sisi vault: ring luar belakang/depan, penyambung, ring dalam, spoke."""
    edges: List[Tuple[int, int]] = []
    for r in (0, 6):                       # dua cincin luar (z -0.42 / +0.42)
        for i in range(6):
            edges.append((r + i, r + (i + 1) % 6))
    for i in range(6):                     # penyambung antar cincin
        edges.append((i, 6 + i))
    for i in range(6):                     # ring dalam
        edges.append((12 + i, 12 + (i + 1) % 6))
    edges += [(0, 13), (2, 15), (4, 17)]   # spoke ke ring dalam (indeks 12..17)
    return edges


def vault_points(inner_scale: float = 0.52) -> List[Point3]:
    pts: List[Point3] = []
    for z in (-0.42, 0.42):
        for c, s in HEX6:
            pts.append((c, s, z))
    for c, s in HEX6:
        pts.append((c * inner_scale, s * inner_scale, 0.0))
    return pts


class LiveWallpaper3D:
    """Wallpaper 3D hemat CPU di atas satu tk.Canvas."""

    def __init__(self, canvas: "object", width: int = 900, height: int = T.HERO_H,
                 enabled: bool = True) -> None:
        self.canvas = canvas
        self.width = max(160, int(width))
        self.height = max(80, int(height))
        self.enabled = bool(enabled)
        self.running = False
        self.paused = False

        self._after_id: Optional[str] = None
        self._angle = 0.0
        self._tilt = 0.28
        self._frame_ms = 33           # ~30 FPS
        self._frame_cost = 0.008      # EMA biaya render (detik)
        self._last = time.perf_counter()
        self._gradient_item: Optional[int] = None
        self._grad_image: Optional[object] = None  # referensi kuat: canvas item tidak menahan objek Python
        self._core_items: List[int] = []
        self._core_phase = 0.0

        self._base_points = vault_points()
        self._edges = vault_edges()
        self._stars = self._make_stars(58)
        self._edge_items: List[int] = []
        self._star_items: List[int] = []

        self._build_items()

    # -- setup -------------------------------------------------------------- #
    def _make_stars(self, count: int) -> List[dict]:
        rnd = random.Random(1337)
        stars = []
        for _ in range(count):
            stars.append({
                "x": rnd.uniform(-1.5, 1.5),
                "y": rnd.uniform(-1.0, 1.0),
                "z": rnd.uniform(-1.3, 1.3),
                "size": rnd.uniform(1.0, 2.4),
                "speed": rnd.uniform(0.0022, 0.0075),
            })
        return stars

    def _build_items(self) -> None:
        cv = self.canvas
        try:
            grad = T.gradient_photo(self.width, self.height, T.PANEL_2, T.BG)
            self._grad_image = grad
            self._gradient_item = cv.create_image(0, 0, anchor="nw", image=grad)  # type: ignore[attr-defined]
            cv.delete("wall")  # type: ignore[attr-defined]
            cv.itemconfigure(self._gradient_item, tags="wall")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            self._gradient_item = None
            grad = None

        # inti bercahaya (3 oval, tidak pernah dibuat ulang)
        for i, radius in enumerate((10, 20, 34)):
            item = cv.create_oval(0, 0, radius, radius, outline="",  # type: ignore[attr-defined]
                                  fill=T.mix(T.BG, T.GLOW, 0.35 - i * 0.09), tags="wall")
            self._core_items.append(item)

        for _ in self._edges:
            item = cv.create_line(0, 0, 1, 1, width=1, fill=T.ACCENT,  # type: ignore[attr-defined]
                                  capstyle="round", tags="wall")
            self._edge_items.append(item)

        for st in self._stars:
            item = cv.create_oval(0, 0, 1, 1, outline="", fill=T.TEXT_3,  # type: ignore[attr-defined]
                                  tags="wall")
            self._star_items.append(item)

        self._layout_static(grad)
        self._render(0.0)

    def _layout_static(self, grad: Optional[object]) -> None:
        if self._gradient_item is not None and grad is not None:
            self.canvas.coords(self._gradient_item, 0, 0)  # type: ignore[attr-defined]

    # -- kontrol ------------------------------------------------------------ #
    def start(self) -> None:
        if not self.enabled or self.running:
            return
        self.running = True
        self.paused = False
        self._last = time.perf_counter()
        self._schedule(self._frame_ms)

    def stop(self) -> None:
        self.running = False
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            self._after_id = None

    def pause(self) -> None:
        if self.running:
            self.paused = True

    def resume(self) -> None:
        self.paused = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self.enabled:
            self.start()
        else:
            self.stop()

    def configure_size(self, width: int, height: int) -> None:
        width = max(160, int(width))
        height = max(80, int(height))
        if (width, height) == (self.width, self.height):
            return
        self.width, self.height = width, height
        try:
            grad = T.gradient_photo(width, height, T.PANEL_2, T.BG)
            self._grad_image = grad
            if self._gradient_item is not None:
                self.canvas.itemconfigure(self._gradient_item, image=grad)  # type: ignore[attr-defined]
            self.canvas.coords(self._gradient_item, 0, 0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        self._render(0.0)

    # -- loop --------------------------------------------------------------- #
    def _schedule(self, delay_ms: int) -> None:
        try:
            self._after_id = self.canvas.after(delay_ms, self._tick)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            self.running = False

    def _tick(self) -> None:
        if not self.running:
            return
        if self.paused:
            self._schedule(120)
            return

        t0 = time.perf_counter()
        now = t0
        dt = min(0.12, now - self._last)
        self._last = now
        self._render(dt)
        cost = time.perf_counter() - t0
        self._frame_cost = self._frame_cost * 0.82 + cost * 0.18

        budget = self._frame_ms / 1000.0
        if self._frame_cost > budget * 0.55 and self._frame_ms < 50:
            self._frame_ms += 4
        elif self._frame_cost < budget * 0.18 and self._frame_ms > 30:
            self._frame_ms -= 2
        self._schedule(self._frame_ms)

    # -- render ------------------------------------------------------------- #
    def _render(self, dt: float) -> None:
        cv = self.canvas
        self._angle += dt * 0.5
        self._core_phase += dt * 1.6

        cx = self.width * 0.5
        cy = self.height * 0.54
        fov = min(self.width, self.height) * 0.95
        cam_z = 3.05
        near, far = cam_z - 1.0, cam_z + 1.6

        pts = rotate_x(rotate_y(self._base_points, self._angle), self._tilt)
        proj = project(pts, cx, cy, fov, cam_z)

        try:
            for item, (a, b) in zip(self._edge_items, self._edges):
                x1, y1, d1 = proj[a]
                x2, y2, d2 = proj[b]
                depth = (d1 + d2) * 0.5
                cv.coords(item, x1, y1, x2, y2)
                cv.itemconfigure(item, fill=depth_color(depth, near, far, T.ACCENT_3))
        except Exception:  # noqa: BLE001
            self.running = False
            return

        # stars: bergerak mendekat kamera, lalu kembali ke kejauhan
        if not T.EFFECTS:
            for item in list(self._star_items) + list(self._core_items):
                cv.coords(item, -20, -20, -19, -19)
            return

        for st, item in zip(self._stars, self._star_items):
            st["z"] -= st["speed"] * max(0.4, dt * 30.0)
            if st["z"] < -1.3:
                st["z"] = 1.3
            px, py, depth = project([(st["x"], st["y"], st["z"])], cx, cy, fov, cam_z)[0]
            if depth <= near - 0.5:
                cv.coords(item, -10, -10, -9, -9)
                continue
            size = st["size"] * (1.8 - min(1.0, (depth - near) / max(0.2, far - near)))
            cv.coords(item, px, py, px + size, py + size)
            cv.itemconfigure(item, fill=depth_color(depth, near, far, T.ACCENT_2))

        pulse = 0.5 + 0.5 * math.sin(self._core_phase)
        for i, item in enumerate(self._core_items):
            base = 16 + i * 17 + pulse * (5 + i * 3)
            cv.coords(item, cx - base, cy - base, cx + base, cy + base)
