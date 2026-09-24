"""Pixel-art status dashboard for Medusa Lab.

Renders a :class:`~medusa.state.LabSnapshot` as

* ``lab.svg``   – animated pixel-art lab (every agent in its room, the Director's
  office, and the weekly pipeline). CSS-animated, works inside a GitHub README.
* ``lab.gif``   – the same scene as an animated GIF (for Slack/Discord).
* ``badges/<agent>.svg`` – compact per-agent status badges.
* ``status.md`` – Markdown status table (README block & Issue comments).
* ``index.html`` – a live dashboard page that polls ``status.json``.
* ANSI pixel art / plain text for the terminal.
"""

from __future__ import annotations

import json
import logging
import re
import time
from html import escape
from pathlib import Path

from .pixelart import sprites as sp
from .pixelart.ansi import canvas_to_ansi
from .pixelart.canvas import Canvas, Scene, TextOverlay
from .pixelart.font import fit_text, text_width
from .pixelart.gif import scene_to_gif
from .pixelart.palette import BASE, ROLES, TONES, ink_on, mix
from .pixelart.scenes import TILE_H, TILE_W, agent_frames, director_frames, head_icon
from .pixelart.svg import render_svg
from .state import (
    AGENT_KEYS,
    AGENT_PROFILES,
    DIRECTOR_STATES,
    STAGES,
    STATE_STYLES,
    TONE_EMOJI,
    AgentState,
    AgentStatus,
    LabSnapshot,
)
from .utils import (
    atomic_write_bytes,
    atomic_write_text,
    contains_cjk,
    pad_display,
    truncate_display,
)

log = logging.getLogger("medusa.visualizer")

LAB_W, LAB_H = 160, 164
CHROME = "#141220"
PANEL = "#1e1b2e"
FRAME = "#2c2842"
INK = "#f7f3e9"
INK_2 = "#c3bdd0"
INK_3 = "#8c85a0"
COL_X = (4, 56, 108)
ROW_Y = (31, 84)
CELLS = (("director", 0, 0), ("scout", 1, 0), ("analyst", 2, 0),
         ("coder", 0, 1), ("writer", 1, 1), ("reviewer", 2, 1))
FRAME_MS = 450
MODE_COLORS = {"in-silico": "#2a78d6", "human": "#eb6834", "hybrid": "#6a4fd6"}
CYCLE_LABELS = {
    "idle": ("IDLE", "待機中", "idle"),
    "waiting": ("WAITING", "テーマ待ち", "wait"),
    "running": ("RUNNING", "研究中", "active"),
    "done": ("DONE", "完了", "done"),
    "error": ("ERROR", "エラー", "error"),
}
STAGE_TONES = {"done": TONES["done"], "active": TONES["active"], "pending": "#3d3448",
               "skipped": "#29253a", "error": TONES["error"]}
DECISION_STAMP = {"accept": "OK", "minor_revision": "OK", "major_revision": "FIX", "reject": "NG"}


def _tone(status: AgentStatus) -> str:
    return STATE_STYLES[status.state].tone


def _label(lang: str, en: str, ja: str) -> str:
    return ja if lang == "ja" else en


# ============================================================================ lab scene
def build_lab_scene(snap: LabSnapshot, *, lang: str = "ja") -> Scene:
    base = Canvas(LAB_W, LAB_H, CHROME)
    scene = Scene(base, title=f"{snap.lab_name} — {snap.cycle_id or 'lab status'}",
                  description=_describe(snap, lang))
    _draw_header(scene, snap, lang)
    for agent, col, row in CELLS:
        _draw_cell(scene, snap, agent, COL_X[col], ROW_Y[row], lang)
    _draw_pipeline(scene, snap, lang)
    return scene


def _describe(snap: LabSnapshot, lang: str) -> str:
    parts = [f"{snap.lab_name} {snap.cycle_id}".strip()]
    if snap.theme:
        parts.append(("テーマ: " if lang == "ja" else "Theme: ") + snap.theme)
    for key in AGENT_KEYS:
        st = snap.agents[key]
        style = STATE_STYLES[st.state]
        parts.append(f"{AGENT_PROFILES[key].name}: {style.en} {st.message}".strip())
    return " / ".join(parts)


