"""Animated 48x36 room tiles: one per agent (+ the Director's office).

Each builder returns the list of animation frames (full tiles) for an agent in
a given :class:`~medusa.state.AgentState`.
"""

from __future__ import annotations

from collections.abc import Callable

from ..state import AgentState
from . import sprites as sp
from .canvas import Canvas
from .font import fit_text, text_width
from .palette import Color, luminance, palette_for

TILE_W, TILE_H = 48, 36
DESK_Y = 24          # desk top edge
HEAD_X, HEAD_Y = 6, 6  # character head position inside a tile

Patch = dict[tuple[int, int], str]


# ----------------------------------------------------------------------------- helpers
def _patched(sprite: tuple[str, ...], patch: Patch | None) -> tuple[str, ...]:
    if not patch:
        return sprite
    rows = [list(r) for r in sprite]
    for (x, y), ch in patch.items():
        rows[y][x] = ch
    return tuple("".join(r) for r in rows)


def draw_room(c: Canvas, pal: dict[str, Color], *, desk: bool = True) -> None:
    c.fill_rect(0, 0, TILE_W, TILE_H, pal["X"])
    for x in range(3, TILE_W, 8):  # wall panel seams
        c.vline(x, 0, DESK_Y, pal["x"])
    c.hline(0, 0, TILE_W, pal["x"])
    # floor
    c.fill_rect(0, 31, TILE_W, 5, pal["F"])
    for x in range(1, TILE_W, 7):
        c.vline(x, 32, 4, pal["f"])
    c.hline(0, 31, TILE_W, pal["f"])
    if desk:
        c.hline(1, DESK_Y, TILE_W - 2, pal["e"])
        c.fill_rect(1, DESK_Y + 1, TILE_W - 2, 2, pal["d"])
        c.fill_rect(2, DESK_Y + 3, TILE_W - 4, 5, pal["D"])
        c.hline(2, DESK_Y + 3, TILE_W - 4, pal["f"])
        c.fill_rect(3, DESK_Y + 5, 6, 2, pal["f"])  # drawer
        c.set(5, DESK_Y + 5, pal["e"])
        c.vline(3, DESK_Y + 8, 3, pal["F"])
        c.vline(TILE_W - 4, DESK_Y + 8, 3, pal["F"])


def draw_character(c: Canvas, role: str, pal: dict[str, Color], *, x: int = HEAD_X, y: int = HEAD_Y,
                   face: str = "normal", pose: str = "rest") -> None:
    """Head at (x, y); body below; arms according to ``pose``."""
    patch = {
        "normal": None,
        "blink": sp.HEAD_BLINK_PATCH,
        "happy": sp.HEAD_HAPPY_PATCH,
        "worry": sp.HEAD_WORRY_PATCH,
        "look": sp.HEAD_LOOK_RIGHT_PATCH,
    }[face]
    c.blit(sp.BODY, x, y + 12, pal)
    if role == "reviewer":
        c.blit(sp.TIE_RED, x + 5, y + 13, pal)
    c.blit(_patched(sp.HEAD, patch), x, y, pal)
    _accessory(c, role, pal, x, y)
    _arms(c, pal, x, y, pose)


def _accessory(c: Canvas, role: str, pal: dict[str, Color], x: int, y: int) -> None:
    if role == "scout":
        c.blit(sp.HAT_SCOUT, x - 1, y - 3, pal)
    elif role == "analyst":
        c.blit(sp.GLASSES_ROUND, x, y + 6, pal)
    elif role == "coder":
        c.blit(sp.HEADPHONES, x - 1, y - 1, pal)
    elif role == "writer":
        c.blit(sp.BERET, x, y - 2, pal)
    elif role == "reviewer":
        c.blit(sp.GLASSES_ROUND, x, y + 6, {**pal, "K": pal["k"]})


def _hand(c: Canvas, pal: dict[str, Color], hx: int, hy: int) -> None:
    c.set(hx, hy, pal["s"])
    c.set(hx + 1, hy, pal["s"])
    c.set(hx, hy + 1, pal["S"])
    c.set(hx + 1, hy + 1, pal["S"])


