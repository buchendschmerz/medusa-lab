"""Render canvases in a truecolor terminal using upper-half-block characters.

Each character cell shows two vertical pixels: the foreground colour paints the
upper half (``▀``) and the background colour the lower half.
"""

from __future__ import annotations

from .canvas import Canvas
from .palette import hex_to_rgb

RESET = "\x1b[0m"


def canvas_to_ansi(canvas: Canvas, background: str = "#000000") -> str:
    rows = canvas.rgb_rows(background)
    if len(rows) % 2:
        rows.append([hex_to_rgb(background)] * canvas.width)
    lines = []
    for top, bottom in zip(rows[0::2], rows[1::2], strict=True):
        parts = []
        last = None
        for (r1, g1, b1), (r2, g2, b2) in zip(top, bottom, strict=True):
            key = (r1, g1, b1, r2, g2, b2)
            if key != last:
                parts.append(f"\x1b[38;2;{r1};{g1};{b1}m\x1b[48;2;{r2};{g2};{b2}m")
                last = key
            parts.append("▀")
        lines.append("".join(parts) + RESET)
    return "\n".join(lines)


def canvas_to_blocks(canvas: Canvas, background: str = "#000000") -> str:
    """Monochrome approximation (for logs without colour support)."""
    shades = " ░▒▓█"
    lines = []
    for row in canvas.rgb_rows(background):
        line = []
        for r, g, b in row:
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            line.append(shades[min(len(shades) - 1, int(lum * len(shades)))])
        lines.append("".join(line).rstrip())
    return "\n".join(lines)
