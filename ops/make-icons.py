#!/usr/bin/env python3
"""生成 PWA 图标（纯 stdlib，不引入 Pillow 等依赖）。

用法：``python3 ops/make-icons.py`` → 写 ``static/icons/*.png``。

图形：蓝色渐变圆角底 + 白色「天窗」（屋顶 + 四格窗），2×2 超采样抗锯齿。
这是可重跑的源脚本：改配色/图形改这里，别手改 PNG。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "icons"

# 底色渐变（上 → 下）
TOP = (0x3B, 0x82, 0xF6)
BOTTOM = (0x1D, 0x4E, 0xD8)
WHITE = (0xFF, 0xFF, 0xFF)

ROOF_HALF_WIDTH = 0.038
STROKE = 0.055  # 窗框线宽（单位坐标）
SS = 2  # 每个方向 2 个采样 → 4x 超采样


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = 0.0 if denom == 0 else ((px - ax) * dx + (py - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _in_round_rect(x: float, y: float, radius: float) -> bool:
    if x < 0 or x > 1 or y < 0 or y > 1:
        return False
    cx = min(max(x, radius), 1 - radius)
    cy = min(max(y, radius), 1 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius


def _in_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float) -> bool:
    return x0 <= x <= x1 and y0 <= y <= y1


def _glyph_hit(x: float, y: float) -> bool:
    """白色图形：屋顶两条斜线 + 窗框 + 十字窗棂。"""
    if _seg_dist(x, y, 0.16, 0.40, 0.50, 0.185) <= ROOF_HALF_WIDTH:
        return True
    if _seg_dist(x, y, 0.50, 0.185, 0.84, 0.40) <= ROOF_HALF_WIDTH:
        return True

    ox0, oy0, ox1, oy1 = 0.245, 0.415, 0.755, 0.760
    outer = _in_rect(x, y, ox0, oy0, ox1, oy1)
    inner = _in_rect(x, y, ox0 + STROKE, oy0 + STROKE, ox1 - STROKE, oy1 - STROKE)
    if outer and not inner:
        return True

    # 窗棂：竖中挺 + 横档（在窗洞范围内）
    if _in_rect(x, y, 0.475, oy0 + STROKE, 0.525, oy1 - STROKE):
        return True
    if _in_rect(x, y, ox0 + STROKE, 0.560, ox1 - STROKE, 0.610):
        return True
    return False


def make_png(size: int, *, rounded: bool, glyph_scale: float = 1.0) -> bytes:
    radius = 0.20 if rounded else 0.0
    rows = bytearray()

    for py in range(size):
        rows.append(0)  # PNG 行过滤类型 0（None）
        for px in range(size):
            r_acc = g_acc = b_acc = a_acc = 0
            for sy in range(SS):
                for sx in range(SS):
                    # 像素中心 + 采样偏移
                    x = (px + (sx + 0.5) / SS) / size
                    y = (py + (sy + 0.5) / SS) / size

                    if rounded and not _in_round_rect(x, y, radius):
                        continue  # 圆角外：透明

                    # 渐变底色
                    t = y
                    r = int(TOP[0] + (BOTTOM[0] - TOP[0]) * t)
                    g = int(TOP[1] + (BOTTOM[1] - TOP[1]) * t)
                    b = int(TOP[2] + (BOTTOM[2] - TOP[2]) * t)

                    # 图形（maskable 时整体缩小到安全区）
                    gx = 0.5 + (x - 0.5) / glyph_scale
                    gy = 0.5 + (y - 0.5) / glyph_scale
                    if 0.0 <= gx <= 1.0 and 0.0 <= gy <= 1.0 and _glyph_hit(gx, gy):
                        r, g, b = WHITE

                    r_acc += r
                    g_acc += g
                    b_acc += b
                    a_acc += 255

            samples = SS * SS
            rows += bytes(
                (
                    r_acc // samples,
                    g_acc // samples,
                    b_acc // samples,
                    a_acc // samples,
                )
            )

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, True, 1.0),
        ("icon-512.png", 512, True, 1.0),
        ("icon-maskable-512.png", 512, False, 0.78),
    ]
    for name, size, rounded, scale in targets:
        path = OUT_DIR / name
        path.write_bytes(make_png(size, rounded=rounded, glyph_scale=scale))
        print(f"written {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