def _arms(c: Canvas, pal: dict[str, Color], x: int, y: int, pose: str) -> None:
    body_bottom = y + 18
    if pose == "none":
        return
    if pose == "cheer":
        for side_x in (x - 2, x + 12):
            c.fill_rect(side_x, y + 9, 2, 5, pal["U"])
            c.vline(side_x + (0 if side_x < x else 1), y + 9, 5, pal["u"])
            _hand(c, pal, side_x, y + 7)
        return
    if pose == "think":
        _hand(c, pal, x + 1, DESK_Y - 1)
        c.fill_rect(x + 10, y + 13, 2, 4, pal["U"])
        c.set(x + 10, y + 12, pal["U"])
        _hand(c, pal, x + 9, y + 10)
        return
    left_up = pose in ("type_a", "write_b")
    right_up = pose in ("type_b",)
    lx, rx = x + 1, x + 9
    if pose.startswith("write"):
        rx = x + 10 if pose == "write_a" else x + 12
    if pose == "point":
        rx = x + 13
    _hand(c, pal, lx, DESK_Y - (2 if left_up else 1))
    if pose == "point":
        c.fill_rect(x + 10, body_bottom - 3, 3, 2, pal["U"])
        _hand(c, pal, rx, body_bottom - 4)
    else:
        _hand(c, pal, rx, DESK_Y - (2 if right_up else 1))


def _bubble(c: Canvas, pal: dict[str, Color], x: int, y: int, think: bool = False) -> None:
    c.blit(sp.BUBBLE_THINK if think else sp.BUBBLE, x, y, pal)


def _bubble_dots(c: Canvas, pal: dict[str, Color], x: int, y: int, n: int) -> None:
    for i in range(n):
        c.set(x + 3 + i * 2, y + 3, pal["K"])


def _bubble_text(c: Canvas, pal: dict[str, Color], x: int, y: int, text: str, color: str = "K") -> None:
    c.text_center(x + 5, y + 1, text, pal[color])


def _nameplate(c: Canvas, pal: dict[str, Color], label: str, center: int = 27, max_w: int = 37) -> None:
    """Name plate on the desk front (plate colour ``Z`` = the agent's identity colour)."""
    label = fit_text(label.upper(), max_w - 4)
    w = text_width(label) + 4
    x = center - w // 2
    c.fill_rect(x, DESK_Y + 4, w, 7, pal["Z"])
    c.hline(x, DESK_Y + 4, w, pal["W"])
    c.text(x + 2, DESK_Y + 5, label, pal["K"] if _light(pal["Z"]) else pal["W"])


def _light(color: Color) -> bool:
    return color is not None and luminance(color) > 0.3


def _progress_ticks(progress: float, steps: int) -> int:
    return max(0, min(steps, round(progress * steps)))


# ----------------------------------------------------------------------------- per-agent props
def _bookshelf(c: Canvas, pal: dict[str, Color], pop: int | None = None) -> None:
    x0, y0, w, h = 26, 2, 20, 22
    c.fill_rect(x0, y0, w, h, pal["F"])
    c.outline(x0, y0, w, h, pal["D"])
    colors = "BRYLVOCMbrLYBV"
    for shelf, sy in enumerate((y0 + 7, y0 + 14, y0 + 21)):
        c.hline(x0 + 1, sy, w - 2, pal["d"])
        bx = x0 + 2
        i = shelf * 3
        while bx < x0 + w - 3:
            bw = 2 if (i % 3) else 1
            bh = 5 - (i % 2)
            color = pal[colors[i % len(colors)]]
            lift = 1 if pop is not None and (i % 7) == pop else 0
            c.fill_rect(bx, sy - bh - lift, bw, bh, color)
            c.set(bx, sy - bh - lift + 1, pal["W"])
            bx += bw + 1
            i += 1


def _open_book(c: Canvas, pal: dict[str, Color], x: int, y: int, page: int) -> None:
    c.fill_rect(x, y, 11, 3, pal["W"])
    c.hline(x, y + 3, 11, pal["w"])
    c.vline(x + 5, y, 4, pal["g"])
    for row in range(3):
        c.hline(x + 1, y + row, 3, pal["G"]) if row != 1 else None
        c.hline(x + 7, y + row, 3, pal["G"]) if row != 2 else None
    if page == 1:  # page turning
        c.fill_rect(x + 5, y - 3, 3, 3, pal["W"])
        c.set(x + 5, y - 3, pal["w"])
    elif page == 2:
        c.fill_rect(x + 3, y - 2, 3, 2, pal["W"])


