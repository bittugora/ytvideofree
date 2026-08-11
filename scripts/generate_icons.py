"""Generate ytvideofree PWA icons and the social/OG banner using only the stdlib.

Usage:  python scripts/generate_icons.py
Output: static/icons/{icon-192,icon-512,maskable-512,apple-touch-icon,favicon-32}.png
        static/og-image.png (1200x630)
"""

import struct
import zlib
from pathlib import Path

TEAL = (15, 118, 110)
WHITE = (255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"
OG_PATH = Path(__file__).resolve().parent.parent / "static" / "og-image.png"
OG_WIDTH, OG_HEIGHT = 1200, 630


def write_png(path: Path, width: int, height: int, draw) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type 0 (None)
        for x in range(width):
            r, g, b, a = draw(x, y, width, height)
            rows += bytes((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def point_in_triangle(px: float, py: float, a, b, c) -> bool:
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sign((px, py), a, b)
    d2 = sign((px, py), b, c)
    d3 = sign((px, py), c, a)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def rounded_rect(px: float, py: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if px < x0 or px > x1 or py < y0 or py > y1:
        return False
    cx = min(max(px, x0 + r), x1 - r)
    cy = min(max(py, y0 + r), y1 - r)
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy <= r * r


def play_triangle(x: float, y: float, s: float) -> bool:
    apex = (0.40 * s, 0.50 * s)
    top = (0.70 * s, 0.36 * s)
    bottom = (0.70 * s, 0.64 * s)
    return point_in_triangle(x, y, apex, top, bottom)


def draw_icon(maskable: bool):
    def draw(x: int, y: int, w: int, h: int) -> tuple:
        s = min(w, h)
        if maskable:
            # Full-bleed background so the icon survives maskable cropping.
            if play_triangle(x + 0.5, y + 0.5, s):
                return (*WHITE, 255)
            return (*TEAL, 255)
        margin = 0.045 * s
        radius = 0.18 * s
        if rounded_rect(x + 0.5, y + 0.5, margin, margin, s - margin, s - margin, radius):
            if play_triangle(x + 0.5, y + 0.5, s):
                return (*WHITE, 255)
            return (*TEAL, 255)
        return TRANSPARENT

    return draw


def draw_og_image(x: int, y: int, w: int, h: int) -> tuple:
    """1200x630 social banner: teal gradient + play triangle + brand mark."""
    top = (15, 118, 110)    # #0f766e
    bottom = (13, 148, 136)  # #0d9488
    t = min(max(y / OG_HEIGHT, 0.0), 1.0)
    bg = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))

    # Brand mark: red rounded square with a small play triangle, top-left.
    mark_size = 120
    mark_x0, mark_y0 = 80, 80
    mark_r = 28
    if rounded_rect(x + 0.5, y + 0.5, mark_x0, mark_y0, mark_x0 + mark_size, mark_y0 + mark_size, mark_r):
        if point_in_triangle(
            x + 0.5 - mark_x0,
            y + 0.5 - mark_y0,
            (0.40 * mark_size, 0.50 * mark_size),
            (0.70 * mark_size, 0.36 * mark_size),
            (0.70 * mark_size, 0.64 * mark_size),
        ):
            return (*WHITE, 255)
        return (223, 63, 50, 255)

    # Large play triangle, center.
    if point_in_triangle(
        x + 0.5,
        y + 0.5,
        (600 - 95, 330 - 55),
        (600 + 85, 330 - 5),
        (600 + 85, 330 + 5),
    ):
        return (*WHITE, 255)

    return (*bg, 255)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = {
        "icon-192.png": (192, draw_icon(maskable=False)),
        "icon-512.png": (512, draw_icon(maskable=False)),
        "maskable-512.png": (512, draw_icon(maskable=True)),
        "apple-touch-icon.png": (180, draw_icon(maskable=False)),
        "favicon-32.png": (32, draw_icon(maskable=False)),
    }
    for name, (size, draw) in specs.items():
        write_png(OUT_DIR / name, size, size, draw)
        print(f"wrote {OUT_DIR / name}")

    write_png(OG_PATH, OG_WIDTH, OG_HEIGHT, draw_og_image)
    print(f"wrote {OG_PATH}")


if __name__ == "__main__":
    main()