def _chip(c: Canvas, x: int, y: int, text: str, bg: str, *, min_w: int = 0, right: bool = False) -> int:
    w = max(min_w, text_width(text) + 4)
    if right:
        x -= w
    c.fill_rect(x, y, w, 7, bg)
    c.set(x, y, CHROME)
    c.set(x + w - 1, y, CHROME)
    c.set(x, y + 6, CHROME)
    c.set(x + w - 1, y + 6, CHROME)
    c.text(x + (w - text_width(text)) // 2, y + 1, text, ink_on(bg))
    return w


def _draw_header(scene: Scene, snap: LabSnapshot, lang: str) -> None:
    c = scene.base
    pal = dict(BASE)
    scene.add(4, 4, [_sprite_canvas(sp.SNAKE_A, pal), _sprite_canvas(sp.SNAKE_B, pal)], FRAME_MS)
    cycle = snap.cycle_id or "----"
    title_room = LAB_W - 4 - text_width(cycle) - 6 - 15
    c.text(15, 3, fit_text(snap.lab_name.upper(), title_room, scale=2), INK, scale=2, shadow="#3d3448")
    c.text(LAB_W - 4 - text_width(cycle), 3, cycle, INK_2)
    en, _ja, tone = CYCLE_LABELS.get(snap.cycle_status, CYCLE_LABELS["idle"])
    _chip(c, LAB_W - 4, 10, en, TONES[tone], right=True)
    # second row: mode chip + theme
    mode = snap.mode or "hybrid"
    mode_w = _chip(c, 4, 18, mode.upper(), MODE_COLORS.get(mode, "#6a4fd6"))
    c.hline(4, 28, LAB_W - 8, FRAME)
    theme = snap.theme
    if not theme:
        theme = ("所長、今週のMedusa Labの研究テーマは何にしますか？" if lang == "ja"
                 else "Director, what should Medusa Lab research this week?")
        if snap.director.state == "away":
            theme = "—"
    tx = 4 + mode_w + 3
    if contains_cjk(theme) or text_width(theme.upper()) > LAB_W - 4 - tx:
        scene.overlays.append(TextOverlay(tx, 23.6, theme, size=5.0, color=INK, max_width=LAB_W - 4 - tx))
    else:
        c.text(tx, 19, theme.upper(), INK)


def _sprite_canvas(sprite: tuple[str, ...], pal: dict[str, str | None]) -> Canvas:
    c = Canvas(len(sprite[0]), len(sprite))
    c.blit(sprite, 0, 0, pal)
    return c


def _draw_cell(scene: Scene, snap: LabSnapshot, agent: str, x: int, y: int, lang: str) -> None:
    c = scene.base
    if agent == "director":
        state = snap.director.state if snap.director.state in DIRECTOR_STATES else "away"
        frames = director_frames(state)
        en, ja, _emoji = DIRECTOR_STATES[state]
        tone = {"waiting": "wait", "reviewing": "wait", "received": "done", "away": "idle"}[state]
        message = snap.director.message if state != "received" else (
            "テーマを受け付けました" if lang == "ja" else "Theme received")
        if state == "waiting" and not message:
            message = "Issueで /theme を待っています" if lang == "ja" else "Waiting for /theme on the Issue"
        name_color = ROLES["director"]["Z"]
        progress = None
    else:
        status = snap.agents.get(agent) or AgentStatus(agent=agent)
        kwargs = {}
        if agent == "reviewer":
            kwargs["stamp"] = DECISION_STAMP.get(str(snap.counters.get("decision", "")), "OK")
        frames = agent_frames(agent, status.state, status.progress, **kwargs)
        style = STATE_STYLES[status.state]
        en, ja, tone = style.en, style.ja, style.tone
        message = status.message or ja
        name_color = AGENT_PROFILES[agent].color
        progress = status.progress if tone == "active" else (1.0 if tone == "done" else None)
    active = tone in ("active", "wait")
    c.outline(x - 1, y - 1, TILE_W + 2, TILE_H + 2, name_color if active else FRAME)
    scene.add(x, y, frames, FRAME_MS)
    # state strip
    strip_y = y + TILE_H + 1
    bg = TONES[tone]
    c.fill_rect(x, strip_y, TILE_W, 7, bg)
    label = fit_text(en, TILE_W - 4)
    c.text(x + (TILE_W - text_width(label)) // 2, strip_y + 1, label, ink_on(bg))
    # progress rail
    rail_y = strip_y + 7
    c.hline(x, rail_y, TILE_W, "#2a2638")
    if progress is not None:
        c.hline(x, rail_y, max(1, round(TILE_W * progress)), mix(bg, "#ffffff", 0.35))
    scene.overlays.append(TextOverlay(x + TILE_W / 2, rail_y + 5.6, message, size=4.0, color=INK_2,
                                      anchor="middle", max_width=TILE_W + 2))


def _draw_pipeline(scene: Scene, snap: LabSnapshot, lang: str) -> None:
    c = scene.base
    top = 139
    c.hline(4, top - 3, LAB_W - 8, FRAME)
    chip_w, gap = 20, 2
    for i, stage in enumerate(STAGES):
        x = 4 + i * (chip_w + gap)
        status = snap.stages.get(stage.key, "pending")
        tone = STAGE_TONES.get(status, STAGE_TONES["pending"])
        icon_color = INK if status in ("done", "active") else "#6e6378"
        icon = _sprite_canvas(sp.STAGE_ICONS[stage.key], {".": None, "W": icon_color})
        c.fill_rect(x, top, chip_w, 10, PANEL)
        c.paste(icon, x + (chip_w - 7) // 2, top + 1)
        if status == "active":
            on = Canvas(chip_w, 2, tone)
            off = Canvas(chip_w, 2, mix(tone, CHROME, 0.6))
            scene.add(x, top + 10, [on, off], FRAME_MS)
        else:
            c.fill_rect(x, top + 10, chip_w, 2, tone)
        if status == "done":
            c.blit(sp.SPARKLE_SMALL, x + chip_w - 4, top, {".": None, "y": TONES["done"], "W": INK})
        if i < len(STAGES) - 1:
            c.set(x + chip_w, top + 4, INK_3)
            c.set(x + chip_w + 1, top + 5, INK_3)
            c.set(x + chip_w, top + 6, INK_3)
        label = stage.ja if lang == "ja" else stage.en
        scene.overlays.append(TextOverlay(x + chip_w / 2, top + 17.2, label, size=3.6 if lang == "ja" else 3.4,
                                          color=INK_2 if status != "pending" else INK_3, anchor="middle",
                                          max_width=chip_w + 1.5))
    scene.overlays.append(TextOverlay(4, LAB_H - 2.2, _counters_line(snap, lang), size=3.5, color=INK_3,
                                      max_width=LAB_W - 8))


def _counters_line(snap: LabSnapshot, lang: str) -> str:
    k = snap.counters
    parts = []
    if "papers" in k:
        parts.append(f"{'文献' if lang == 'ja' else 'papers'} {k['papers']}")
    if "hypotheses_in_silico" in k or "hypotheses_human" in k:
        hyp = f"{k.get('hypotheses_in_silico', 0)}+{k.get('hypotheses_human', 0)}"
        parts.append(f"{'仮説(計算+人間)' if lang == 'ja' else 'hypotheses (sim+human)'} {hyp}")
    if "figures" in k:
        parts.append(f"{'図' if lang == 'ja' else 'figures'} {k['figures']}")
    if "review_score" in k:
        parts.append(f"{'査読' if lang == 'ja' else 'review'} {k['review_score']}/5")
    if "proposals" in k:
        parts.append(f"{'実験提案' if lang == 'ja' else 'proposals'} {k['proposals']}")
    stamp = (snap.updated_at or "")[:16].replace("T", " ")
    if stamp:
        parts.append(f"{'更新' if lang == 'ja' else 'updated'} {stamp} UTC")
    return " · ".join(parts)


def render_lab_svg(snap: LabSnapshot, *, scale: int = 4, animate: bool = True, lang: str = "ja") -> str:
    return render_svg(build_lab_scene(snap, lang=lang), scale=scale, animate=animate)


def render_lab_gif(snap: LabSnapshot, *, scale: int = 3, lang: str = "ja") -> bytes:
    return scene_to_gif(build_lab_scene(snap, lang=lang), scale=scale, background=CHROME)


# ============================================================================ badges
def build_badge_scene(agent: str, status: AgentStatus) -> Scene:
    profile = AGENT_PROFILES[agent]
    style = STATE_STYLES[status.state]
    name = profile.name.upper()
    state = style.en
    name_w = text_width(name) + 8
    state_w = text_width(state) + 8
    height = 16
    width = 18 + name_w + state_w
    c = Canvas(width, height, PANEL)
    scene = Scene(c, title=f"{profile.name}: {style.en}", description=f"{profile.name} — {style.en} {status.message}")
    ident = profile.color
    c.fill_rect(0, 0, 18, height, mix(ident, "#000000", 0.45))
    head = head_icon(agent)
    c.paste(head, 1, 1)
    c.fill_rect(18, 0, name_w, height, ident)
    c.text(18 + 4, 6, name, ink_on(ident))
    tone = TONES[style.tone]
    c.fill_rect(18 + name_w, 0, state_w, height, tone)
    c.text(18 + name_w + 4, 6, state, ink_on(tone))
    for (px, py) in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        c.px[py][px] = None
    if style.tone == "active":  # blinking activity dot
        on = Canvas(2, 2, "#ffffff")
        off = Canvas(2, 2, tone)
        scene.add(width - 4, 2, [on, off], 500)
    return scene


def render_badge_svg(agent: str, status: AgentStatus, *, scale: int = 2) -> str:
    return render_svg(build_badge_scene(agent, status), scale=scale)


# ============================================================================ text renderings
def _bar(progress: float, width: int = 10) -> str:
    filled = max(0, min(width, round(progress * width)))
    return "▰" * filled + "▱" * (width - filled)


def render_status_markdown(snap: LabSnapshot, *, lang: str = "ja", image_url: str | None = None,
                           heading: bool = True) -> str:
    ja = lang == "ja"
    lines: list[str] = []
    en, ja_label, tone = CYCLE_LABELS.get(snap.cycle_status, CYCLE_LABELS["idle"])
    if heading:
        title = f"### 🐍 {snap.lab_name} — {snap.cycle_id or ('ステータス' if ja else 'status')}"
        lines.append(title)
        lines.append("")
    if image_url:
        lines += [f"![{snap.lab_name} pixel-art dashboard]({image_url})", ""]
    meta = []
    meta.append(f"**{'テーマ' if ja else 'Theme'}:** {snap.theme or '—'}")
    meta.append(f"**{'モード' if ja else 'Mode'}:** `{snap.mode}`")
    meta.append(f"**{'状態' if ja else 'Status'}:** {TONE_EMOJI[tone]} `{en}` {ja_label if ja else ''}".rstrip())
    lines.append(" ｜ ".join(meta) if ja else " | ".join(meta))
    lines.append("")
    header = ("| | エージェント | 状態 | いまやっていること | 進捗 |" if ja
              else "| | Agent | State | Current activity | Progress |")
    lines += [header, "|:-:|:--|:--|:--|:--|"]
    director = DIRECTOR_STATES.get(snap.director.state, DIRECTOR_STATES["away"])
    lines.append(f"| 🏛️ | **{'所長' if ja else 'Director'}**<br><sub>{'人間' if ja else 'human'}</sub> | "
                 f"{director[2]} `{director[0]}` {director[1] if ja else ''} | "
                 f"{_md_escape(snap.director.message) or '—'} | |")
    for key in AGENT_KEYS:
        st = snap.agents[key]
        profile = AGENT_PROFILES[key]
        style = STATE_STYLES[st.state]
        role = profile.role_ja if ja else profile.role_en
        progress = f"`{_bar(st.progress)}` {round(st.progress * 100)}%" if style.tone in ("active", "done") else ""
        lines.append(f"| {profile.emoji} | **{profile.name}**<br><sub>{role}</sub> | "
                     f"{TONE_EMOJI[style.tone]} `{style.en}` {style.ja if ja else ''} | "
                     f"{_md_escape(st.message) or '—'} | {progress} |")
    lines.append("")
    marks = {"done": "✅", "active": "🔵", "pending": "⚪", "skipped": "⏭️", "error": "❌"}
    pipeline = " → ".join(f"{marks.get(snap.stages.get(s.key, 'pending'), '⚪')} {s.ja if ja else s.en.title()}"
                          for s in STAGES)
    lines.append(f"**{'パイプライン' if ja else 'Pipeline'}:** {pipeline}")
    counters = _counters_line(snap, lang)
    if counters:
        lines += ["", f"<sub>{counters}</sub>"]
    return "\n".join(lines) + "\n"


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def render_status_text(snap: LabSnapshot, *, lang: str = "ja", color: bool = False) -> str:
    """Compact terminal status (no pixel art)."""
    ja = lang == "ja"
    en, ja_label, _tone = CYCLE_LABELS.get(snap.cycle_status, CYCLE_LABELS["idle"])
    out = [f"🐍 {snap.lab_name}  {snap.cycle_id or ''}  [{snap.mode}]  {en}",
           f"   {'テーマ' if ja else 'Theme'}: {snap.theme or '—'}", ""]
    tone_ansi = {"idle": "90", "active": "94", "wait": "93", "done": "92", "error": "91"}
    for key in AGENT_KEYS:
        st = snap.agents[key]
        style = STATE_STYLES[st.state]
        name = pad_display(f"{AGENT_PROFILES[key].emoji} {AGENT_PROFILES[key].name}", 12)
        label = pad_display(style.en, 10)
        if color:
            label = f"\x1b[{tone_ansi[style.tone]}m{label}\x1b[0m"
        bar = _bar(st.progress) if style.tone in ("active", "done") else " " * 10
        out.append(f"  {name} {label} {bar}  {truncate_display(st.message or style.ja, 52)}")
    marks = {"done": "■", "active": "▶", "pending": "·", "skipped": "-", "error": "✗"}
    out.append("")
    out.append("  " + " ".join(f"{marks[snap.stages.get(s.key, 'pending')]}{s.en}" for s in STAGES))
    return "\n".join(out)


def render_status_ansi(snap: LabSnapshot, *, t_ms: int = 0, lang: str = "ja", agent: str | None = None) -> str:
    """Truecolor pixel-art rendering (whole lab, or a single agent's room)."""
    scene = build_lab_scene(snap, lang=lang)
    frame = scene.frame_at(t_ms)
    if agent:
        cells = {name: (COL_X[col], ROW_Y[row]) for name, col, row in CELLS}
        x, y = cells[agent]
        frame = frame.crop(x - 1, y - 1, TILE_W + 2, TILE_H + 9)
    return canvas_to_ansi(frame, CHROME)


# ============================================================================ gallery / demo
def demo_snapshot(lang: str = "ja") -> LabSnapshot:
    """A representative mid-cycle snapshot (used for README showcase images)."""
    from .state import StatusBoard

    board = StatusBoard(None, autosave=False)
    ja = lang == "ja"
    board.reset_for_cycle(cycle_id="2026-W39", theme="SNSにおける新語の拡散と言語進化" if ja else
                          "How new words spread on social media", mode="hybrid")
    for stage in ("theme", "scout", "analyst"):
        board.stage(stage, "done")
    board.stage("coder", "active")
    board.agent("scout", AgentState.DONE, "文献12本・課題4件を抽出" if ja else "12 papers, 4 gaps", 1.0)
    board.agent("analyst", AgentState.THINKING, "人間向け実験を設計中" if ja else "Designing human experiments", 0.6)
    board.agent("coder", AgentState.RUNNING, "パラメータスイープ N=32..256" if ja else "Sweeping N=32..256", 0.55)
    board.agent("writer", AgentState.WRITING, "Introduction を執筆中" if ja else "Drafting the introduction", 0.3)
    board.agent("reviewer", AgentState.SLEEPING, "出番待ち" if ja else "Waiting for a draft")
    for key, value in (("papers", 12), ("hypotheses_in_silico", 2), ("hypotheses_human", 2), ("figures", 2)):
        board.counter(key, value)
    return board.snapshot


SHEET_STATES: dict[str, tuple[AgentState, ...]] = {
    "scout": (AgentState.SEARCHING, AgentState.READING, AgentState.DONE, AgentState.SLEEPING),
    "analyst": (AgentState.THINKING, AgentState.WRITING, AgentState.WAITING, AgentState.DONE),
    "coder": (AgentState.CODING, AgentState.RUNNING, AgentState.DEBUGGING, AgentState.DONE),
    "writer": (AgentState.WRITING, AgentState.BUILDING, AgentState.DONE, AgentState.IDLE),
    "reviewer": (AgentState.REVIEWING, AgentState.DONE, AgentState.WAITING, AgentState.ERROR),
}


def build_sprite_sheet() -> Scene:
    """Every agent in its signature states (animated) — a gallery for the docs."""
    cols, gap, label_h = 4, 4, 9
    width = gap + cols * (TILE_W + gap)
    height = gap + len(SHEET_STATES) * (TILE_H + label_h + gap)
    scene = Scene(Canvas(width, height, CHROME), title="Medusa Lab sprite sheet",
                  description="Each agent of Medusa Lab in four of its states")
    c = scene.base
    for row, (agent, states) in enumerate(SHEET_STATES.items()):
        y = gap + row * (TILE_H + label_h + gap)
        for col, state in enumerate(states):
            x = gap + col * (TILE_W + gap)
            scene.add(x, y, agent_frames(agent, state, 0.6), FRAME_MS)
            style = STATE_STYLES[state]
            bg = TONES[style.tone]
            c.fill_rect(x, y + TILE_H + 1, TILE_W, 7, bg)
            label = fit_text(style.en, TILE_W - 4)
            c.text(x + (TILE_W - text_width(label)) // 2, y + TILE_H + 2, label, ink_on(bg))
    return scene


# ============================================================================ README & files
README_START = "<!-- MEDUSA:STATUS:START -->"
README_END = "<!-- MEDUSA:STATUS:END -->"


def update_readme(readme: Path, markdown: str) -> bool:
    """Replace the status block between the MEDUSA:STATUS markers. Returns True if changed."""
    if not readme.is_file():
        return False
    text = readme.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.S)
    if not pattern.search(text):
        return False
    block = f"{README_START}\n{markdown.strip()}\n{README_END}"
    new = pattern.sub(lambda _m: block, text)
    if new == text:
        return False
    atomic_write_text(readme, new)
    return True


def render_dashboard_html(snap: LabSnapshot, *, lang: str = "ja") -> str:
    """A self-contained live dashboard page (polls status.json when served over HTTP)."""
    data = json.dumps(snap.to_dict(), ensure_ascii=False).replace("</", "<\\/")
    profiles = json.dumps({k: {"name": p.name, "emoji": p.emoji, "role": p.role_ja if lang == "ja" else p.role_en}
                           for k, p in AGENT_PROFILES.items()}, ensure_ascii=False)
    styles = json.dumps({s.value: {"en": st.en, "ja": st.ja, "tone": st.tone} for s, st in STATE_STYLES.items()},
                        ensure_ascii=False)
    stages = json.dumps([{"key": s.key, "en": s.en, "ja": s.ja} for s in STAGES], ensure_ascii=False)
    title = escape(f"{snap.lab_name} — dashboard")
    return _DASHBOARD_TEMPLATE.replace("__TITLE__", title).replace("__LANG__", lang).replace(
        "__DATA__", data).replace("__PROFILES__", profiles).replace("__STYLES__", styles).replace(
        "__STAGES__", stages)


class DashboardRenderer:
    """StatusBoard subscriber that keeps the dashboard files up to date."""

    def __init__(self, out_dir: Path, *, lang: str = "ja", scale: int = 4, gif_scale: int = 3,
                 animate: bool = True, gif: bool = True, readme: Path | None = None,
                 min_interval: float = 0.5) -> None:
        self.out_dir = Path(out_dir)
        self.lang = lang
        self.scale = scale
        self.gif_scale = gif_scale
        self.animate = animate
        self.gif = gif
        self.readme = readme
        self.min_interval = min_interval
        self._last = 0.0
        self._last_states: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, cfg) -> DashboardRenderer:  # type: ignore[no-untyped-def]
        return cls(cfg.dashboard_dir, lang=cfg.lab.language, scale=cfg.dashboard.scale,
                   gif_scale=cfg.dashboard.gif_scale, animate=cfg.dashboard.animate, gif=cfg.dashboard.gif,
                   readme=cfg.readme_path if cfg.dashboard.update_readme else None)

    def __call__(self, snap: LabSnapshot, kind: str) -> None:
        now = time.monotonic()
        states = tuple(snap.agents[k].state.value for k in AGENT_KEYS)
        # state switches always render; message/progress updates are throttled
        if kind in ("stage", "cycle", "director") or states != self._last_states or now - self._last >= self.min_interval:
            self._last, self._last_states = now, states
            try:
                self.render_live(snap)
            except Exception:  # the dashboard must never break a research cycle
                log.exception("dashboard render failed")

    def render_live(self, snap: LabSnapshot) -> list[Path]:
        """Fast outputs, refreshed on every state change."""
        written = [
            atomic_write_text(self.out_dir / "lab.svg",
                              render_lab_svg(snap, scale=self.scale, animate=self.animate, lang=self.lang)),
            atomic_write_text(self.out_dir / "status.md", render_status_markdown(snap, lang=self.lang)),
        ]
        for key in AGENT_KEYS:
            written.append(atomic_write_text(self.out_dir / "badges" / f"{key}.svg",
                                             render_badge_svg(key, snap.agents[key])))
        return written

    def render_all(self, snap: LabSnapshot, *, update_readme_block: bool = True) -> list[Path]:
        """Everything, including the (slower) GIF, the HTML page and the README block."""
        written = self.render_live(snap)
        written.append(atomic_write_text(self.out_dir / "index.html", render_dashboard_html(snap, lang=self.lang)))
        if self.gif:
            written.append(atomic_write_bytes(self.out_dir / "lab.gif",
                                              render_lab_gif(snap, scale=self.gif_scale, lang=self.lang)))
        if update_readme_block and self.readme:
            md = render_status_markdown(snap, lang=self.lang, heading=False)
            if update_readme(self.readme, md):
                written.append(self.readme)
        return written


_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#0f0d18;--panel:#1e1b2e;--ink:#f7f3e9;--ink2:#c3bdd0;--ink3:#8c85a0;--line:#2c2842;
--idle:#6e6378;--active:#2a78d6;--wait:#fab219;--done:#0ca30c;--error:#d03b3b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 16px}
.lab{width:100%;height:auto;image-rendering:pixelated;border:1px solid var(--line);border-radius:8px;background:#141220}
table{width:100%;border-collapse:collapse;margin-top:20px;background:var(--panel);border-radius:8px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--ink3);font-weight:600;font-size:13px}
td.msg{color:var(--ink2)}
.tag{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;color:#0b0b0b}
.tag.idle{background:var(--idle);color:#fff}.tag.active{background:var(--active);color:#fff}
.tag.wait{background:var(--wait)}.tag.done{background:var(--done);color:#fff}.tag.error{background:var(--error);color:#fff}
.bar{height:6px;background:#2a2638;border-radius:3px;min-width:80px}
.bar>span{display:block;height:100%;border-radius:3px;background:var(--active)}
ol.events{list-style:none;padding:0;margin:20px 0 0;color:var(--ink2);font-size:13px}
ol.events li{padding:4px 0;border-bottom:1px dashed var(--line)}
ol.events time{color:var(--ink3);margin-right:8px;font-variant-numeric:tabular-nums}
.live{font-size:12px;color:var(--ink3)}
@media (max-width:640px){td.role,th.role{display:none}}
</style>
</head>
<body>
<main>
<h1 id="title"></h1>
<p class="sub" id="theme"></p>
<img class="lab" id="lab" src="lab.svg" alt="pixel-art lab dashboard">
<p class="live" id="live"></p>
<table><thead><tr><th>Agent</th><th class="role">Role</th><th>State</th><th>Activity</th><th>Progress</th></tr></thead>
<tbody id="agents"></tbody></table>
<ol class="events" id="events"></ol>
</main>
<script>
const INITIAL = __DATA__;
const PROFILES = __PROFILES__;
const STYLES = __STYLES__;
const STAGES = __STAGES__;
const LANG = "__LANG__";
let lastUpdate = null;
function el(tag, cls, text){const e=document.createElement(tag); if(cls) e.className=cls; if(text!==undefined) e.textContent=text; return e;}
function render(s){
  document.getElementById("title").textContent = `🐍 ${s.lab_name} — ${s.cycle_id || "status"}`;
  document.getElementById("theme").textContent = (LANG==="ja"?"テーマ: ":"Theme: ") + (s.theme || "—") + `  [${s.mode}]`;
  const body = document.getElementById("agents"); body.replaceChildren();
  for (const [key, p] of Object.entries(PROFILES)) {
    const a = s.agents[key] || {state:"sleeping", message:"", progress:0};
    const st = STYLES[a.state] || STYLES.sleeping;
    const tr = el("tr");
    tr.append(el("td", "", `${p.emoji} ${p.name}`), el("td", "role", p.role));
    const tdState = el("td"); tdState.append(el("span", "tag " + st.tone, st.en)); tr.append(tdState);
    tr.append(el("td", "msg", a.message || (LANG==="ja"?st.ja:"")));
    const tdBar = el("td"); const bar = el("div", "bar"); const fill = el("span");
    fill.style.width = Math.round((st.tone==="active"||st.tone==="done" ? a.progress : 0) * 100) + "%";
    bar.append(fill); tdBar.append(bar); tr.append(tdBar); body.append(tr);
  }
  const ev = document.getElementById("events"); ev.replaceChildren();
  for (const e of (s.events || []).slice().reverse().slice(0, 15)) {
    const li = el("li"); li.append(el("time", "", (e.at||"").slice(11,19)), document.createTextNode(`${e.agent} · ${e.state} · ${e.message||""}`));
    ev.append(li);
  }
  if (s.updated_at !== lastUpdate) {
    lastUpdate = s.updated_at;
    document.getElementById("lab").src = "lab.svg?t=" + encodeURIComponent(s.updated_at || Date.now());
  }
  document.getElementById("live").textContent = (LANG==="ja"?"最終更新: ":"Last update: ") + (s.updated_at || "—");
}
render(INITIAL);
async function poll(){
  try { const r = await fetch("status.json?t=" + Date.now(), {cache:"no-store"}); if (r.ok) render(await r.json()); }
  catch (e) { /* file:// or offline: keep the embedded snapshot */ }
}
if (location.protocol.startsWith("http")) setInterval(poll, 3000);
</script>
</body>
</html>
"""