def _blackboard(c: Canvas, pal: dict[str, Color], curve_steps: int, lit_formula: bool) -> None:
    x0, y0, w, h = 23, 2, 23, 17
    c.fill_rect(x0, y0, w, h, pal["D"])
    c.fill_rect(x0 + 1, y0 + 1, w - 2, h - 2, pal["j"])
    c.hline(x0 + 1, y0 + h - 1, w - 2, pal["d"])  # chalk tray
    c.fill_rect(x0 + 16, y0 + h - 2, 3, 1, pal["W"])
    # axes
    ax, ay = x0 + 3, y0 + 13
    c.vline(ax, y0 + 6, 8, pal["w"])
    c.hline(ax, ay, 16, pal["w"])
    # sigmoid-ish curve drawn progressively
    curve = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 3), (7, 4), (8, 5),
             (9, 5), (10, 6), (11, 6), (12, 6), (13, 6), (14, 6)]
    n = len(curve) * curve_steps // 3
    for dx, dy in curve[:n]:
        c.set(ax + 1 + dx, ay - 1 - dy, pal["y"])
    # formula
    c.text(x0 + 3, y0 + 2, "DX/DT", pal["W"] if lit_formula else pal["J"])


def _monitor(c: Canvas, pal: dict[str, Color], screen: Callable[[Canvas, int, int], None]) -> None:
    x0, y0, w, h = 26, 9, 19, 14
    c.fill_rect(x0, y0, w, h, pal["k"])
    c.outline(x0, y0, w, h, pal["K"])
    c.fill_rect(x0 + 2, y0 + 2, w - 4, h - 4, pal["T"])
    c.fill_rect(x0 + 8, y0 + h, 3, 1, pal["k"])
    c.fill_rect(x0 + 5, y0 + h + 1, 9, 1, pal["K"])
    screen(c, x0 + 2, y0 + 2)


CODE_LINES = ((0, 5, "t"), (2, 7, "c"), (2, 4, "t"), (4, 6, "t"), (0, 3, "c"))


def _screen_code(lines: int, cursor: bool) -> Callable[[Canvas, int, int], None]:
    def draw(c: Canvas, sx: int, sy: int) -> None:
        pal = palette_for()
        for i, (indent, length, col) in enumerate(CODE_LINES[:lines]):
            c.hline(sx + 1 + indent, sy + 1 + i * 2, length, pal[col])
            c.hline(sx + 2 + indent + length, sy + 1 + i * 2, 3 - (i % 2), pal["t"]) if i % 2 == 0 else None
        if cursor:
            cy = sy + 1 + min(lines, len(CODE_LINES) - 1) * 2
            cx = sx + 1 + (CODE_LINES[lines][0] if lines < len(CODE_LINES) else 0)
            c.fill_rect(cx, cy - (1 if lines >= len(CODE_LINES) else 0), 2, 1, pal["W"])
    return draw


