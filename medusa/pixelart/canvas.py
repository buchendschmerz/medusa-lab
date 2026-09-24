"""A minimal indexed pixel canvas plus an animated scene container."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from .font import GLYPH_HEIGHT, glyph, text_width
from .palette import Color, hex_to_rgb

Sprite = Sequence[str]


class Canvas:
    """A width x height grid of ``#rrggbb`` colours (``None`` = transparent)."""

    __slots__ = ("width", "height", "px")

    def __init__(self, width: int, height: int, fill: Color = None) -> None:
        self.width = width
        self.height = height
        self.px: list[list[Color]] = [[fill] * width for _ in range(height)]

    # ---------------------------------------------------------------- basics
    def copy(self) -> Canvas:
        other = Canvas(self.width, self.height)
        other.px = [row[:] for row in self.px]
        return other

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Canvas) and self.px == other.px

    def __hash__(self) -> int:  # pragma: no cover - canvases are mutable
        return id(self)

    def get(self, x: int, y: int) -> Color:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.px[y][x]
        return None

    def set(self, x: int, y: int, color: Color) -> None:
        if color is not None and 0 <= x < self.width and 0 <= y < self.height:
            self.px[y][x] = color

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            row = self.px[yy]
            for xx in range(max(0, x), min(self.width, x + w)):
                row[xx] = color

    def hline(self, x: int, y: int, w: int, color: Color) -> None:
        self.fill_rect(x, y, w, 1, color)

    def vline(self, x: int, y: int, h: int, color: Color) -> None:
        self.fill_rect(x, y, 1, h, color)

    def outline(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        self.hline(x, y, w, color)
        self.hline(x, y + h - 1, w, color)
        self.vline(x, y, h, color)
        self.vline(x + w - 1, y, h, color)

    def dither_rect(self, x: int, y: int, w: int, h: int, color: Color, phase: int = 0) -> None:
        """Checkerboard fill (classic pixel-art shading)."""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if (xx + yy + phase) % 2 == 0:
                    self.set(xx, yy, color)

    # ---------------------------------------------------------------- sprites
    def blit(self, sprite: Sprite, x: int, y: int, palette: Mapping[str, Color],
             flip: bool = False) -> None:
        for dy, row in enumerate(sprite):
            if flip:
                row = row[::-1]
            for dx, ch in enumerate(row):
                if ch in ".  ":
                    continue
                try:
                    color = palette[ch]
                except KeyError as exc:
                    raise KeyError(f"colour code {ch!r} missing from palette") from exc
                self.set(x + dx, y + dy, color)

    def paste(self, other: Canvas, x: int, y: int) -> None:
        for dy, row in enumerate(other.px):
            for dx, color in enumerate(row):
                if color is not None:
                    self.set(x + dx, y + dy, color)

    def crop(self, x: int, y: int, w: int, h: int) -> Canvas:
        out = Canvas(w, h)
        for dy in range(h):
            for dx in range(w):
                out.px[dy][dx] = self.get(x + dx, y + dy)
        return out

    def text(self, x: int, y: int, text: str, color: Color, *, spacing: int = 1,
             scale: int = 1, shadow: Color = None) -> int:
        """Draw pixel-font text; returns the drawn width."""
        if shadow is not None:
            self.text(x + scale, y + scale, text, shadow, spacing=spacing, scale=scale)
        cx = x
        for ch in text:
            rows = glyph(ch)
            for gy, row in enumerate(rows):
                for gx, bit in enumerate(row):
                    if bit == "#":
                        self.fill_rect(cx + gx * scale, y + gy * scale, scale, scale, color)
            cx += (len(rows[0]) + spacing) * scale
        return text_width(text, spacing, scale)

    def text_center(self, cx: int, y: int, text: str, color: Color, **kw: int) -> int:
        w = text_width(text, kw.get("spacing", 1), kw.get("scale", 1))
        return self.text(cx - w // 2, y, text, color, **kw)  # type: ignore[arg-type]

    @staticmethod
    def text_height(scale: int = 1) -> int:
        return GLYPH_HEIGHT * scale

    # ---------------------------------------------------------------- export
    def rgb_rows(self, background: str = "#000000") -> list[list[tuple[int, int, int]]]:
        bg = hex_to_rgb(background)
        cache: dict[str, tuple[int, int, int]] = {}
        rows = []
        for row in self.px:
            out = []
            for color in row:
                if color is None:
                    out.append(bg)
                else:
                    rgb = cache.get(color)
                    if rgb is None:
                        rgb = cache[color] = hex_to_rgb(color)
                    out.append(rgb)
            rows.append(out)
        return rows

    def colors(self) -> set[str]:
        return {c for row in self.px for c in row if c is not None}


@dataclass
class Layer:
    """An animated rectangle of a scene: ``frames`` are drawn at (x, y)."""

    x: int
    y: int
    frames: list[Canvas]
    frame_ms: int = 450

    @property
    def period_ms(self) -> int:
        return self.frame_ms * len(self.frames)


@dataclass
class TextOverlay:
    """Real (vector) text for the SVG output, e.g. Japanese status messages.

    Coordinates are in scene pixels; the GIF/ANSI outputs skip overlays.
    """

    x: float
    y: float
    text: str
    size: float = 4.0
    color: str = "#f7f3e9"
    anchor: str = "start"  # start | middle | end
    weight: str = "normal"
    max_width: float | None = None
    css_class: str = ""


@dataclass
class Scene:
    """Static background + animated layers + SVG-only text overlays."""

    base: Canvas
    layers: list[Layer] = field(default_factory=list)
    overlays: list[TextOverlay] = field(default_factory=list)
    title: str = ""
    description: str = ""

    @property
    def width(self) -> int:
        return self.base.width

    @property
    def height(self) -> int:
        return self.base.height

    def add(self, x: int, y: int, frames: Iterable[Canvas], frame_ms: int = 450) -> None:
        frames = list(frames)
        if len(frames) == 1:
            self.base.paste(frames[0], x, y)
        elif frames:
            self.layers.append(Layer(x, y, frames, frame_ms))

    def loop_ms(self) -> int:
        """Length of one full animation loop (LCM of the layer periods)."""
        loop = 1
        for layer in self.layers:
            loop = loop * layer.period_ms // math.gcd(loop, layer.period_ms)
        return loop if self.layers else 0

    def frame_at(self, t_ms: int) -> Canvas:
        canvas = self.base.copy()
        for layer in self.layers:
            index = (t_ms // layer.frame_ms) % len(layer.frames)
            canvas.paste(layer.frames[index], layer.x, layer.y)
        return canvas

    def timeline(self, max_frames: int = 24) -> list[tuple[Canvas, int]]:
        """Distinct frames with durations (ms) for GIF export."""
        if not self.layers:
            return [(self.base.copy(), 1000)]
        loop = self.loop_ms()
        tick = self.layers[0].frame_ms
        for layer in self.layers[1:]:
            tick = math.gcd(tick, layer.frame_ms)
        steps = loop // tick
        if steps > max_frames:  # keep GIFs small: sample the loop coarsely
            tick = loop // max_frames
            steps = max_frames
        frames: list[tuple[Canvas, int]] = []
        for i in range(steps):
            frame = self.frame_at(i * tick)
            if frames and frames[-1][0] == frame:
                frames[-1] = (frames[-1][0], frames[-1][1] + tick)
            else:
                frames.append((frame, tick))
        return frames
