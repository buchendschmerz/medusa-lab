"""Render a :class:`Scene` to an animated, crisp-edged SVG.

* Pixels are merged into one ``<path>`` per colour (horizontal runs) to keep
  files small.
* Each animated layer is split into the pixels that never change (merged into
  the static background) and per-frame "diff" groups toggled with CSS
  ``@keyframes`` using ``step-end`` timing. SVG CSS animations keep running
  when the file is embedded as an ``<img>`` (e.g. in a GitHub README).
* ``prefers-reduced-motion`` freezes every layer on its first frame.
"""

from __future__ import annotations

from collections import defaultdict
from html import escape

from .canvas import Canvas, Scene, TextOverlay

FONT_STACK = ("'DotGothic16','PixelMplus10','Noto Sans JP','Hiragino Kaku Gothic ProN',"
              "'Yu Gothic','Meiryo',ui-monospace,monospace")


def _runs(canvas: Canvas, mask: set[tuple[int, int]] | None = None,
          dx: int = 0, dy: int = 0) -> dict[str, list[tuple[int, int, int]]]:
    runs: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for y, row in enumerate(canvas.px):
        x = 0
        width = canvas.width
        while x < width:
            color = row[x]
            if color is None or (mask is not None and (x, y) not in mask):
                x += 1
                continue
            start = x
            x += 1
            while x < width and row[x] == color and (mask is None or (x, y) in mask):
                x += 1
            runs[color].append((start + dx, y + dy, x - start))
    return runs


def paths(canvas: Canvas, mask: set[tuple[int, int]] | None = None, dx: int = 0, dy: int = 0) -> str:
    out = []
    for color, runs in sorted(_runs(canvas, mask, dx, dy).items()):
        d = "".join(f"M{x} {y}h{w}v1h-{w}z" for x, y, w in runs)
        out.append(f'<path fill="{color}" d="{d}"/>')
    return "".join(out)


def _keyframes(n: int, i: int) -> str:
    """Frame ``i`` of an ``n``-frame loop is visible during [i/n, (i+1)/n)."""
    start = 100.0 * i / n
    end = 100.0 * (i + 1) / n
    stops = []
    if i > 0:
        stops.append("0%{opacity:0}")
    stops.append(f"{start:.3f}%{{opacity:1}}")
    if i < n - 1:
        stops.append(f"{end:.3f}%{{opacity:0}}")
    stops.append(f"100%{{opacity:{1 if i == n - 1 else 0}}}")
    return f"@keyframes mf{n}_{i}{{{''.join(stops)}}}"


def estimate_text_width(text: str, size: float) -> float:
    """Generous width estimate for system fonts (CJK ~1em, Latin ~0.6em)."""
    width = 0.0
    for ch in text:
        width += size * (1.0 if ord(ch) > 0x2E7F else 0.62)
    return width


def fit_overlay_text(text: str, size: float, max_width: float) -> str:
    if estimate_text_width(text, size) <= max_width:
        return text
    while text and estimate_text_width(text + "…", size) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _overlay(o: TextOverlay) -> str:
    attrs = [f'x="{o.x:g}"', f'y="{o.y:g}"', f'font-size="{o.size:g}"', f'fill="{o.color}"']
    if o.anchor != "start":
        attrs.append(f'text-anchor="{o.anchor}"')
    if o.weight != "normal":
        attrs.append(f'font-weight="{o.weight}"')
    if o.css_class:
        attrs.append(f'class="{o.css_class}"')
    text = fit_overlay_text(o.text, o.size, o.max_width) if o.max_width else o.text
    return f"<text {' '.join(attrs)}>{escape(text)}</text>"


def render_svg(scene: Scene, scale: int = 4, animate: bool = True, background: str | None = None) -> str:
    base = scene.base.copy()
    dynamic_groups: list[tuple[int, int, str]] = []  # (n_frames, index, svg)
    periods: list[int] = []

    for layer in scene.layers:
        frames = layer.frames
        first = frames[0]
        dynamic: set[tuple[int, int]] = set()
        for y in range(first.height):
            for x in range(first.width):
                c0 = first.px[y][x]
                if any(f.px[y][x] != c0 for f in frames[1:]):
                    dynamic.add((x, y))
        # Static part of the layer is folded into the background.
        static_part = first.copy()
        for x, y in dynamic:
            static_part.px[y][x] = None
        base.paste(static_part, layer.x, layer.y)
        if not dynamic:
            continue
        if not animate:
            frame0 = Canvas(first.width, first.height)
            for x, y in dynamic:
                frame0.px[y][x] = first.px[y][x]
            base.paste(frame0, layer.x, layer.y)
            continue
        # Under a dynamic pixel that is transparent in some frame, the background shows.
        n = len(frames)
        for i, frame in enumerate(frames):
            body = paths(frame, dynamic, layer.x, layer.y)
            if body:
                hidden = "" if i == 0 else ' opacity="0"'
                dynamic_groups.append((n, i, f'<g class="mf mf{n}_{i}" '
                                             f'style="animation-duration:{layer.period_ms}ms"{hidden}>{body}</g>'))
        periods.append(layer.period_ms)

    width, height = scene.width * scale, scene.height * scale
    css = [
        "svg{shape-rendering:crispEdges}",
        f"text{{font-family:{FONT_STACK};shape-rendering:auto;dominant-baseline:alphabetic}}",
    ]
    used = sorted({(n, i) for n, i, _ in dynamic_groups})
    if used:
        css.append(".mf{animation-timing-function:step-end;animation-iteration-count:infinite}")
        for n, i in used:
            css.append(f".mf{n}_{i}{{animation-name:mf{n}_{i}}}")
            css.append(_keyframes(n, i))
        css.append("@media (prefers-reduced-motion:reduce){.mf{animation:none!important}}")
    css.append(".blink{animation:blink 1.2s step-end infinite}@keyframes blink{50%{opacity:0}}")
    css.append("@media (prefers-reduced-motion:reduce){.blink{animation:none}}")

    title = escape(scene.title or "Medusa Lab")
    desc = escape(scene.description or "")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {scene.width} {scene.height}" role="img" aria-labelledby="t d">',
        f'<title id="t">{title}</title><desc id="d">{desc}</desc>',
        f"<style>{''.join(css)}</style>",
    ]
    if background:
        parts.append(f'<rect width="{scene.width}" height="{scene.height}" fill="{background}"/>')
    parts.append(f"<g>{paths(base)}</g>")
    parts.extend(svg for _, _, svg in dynamic_groups)
    if scene.overlays:
        parts.append('<g class="overlay">' + "".join(_overlay(o) for o in scene.overlays) + "</g>")
    parts.append("</svg>")
    return "".join(parts) + "\n"