def _screen_run(step: int, steps: int) -> Callable[[Canvas, int, int], None]:
    def draw(c: Canvas, sx: int, sy: int) -> None:
        pal = palette_for()
        c.text(sx + 1, sy + 1, "RUN", pal["t"])
        c.outline(sx + 1, sy + 7, 13, 3, pal["t"])
        c.hline(sx + 2, sy + 8, max(1, 11 * step // steps), pal["c"])
        c.set(sx + 12 + (step % 2), sy + 2 + (step % 2) * 2, pal["y"])
    return draw


def _screen_bug(frame: int) -> Callable[[Canvas, int, int], None]:
    def draw(c: Canvas, sx: int, sy: int) -> None:
        pal = palette_for()
        c.fill_rect(sx, sy, 15, 10, "#2a0d12")
        c.blit(sp.BUG, sx + 2 + frame * 5, sy + 2 + frame, pal)
        if frame == 0:
            c.text(sx + 12, sy + 1, "!", pal["r"])
        c.hline(sx + 1, sy + 9, 13, pal["R"])
    return draw


def _screen_check() -> Callable[[Canvas, int, int], None]:
    def draw(c: Canvas, sx: int, sy: int) -> None:
        pal = palette_for()
        c.blit(sp.CHECK, sx + 4, sy + 2, pal)
    return draw


def _screen_sleep(phase: int) -> Callable[[Canvas, int, int], None]:
    def draw(c: Canvas, sx: int, sy: int) -> None:
        pal = palette_for()
        c.fill_rect(sx, sy, 15, 10, "#060d0a")
        c.set(sx + 3 + phase * 4, sy + 3 + (phase % 2) * 3, pal["g"])
    return draw


def _keyboard(c: Canvas, pal: dict[str, Color], x: int) -> None:
    c.fill_rect(x, DESK_Y, 10, 2, pal["G"])
    for kx in range(x + 1, x + 9, 2):
        c.set(kx, DESK_Y, pal["g"])
        c.set(kx + 1, DESK_Y + 1, pal["g"])


def _typewriter(c: Canvas, pal: dict[str, Color], lines: int, shift: int, paper: bool = True) -> None:
    x0 = 27
    if paper:
        px = x0 + 4 - shift
        c.fill_rect(px, 7, 11, 12, pal["W"])
        c.vline(px + 10, 7, 12, pal["w"])
        for i in range(lines):
            c.hline(px + 1, 9 + i * 2, 8 - (i * 3) % 5, pal["g"])
    c.fill_rect(x0 + 1, 17, 17, 2, pal["k"])      # platen
    c.set(x0, 17, pal["G"])
    c.set(x0 + 18, 17, pal["G"])
    c.fill_rect(x0, 19, 19, 5, pal["A"])          # body
    c.hline(x0, 19, 19, pal["a"])
    for kx in range(x0 + 2, x0 + 17, 2):          # keys
        c.set(kx, 21, pal["W"])
        c.set(kx + 1, 22, pal["G"])


def _clipboard(c: Canvas, pal: dict[str, Color], marks: int, stamp: str | None) -> None:
    x0, y0 = 28, 3
    c.fill_rect(x0, y0, 16, 21, pal["D"])
    c.fill_rect(x0 + 1, y0 + 2, 14, 18, pal["W"])
    c.fill_rect(x0 + 5, y0, 6, 3, pal["G"])
    c.hline(x0 + 6, y0, 4, pal["g"])
    for i in range(7):
        c.hline(x0 + 3, y0 + 5 + i * 2, 10 - (i * 3) % 4, pal["G"])
    red = pal["R"]
    if marks >= 1:  # circle a word
        c.outline(x0 + 2, y0 + 4, 7, 3, red)
    if marks >= 2:  # strike-through
        c.hline(x0 + 3, y0 + 9, 9, red)
    if marks >= 3:  # margin "?"
        c.text(x0 + 11, y0 + 12, "?", red)
    if marks >= 4:
        c.hline(x0 + 3, y0 + 18, 6, red)
        c.set(x0 + 2, y0 + 17, red)
    if stamp:
        c.fill_rect(x0 + 2, y0 + 9, 12, 9, pal["W"])
        c.outline(x0 + 2, y0 + 9, 12, 9, red)
        c.text_center(x0 + 8, y0 + 11, stamp, red)


def _spinner(c: Canvas, pal: dict[str, Color], x: int, y: int, phase: int) -> None:
    c.blit(sp.SPINNER, x, y, pal)
    for dx, dy in sp.SPINNER_SEGMENTS[phase % len(sp.SPINNER_SEGMENTS)]:
        c.set(x + dx, y + dy, pal["Y"])


def _scene_frames(n: int, build: Callable[[int], Canvas]) -> list[Canvas]:
    return [build(i) for i in range(n)]


# ----------------------------------------------------------------------------- common overlays
def _overlay_state(c: Canvas, pal: dict[str, Color], state: AgentState, i: int, role: str = "") -> None:
    """State cues shared by every agent (sleep bubbles, sweat, sparkles, bubbles)."""
    bx, by = 17, 0
    if state == AgentState.SLEEPING:
        z = sp.ZZZ
        c.blit(z, bx + 1 + i, by + 3 - i, {**pal, "W": pal["G"]})
        if i:
            c.blit(sp.SPARKLE_SMALL, bx + 6, by + 5, {**pal, "y": pal["x"], "W": pal["G"]})
    elif state == AgentState.WAITING:
        _bubble(c, pal, bx, by)
        _bubble_text(c, pal, bx, by, "?" if i == 0 else "??")
    elif state == AgentState.THINKING and role != "analyst":
        _bubble(c, pal, bx, by, think=True)
        _bubble_dots(c, pal, bx, by, i + 1)
    elif state == AgentState.ERROR:
        _bubble(c, pal, bx, by)
        _bubble_text(c, pal, bx, by, "!" if i == 0 else "!!", "R")
        c.blit(sp.SWEAT, HEAD_X - 2, HEAD_Y + 3 + i, pal)
    elif state == AgentState.DONE:
        spots = ((2, 2), (19, 4), (4, 20), (21, 13))
        for j, (sx, sy) in enumerate(spots):
            if (i + j) % 2 == 0:
                c.blit(sp.SPARKLE_SMALL, sx, sy, pal)


FACE_FOR = {
    AgentState.SLEEPING: "blink", AgentState.IDLE: "normal", AgentState.WAITING: "normal",
    AgentState.ERROR: "worry", AgentState.DONE: "happy", AgentState.THINKING: "look",
    AgentState.DEBUGGING: "worry",
}


def _base(role: str, state: AgentState, i: int, *, pose: str = "rest", face: str | None = None,
          draw_char: bool = True, head_dy: int = 0) -> tuple[Canvas, dict[str, Color]]:
    pal = palette_for(role)
    c = Canvas(TILE_W, TILE_H)
    draw_room(c, pal)
    if draw_char:
        if state == AgentState.SLEEPING:
            head_dy = max(head_dy, 3)
        f = face or FACE_FOR.get(state, "look")
        if state == AgentState.IDLE and i == 1:
            f = "blink"
        if state == AgentState.DONE:
            pose = "cheer"
        if state == AgentState.SLEEPING:
            pose = "none"
        draw_character(c, role, pal, y=HEAD_Y + head_dy, face=f, pose=pose)
        if state == AgentState.SLEEPING:  # arms folded on the desk, head resting on them
            c.fill_rect(HEAD_X - 2, DESK_Y - 2, 16, 3, pal["U"])
            c.hline(HEAD_X - 2, DESK_Y, 16, pal["u"])
            c.set(HEAD_X - 2, DESK_Y - 2, pal["X"])
            c.set(HEAD_X + 13, DESK_Y - 2, pal["X"])
    return c, pal


def _finish(c: Canvas, pal: dict[str, Color], state: AgentState, i: int, role: str = "") -> Canvas:
    if role:
        _nameplate(c, pal, role)
    _overlay_state(c, pal, state, i, role)
    if state == AgentState.IDLE:
        steam = sp.COFFEE if i == 0 else sp.COFFEE_STEAM_B
        c.blit(steam, 19, DESK_Y - 6, pal)
    return c


# ----------------------------------------------------------------------------- agent tiles
def scout_frames(state: AgentState, progress: float = 0.0) -> list[Canvas]:
    def build(i: int) -> Canvas:
        pose = "rest"
        if state == AgentState.SEARCHING:
            pose = "point"
        c, pal = _base("scout", state, i, pose=pose)
        pop = i if state == AgentState.SEARCHING else None
        _bookshelf(c, pal, pop=pop)
        if state == AgentState.SEARCHING:
            spots = ((27, 3), (35, 9), (29, 15), (38, 16))
            c.blit(sp.MAGNIFIER, *spots[i % len(spots)], pal)
        elif state == AgentState.READING:
            _open_book(c, pal, HEAD_X, DESK_Y - 2, i % 3)
        return _finish(c, pal, state, i, "scout")

    n = {AgentState.SEARCHING: 4, AgentState.READING: 3, AgentState.THINKING: 3}.get(state, 2)
    return _scene_frames(n, build)


def analyst_frames(state: AgentState, progress: float = 0.0) -> list[Canvas]:
    def build(i: int) -> Canvas:
        pose = "think" if state == AgentState.THINKING else ("write_a" if state == AgentState.WRITING else "rest")
        if state == AgentState.WRITING and i % 2:
            pose = "write_b"
        c, pal = _base("analyst", state, i, pose=pose)
        if state == AgentState.THINKING:
            steps = i + 1
        elif state in (AgentState.DONE, AgentState.WRITING, AgentState.WAITING):
            steps = 3
        else:
            steps = _progress_ticks(progress, 3)
        _blackboard(c, pal, steps, lit_formula=state != AgentState.SLEEPING)
        if state == AgentState.THINKING:
            c.blit(sp.BULB_ON if i != 1 else sp.BULB_OFF, HEAD_X + 3, 0, pal)
        return _finish(c, pal, state, i, "analyst")

    n = {AgentState.THINKING: 3, AgentState.WRITING: 2}.get(state, 2)
    return _scene_frames(n, build)


def coder_frames(state: AgentState, progress: float = 0.0) -> list[Canvas]:
    def build(i: int) -> Canvas:
        pose = ("type_a" if i % 2 == 0 else "type_b") if state in (AgentState.CODING, AgentState.DEBUGGING) else "rest"
        c, pal = _base("coder", state, i, pose=pose)
        if state == AgentState.CODING:
            screen = _screen_code(1 + i, cursor=True)
        elif state == AgentState.RUNNING:
            base_step = _progress_ticks(progress, 4)
            screen = _screen_run(min(4, base_step + i), 4)
        elif state == AgentState.DEBUGGING or state == AgentState.ERROR:
            screen = _screen_bug(i % 2)
        elif state == AgentState.DONE:
            screen = _screen_check()
        elif state in (AgentState.SLEEPING, AgentState.IDLE):
            screen = _screen_sleep(i)
        else:
            screen = _screen_code(5, cursor=i == 0)
        _monitor(c, pal, screen)
        _keyboard(c, pal, HEAD_X + 1)
        if state == AgentState.RUNNING:
            _spinner(c, pal, 20, DESK_Y - 6, i)
        return _finish(c, pal, state, i, "coder")

    n = {AgentState.CODING: 4, AgentState.RUNNING: 4}.get(state, 2)
    return _scene_frames(n, build)


def writer_frames(state: AgentState, progress: float = 0.0) -> list[Canvas]:
    def build(i: int) -> Canvas:
        pose = ("type_a" if i % 2 == 0 else "type_b") if state == AgentState.WRITING else "rest"
        c, pal = _base("writer", state, i, pose=pose)
        if state == AgentState.WRITING:
            _typewriter(c, pal, lines=1 + i, shift=i)
        elif state == AgentState.BUILDING:
            _typewriter(c, pal, lines=5, shift=0, paper=False)
            label = ("TEX", "...", "PDF")[i]
            c.fill_rect(30, 6, 13, 9, pal["W"])
            c.outline(30, 6, 13, 9, pal["w"])
            c.text_center(36, 8, label, pal["R"] if label == "PDF" else pal["B"])
            _spinner(c, pal, 22, 4, i)
        else:
            _typewriter(c, pal, lines=5 if state in (AgentState.DONE, AgentState.REVIEWING) else 2, shift=0)
        return _finish(c, pal, state, i, "writer")

    n = {AgentState.WRITING: 4, AgentState.BUILDING: 3}.get(state, 2)
    return _scene_frames(n, build)


def reviewer_frames(state: AgentState, progress: float = 0.0, stamp: str = "OK") -> list[Canvas]:
    def build(i: int) -> Canvas:
        pose = ("write_a" if i % 2 == 0 else "write_b") if state == AgentState.REVIEWING else "rest"
        c, pal = _base("reviewer", state, i, pose=pose)
        if state == AgentState.REVIEWING:
            _clipboard(c, pal, marks=i + 1, stamp=None)
            c.blit(sp.RED_PEN, 20 + (i % 2) * 2, DESK_Y - 7, pal)
        elif state == AgentState.DONE:
            _clipboard(c, pal, marks=4, stamp=stamp)
        else:
            _clipboard(c, pal, marks=0, stamp=None)
        return _finish(c, pal, state, i, "reviewer")

    n = {AgentState.REVIEWING: 4}.get(state, 2)
    return _scene_frames(n, build)


def director_frames(state: str, *, label: str = "DIRECTOR") -> list[Canvas]:
    """The Director's office: an empty chair waiting for the human in charge."""

    def build(i: int) -> Canvas:
        pal = palette_for("director")
        c = Canvas(TILE_W, TILE_H)
        draw_room(c, pal)
        # window with night sky
        c.fill_rect(3, 2, 14, 11, pal["D"])
        c.fill_rect(4, 3, 12, 9, pal["N"])
        c.vline(9, 3, 9, pal["D"])
        c.hline(4, 7, 12, pal["D"])
        c.fill_rect(12, 4, 2, 2, pal["n"])
        for j, (sx, sy) in enumerate(((5, 4), (7, 9), (11, 10), (14, 9))):
            if (i + j) % 2 == 0:
                c.set(sx, sy, pal["n"])
        # executive high-back chair behind the desk (the Director is out: the human!)
        c.fill_rect(19, 7, 12, 17, pal["U"])
        for px_, py_ in ((19, 7), (30, 7)):
            c.set(px_, py_, pal["X"])
        c.outline(20, 8, 10, 15, pal["u"])
        for bx_ in (22, 27):
            for by_ in (11, 15, 19):
                c.set(bx_, by_, pal["A"])
        c.fill_rect(16, 19, 3, 5, pal["u"])   # armrests
        c.fill_rect(31, 19, 3, 5, pal["u"])
        c.hline(16, 19, 3, pal["U"])
        c.hline(31, 19, 3, pal["U"])
        # name plate on the desk front
        _nameplate(c, pal, label, center=24, max_w=40)
        # mascot snake on the desk (tongue flicks)
        c.blit(sp.SNAKE_B if i % 2 else sp.SNAKE_A, 38, DESK_Y - 7, pal)
        if state == "waiting":
            c.fill_rect(20, 18 - (i % 2), 11, 7, pal["W"])  # envelope hopping on the desk
            c.outline(20, 18 - (i % 2), 11, 7, pal["w"])
            for k in range(5):
                c.set(21 + k, 19 + k // 2 - (i % 2), pal["w"])
                c.set(29 - k, 19 + k // 2 - (i % 2), pal["w"])
            c.set(25, 22 - (i % 2), pal["R"])
            _bubble(c, pal, 30, 0)
            _bubble_text(c, pal, 30, 0, "?" if i == 0 else "??")
        elif state == "received":
            c.fill_rect(20, 17, 11, 7, pal["y"])  # scroll
            c.vline(20, 17, 7, pal["Y"])
            c.vline(30, 17, 7, pal["Y"])
            for k in range(3):
                c.hline(22, 18 + k * 2, 6, pal["D"])
            if i == 0:
                c.blit(sp.SPARKLE_SMALL, 31, 14, pal)
        elif state == "reviewing":
            for k in range(3):
                c.fill_rect(21 - k, 18 + k, 10, 2, pal["W"] if k % 2 == 0 else pal["w"])
            _bubble(c, pal, 30, 0)
            _bubble_text(c, pal, 30, 0, "!", "R") if i == 0 else None
        else:  # away
            c.blit(sp.ZZZ, 32 + i, 2 - i + 1, {**pal, "W": pal["G"]})
        return c

    return _scene_frames(2, build)


AGENT_BUILDERS: dict[str, Callable[..., list[Canvas]]] = {
    "scout": scout_frames,
    "analyst": analyst_frames,
    "coder": coder_frames,
    "writer": writer_frames,
    "reviewer": reviewer_frames,
}


def agent_frames(agent: str, state: AgentState, progress: float = 0.0, **kw: str) -> list[Canvas]:
    return AGENT_BUILDERS[agent](AgentState(state), progress, **kw)


def head_icon(agent: str, size_pad: int = 2) -> Canvas:
    """Just the character's head (with accessory) — used in badges."""
    pal = palette_for(agent)
    c = Canvas(12 + 2 * size_pad, 12 + size_pad + 3)
    draw_character(c, agent, pal, x=size_pad, y=3, face="normal", pose="none")
    return c.crop(0, 0, c.width, 15)
