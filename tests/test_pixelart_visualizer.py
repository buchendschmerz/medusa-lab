from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from medusa.pixelart.canvas import Canvas, Scene
from medusa.pixelart.font import fit_text, text_width
from medusa.pixelart.gif import encode_gif
from medusa.pixelart.scenes import TILE_H, TILE_W, agent_frames, director_frames
from medusa.pixelart.svg import render_svg
from medusa.state import AGENT_KEYS, AgentState, StatusBoard
from medusa.visualizer import (
    DashboardRenderer,
    build_lab_scene,
    render_badge_svg,
    render_dashboard_html,
    render_lab_svg,
    render_status_ansi,
    render_status_markdown,
    update_readme,
)


def _board() -> StatusBoard:
    board = StatusBoard(None)
    board.reset_for_cycle(cycle_id="2026-W39", theme="拍手の同期 <script>&", mode="hybrid")
    board.stage("theme", "done")
    board.stage("scout", "active")
    board.agent("scout", AgentState.SEARCHING, "arXiv を検索中", 0.4)
    board.agent("coder", AgentState.RUNNING, "sweep K", 0.5)
    return board


def test_font_and_canvas_basics() -> None:
    assert text_width("A") == 3 and text_width("AB") == 7 and text_width("M") == 5
    assert text_width("") == 0
    assert text_width(fit_text("SUPERCALIFRAGILISTIC", 30)) <= 30
    c = Canvas(10, 6, "#000000")
    c.fill_rect(2, 2, 3, 2, "#ff0000")
    assert c.get(3, 3) == "#ff0000" and c.get(9, 5) == "#000000" and c.get(20, 20) is None
    w = c.text(0, 0, "HI", "#ffffff")
    assert w == text_width("HI")


@pytest.mark.parametrize("agent", AGENT_KEYS)
def test_every_agent_state_has_frames(agent: str) -> None:
    for state in AgentState:
        frames = agent_frames(agent, state, 0.5)
        assert frames and all(f.width == TILE_W and f.height == TILE_H for f in frames)
    for state in ("away", "waiting", "received", "reviewing"):
        assert len(director_frames(state)) == 2


def test_lab_svg_is_valid_animated_and_escaped() -> None:
    svg = render_lab_svg(_board().snapshot, lang="ja")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "@keyframes" in svg and "prefers-reduced-motion" in svg
    assert "&lt;script&gt;&amp;" in svg and "<script>" not in svg
    static = render_lab_svg(_board().snapshot, lang="en", animate=False)
    assert "@keyframes mf" not in static
    ET.fromstring(static)


def test_svg_animation_frames_toggle() -> None:
    base = Canvas(4, 4, "#000000")
    a, b = Canvas(2, 2, "#ff0000"), Canvas(2, 2, "#00ff00")
    scene = Scene(base)
    scene.add(1, 1, [a, b], 300)
    svg = render_svg(scene, scale=2)
    assert svg.count('class="mf mf2_') == 2
    assert 'opacity="0"' in svg and "animation-duration:600ms" in svg


def test_gif_round_trip_with_pillow() -> None:
    pil = pytest.importorskip("PIL.Image")
    scene = build_lab_scene(_board().snapshot, lang="en")
    frames = scene.timeline(max_frames=12)
    data = encode_gif(frames, scale=1, background="#141220")
    img = pil.open(io.BytesIO(data))
    assert img.size == (scene.width, scene.height)
    assert img.n_frames == len(frames)
    for i, (canvas, _) in enumerate(frames):
        img.seek(i)
        rgb = img.convert("RGB")
        expected = canvas.rgb_rows("#141220")
        for y in range(0, canvas.height, 7):
            for x in range(0, canvas.width, 5):
                assert rgb.getpixel((x, y)) == expected[y][x]


def test_badges_markdown_ansi_html() -> None:
    snap = _board().snapshot
    for agent in AGENT_KEYS:
        ET.fromstring(render_badge_svg(agent, snap.agents[agent]))
    md = render_status_markdown(snap, lang="ja")
    assert "| 🔍 | **Kepler**" in md and "SEARCHING" in md and "パイプライン" in md
    ansi = render_status_ansi(snap, agent="coder")
    assert "\x1b[38;2;" in ansi and "▀" in ansi
    page = render_dashboard_html(snap, lang="ja")
    assert "status.json" in page and "</script>" in page and "<\\/" not in page.split("<script>")[0]


def test_readme_block_update(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("intro\n<!-- MEDUSA:STATUS:START -->\nold\n<!-- MEDUSA:STATUS:END -->\noutro\n")
    assert update_readme(readme, "NEW TABLE")
    text = readme.read_text()
    assert "NEW TABLE" in text and "old" not in text and text.startswith("intro") and text.endswith("outro\n")
    assert not update_readme(readme, "NEW TABLE")  # idempotent
    no_markers = tmp_path / "other.md"
    no_markers.write_text("x")
    assert not update_readme(no_markers, "y")


def test_renderer_writes_files(tmp_path: Path) -> None:
    renderer = DashboardRenderer(tmp_path, gif=True, gif_scale=1)
    written = renderer.render_all(_board().snapshot)
    names = {p.name for p in written}
    assert {"lab.svg", "status.md", "index.html", "lab.gif"} <= names
    assert (tmp_path / "badges" / "coder.svg").exists()
