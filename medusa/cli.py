"""``medusa`` command line interface.

    medusa prompt            Monday: ask the Director for a theme (Issue / Slack / Discord)
    medusa run --theme ...   run a full research cycle
    medusa demo              offline demo cycle (no API key, no network)
    medusa status [--pixel]  show the lab status (pixel art in the terminal)
    medusa serve             serve outputs/ with the live dashboard
    medusa resolve-theme     (CI) turn the triggering event into a theme file
    medusa notify-complete   (CI) post the final Issue comment with the PR link
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import http.server
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config, ConfigError
from .models import Mode, ResearchTheme
from .utils import WEEK_IN_TEXT_RE, env_flag, iso_week, read_json, setup_logging, write_json


def _load_config(args: argparse.Namespace) -> Config:
    cfg = Config.load(args.config) if args.config else Config.load()
    for warning in cfg.warnings:
        print(f"⚠️  {warning}", file=sys.stderr)
    return cfg


def _set_output(path: str | None, values: dict[str, Any]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            text = "true" if value is True else "false" if value is False else str(value if value is not None else "")
            fh.write(f"{key}={' '.join(text.split())}\n")


# ------------------------------------------------------------------------------ prompt
def cmd_prompt(args: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator

    cfg = _load_config(args)
    orch = Orchestrator(cfg, console=False)
    result = orch.request_theme(dry_run=args.dry_run)
    for err in result["errors"]:
        print(f"⚠️  {err}", file=sys.stderr)
    if result["issue_url"]:
        print(f"📮 {result['issue_url']}")
    return 0


# ------------------------------------------------------------------------------ resolve-theme
def cmd_resolve_theme(args: argparse.Namespace) -> int:
    from .notifier import Notifier
    from .themes import ThemeError, parse_theme_comment, theme_from_config, theme_from_inputs

    cfg = _load_config(args)
    env = os.environ
    event = args.event or env.get("EVENT_NAME") or env.get("GITHUB_EVENT_NAME", "")
    default_mode = Mode.parse(cfg.theme.mode, Mode.HYBRID)
    outputs: dict[str, Any] = {"should_run": False}
    cmd = None
    source, issue_number, comment_id, author = "cli", None, None, ""
    cycle_hint = ""
    try:
        if event == "issue_comment":
            source = "issue"
            issue_number = int(env.get("ISSUE_NUMBER") or 0) or None
            comment_id = int(env.get("COMMENT_ID") or 0) or None
            author = env.get("COMMENT_AUTHOR", "")
            m = WEEK_IN_TEXT_RE.search(env.get("ISSUE_TITLE", ""))
            cycle_hint = m.group(1) if m else ""
            cmd = parse_theme_comment(env.get("COMMENT_BODY", ""), default_mode)
            if cmd is None:
                outputs["reason"] = "comment has no /theme command"
        elif event == "workflow_dispatch":
            source = "dispatch"
            cmd = theme_from_inputs(env.get("INPUT_THEME", ""), env.get("INPUT_KEYWORDS", ""),
                                    env.get("INPUT_MODE", ""), env.get("INPUT_NOTES", ""), default_mode)
        else:
            source = "config"
            cmd = theme_from_config(cfg)
            if cmd is None:
                outputs["reason"] = "config.yaml has no theme.current"
            else:
                week = iso_week(tz=cfg.lab.timezone)
                history = read_json(cfg.outputs_dir / "history.json", []) or []
                if any(h.get("theme") == cmd.title and str(h.get("cycle_id", "")).startswith(week)
                       and h.get("status") == "done" for h in history) and not env_flag("MEDUSA_FORCE"):
                    outputs["reason"] = f"theme already studied in {week}"
                    cmd = None
    except (ThemeError, ValueError) as exc:
        outputs["reason"] = f"invalid theme: {exc}"
        outputs["error"] = str(exc)
        notifier = Notifier(cfg)
        if notifier.github and issue_number:
            ja = cfg.lab.language == "ja"
            notifier.github.comment(issue_number, (
                f"⚠️ `/theme` の書式を読み取れませんでした: {exc}\n\n例:\n```text\n/theme SNSにおける新語の拡散\n/mode hybrid\n```"
                if ja else f"⚠️ Could not read the `/theme` command: {exc}\n\nExample:\n```text\n/theme How slang spreads\n"
                           "/mode hybrid\n```"))
        cmd = None
    if cmd is not None:
        theme = cmd.to_theme(cycle_id=cycle_hint or iso_week(tz=cfg.lab.timezone), source=source,
                             issue_number=issue_number, requested_by=author)
        out = Path(args.out)
        write_json(out, {**theme.to_dict(), "comment_id": comment_id})
        outputs.update({"should_run": True, "theme_file": str(out), "cycle_id": theme.cycle_id,
                        "mode": theme.mode.value, "branch": f"medusa/{theme.cycle_id}",
                        "issue_number": issue_number or "", "comment_id": comment_id or "", "reason": "ok"})
        print(f"🐍 theme: {theme.title} [{theme.mode.value}] → {theme.cycle_id}")
    else:
        print(f"⏭️  not running: {outputs.get('reason')}")
    _set_output(args.github_output, outputs)
    return 0


# ------------------------------------------------------------------------------ run
def _apply_overrides(cfg: Config, args: argparse.Namespace) -> None:
    if getattr(args, "offline", False):
        cfg.llm.provider = "offline"
    if getattr(args, "no_network", False):
        cfg.scout.network = False
    if getattr(args, "quick", False):
        cfg.coder.quick = True
    if getattr(args, "no_pdf", False):
        cfg.writer.compile_pdf = False


def _theme_from_args(cfg: Config, args: argparse.Namespace) -> tuple[ResearchTheme, int | None]:
    from .themes import theme_from_config, theme_from_inputs

    comment_id = None
    if args.theme_file:
        data = json.loads(Path(args.theme_file).read_text(encoding="utf-8"))
        comment_id = data.pop("comment_id", None)
        theme = ResearchTheme.from_dict(data)
    elif args.theme:
        cmd = theme_from_inputs(args.theme, args.keywords, args.mode or "", args.notes,
                                Mode.parse(cfg.theme.mode, Mode.HYBRID))
        theme = cmd.to_theme(source="cli")
    else:
        cmd = theme_from_config(cfg)
        if cmd is None:
            raise ConfigError("no theme: pass --theme, --theme-file, or set theme.current in config.yaml")
        theme = cmd.to_theme(source="config")
    if args.mode:
        theme.mode = Mode.parse(args.mode)
    if args.cycle_id:
        theme.cycle_id = args.cycle_id
    if args.issue:
        theme.issue_number = args.issue
    return theme, (args.comment_id or comment_id)


def cmd_run(args: argparse.Namespace) -> int:
    from .notifier import IssueLiveReporter, Notifier
    from .orchestrator import Orchestrator

    cfg = _load_config(args)
    _apply_overrides(cfg, args)
    theme, comment_id = _theme_from_args(cfg, args)
    notifier = Notifier(cfg)
    live = None
    if theme.issue_number and notifier.github and cfg.notify.live_status_comment:
        live = IssueLiveReporter(notifier.github, theme.issue_number, lang=cfg.lab.language, run_url=notifier.run_url,
                                 image_url=cfg.notify.dashboard_url)
    notifier.acknowledge(theme.issue_number, comment_id)
    orch = Orchestrator(cfg, notifier=notifier)
    print(f"🐍 {cfg.lab.name}: '{theme.title}' [{theme.mode.value}] — LLM: {orch.llm.describe()}", file=sys.stderr)
    try:
        outcome = orch.run_cycle(theme, resume=args.resume, live_reporter=live)
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero
        print(f"❌ research cycle failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if live:
            live.push(orch.board.snapshot)
        cycle_dir = cfg.cycle_dir(theme.cycle_id)
        summary = (cycle_dir / "summary.md").read_text(encoding="utf-8") if (cycle_dir / "summary.md").exists() else str(exc)
        if theme.issue_number:
            notifier.finish(theme.issue_number, summary, comment_id=comment_id, ok=False)
        _set_output(os.environ.get("GITHUB_OUTPUT"), {"ok": False, "cycle_id": theme.cycle_id})
        return 1
    if live:
        live.push(orch.board.snapshot)
    record = outcome.record
    print(outcome.summary_md)
    _set_output(os.environ.get("GITHUB_OUTPUT"), {
        "ok": True, "cycle_id": record.cycle_id, "pr_body": str(outcome.pr_body_path or ""),
        "paper_title": record.paper_title or record.theme.title, "decision": record.decision,
        "comment_id": comment_id or "", "issue_number": theme.issue_number or ""})
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator

    cfg = _load_config(args)
    cfg.llm.provider = "offline"
    cfg.scout.network = False
    cfg.coder.quick = not args.full
    cfg.paths.outputs = args.outputs
    cfg.dashboard.update_readme = False
    if args.no_pdf:
        cfg.writer.compile_pdf = False
    theme = ResearchTheme(title=args.theme, keywords=[k.strip() for k in args.keywords.split(",") if k.strip()],
                          mode=Mode.parse(args.mode), source="demo")
    orch = Orchestrator(cfg)
    outcome = orch.run_cycle(theme)
    print(outcome.summary_md)
    print(f"🌐 open {cfg.outputs_dir / 'index.html'}  (or: medusa serve --outputs {args.outputs})")
    return 0


# ------------------------------------------------------------------------------ status / render / serve
def cmd_status(args: argparse.Namespace) -> int:
    from .state import StatusBoard
    from .visualizer import render_status_ansi, render_status_text

    cfg = _load_config(args)
    path = cfg.dashboard_dir / "status.json"
    if args.json:
        print(json.dumps(read_json(path, {}), ensure_ascii=False, indent=2))
        return 0
    if not args.watch:
        board = StatusBoard.load(path, lab_name=cfg.lab.name, autosave=False)
        if args.pixel or args.agent:
            print(render_status_ansi(board.snapshot, lang=cfg.lab.language, agent=args.agent))
        print(render_status_text(board.snapshot, lang=cfg.lab.language, color=sys.stdout.isatty()))
        return 0
    t = 0
    try:
        while True:
            board = StatusBoard.load(path, lab_name=cfg.lab.name, autosave=False)
            frame = render_status_ansi(board.snapshot, t_ms=t, lang=cfg.lab.language, agent=args.agent)
            sys.stdout.write("\x1b[H\x1b[2J" + frame + "\n" + render_status_text(board.snapshot, lang=cfg.lab.language,
                                                                                   color=True) + "\n")
            sys.stdout.flush()
            time.sleep(0.45)
            t += 450
    except KeyboardInterrupt:
        return 0


def cmd_render(args: argparse.Namespace) -> int:
    from .report import render_index
    from .state import StatusBoard
    from .utils import atomic_write_text
    from .visualizer import DashboardRenderer

    cfg = _load_config(args)
    board = StatusBoard.load(cfg.dashboard_dir / "status.json", lab_name=cfg.lab.name)
    board.snapshot.lab_name = cfg.lab.name
    written = DashboardRenderer.from_config(cfg).render_all(board.snapshot)
    history = read_json(cfg.outputs_dir / "history.json", []) or []
    written.append(atomic_write_text(cfg.outputs_dir / "index.html", render_index(history, lab_name=cfg.lab.name,
                                                                                   lang=cfg.lab.language)))
    board.save()
    for path in written:
        print(f"🖼️  {path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    root = Path(args.outputs).resolve() if args.outputs else cfg.outputs_dir
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    with http.server.ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"🌐 Medusa Lab dashboard: http://{args.host}:{args.port}/dashboard/index.html  (archive: /index.html)")
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()
    return 0


# ------------------------------------------------------------------------------ notify-complete
def cmd_notify_complete(args: argparse.Namespace) -> int:
    from .notifier import Notifier

    cfg = _load_config(args)
    cycle_dir = cfg.cycle_dir(args.cycle_id)
    record = read_json(cycle_dir / "cycle.json", {}) or {}
    summary_path = cycle_dir / "summary.md"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else f"Cycle {args.cycle_id} finished."
    if args.pr_url and record:
        record["pr_url"] = args.pr_url
        write_json(cycle_dir / "cycle.json", record)
    issue = args.issue or (record.get("theme") or {}).get("issue_number")
    Notifier(cfg).finish(int(issue) if issue else None, summary, pr_url=args.pr_url or "",
                         comment_id=args.comment_id, ok=record.get("status") == "done")
    print("📨 notified")
    return 0


def cmd_gallery(args: argparse.Namespace) -> int:
    from .pixelart.gif import scene_to_gif
    from .pixelart.svg import render_svg
    from .utils import atomic_write_bytes, atomic_write_text
    from .visualizer import CHROME, build_lab_scene, build_sprite_sheet, demo_snapshot

    cfg = _load_config(args)
    out = Path(args.out)
    snap = demo_snapshot(cfg.lab.language)
    lab = build_lab_scene(snap, lang=cfg.lab.language)
    sheet = build_sprite_sheet()
    for path in (atomic_write_text(out / "lab-demo.svg", render_svg(lab, scale=4)),
                 atomic_write_bytes(out / "lab-demo.gif", scene_to_gif(lab, scale=3, background=CHROME)),
                 atomic_write_text(out / "sprite-sheet.svg", render_svg(sheet, scale=3))):
        print(f"🖼️  {path}")
    return 0


def cmd_recipes(args: argparse.Namespace) -> int:
    from .recipes import all_recipes

    for r in all_recipes():
        print(f"{r.id:20} {r.title}\n{'':20} {r.title_ja} — {r.field}\n{'':20} keywords: {', '.join(r.keywords[:8])}…\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medusa", description="🐍 Medusa Lab — autonomous multi-agent research lab")
    parser.add_argument("--version", action="version", version=f"medusa-lab {__version__}")
    parser.add_argument("--config", help="path to config.yaml (default: search upwards from the cwd)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prompt", help="ask the Director for this week's theme")
    p.add_argument("--dry-run", action="store_true", help="print the request instead of opening an Issue")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("resolve-theme", help="(CI) derive the theme from the triggering GitHub event")
    p.add_argument("--event", help="override the event name (issue_comment | workflow_dispatch | push)")
    p.add_argument("--out", default=".medusa/theme.json")
    p.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    p.set_defaults(func=cmd_resolve_theme)

    p = sub.add_parser("run", help="run a research cycle")
    p.add_argument("--theme", help="research theme (any language)")
    p.add_argument("--keywords", default="", help="comma-separated search keywords (English recommended)")
    p.add_argument("--mode", choices=["in-silico", "human", "hybrid"])
    p.add_argument("--notes", default="")
    p.add_argument("--theme-file", help="JSON written by `medusa resolve-theme`")
    p.add_argument("--cycle-id", help="e.g. 2026-W39 (default: current ISO week)")
    p.add_argument("--resume", action="store_true", help="reuse finished phases of an interrupted cycle")
    p.add_argument("--offline", action="store_true", help="no LLM: deterministic template agents")
    p.add_argument("--no-network", action="store_true", help="skip literature retrieval")
    p.add_argument("--quick", action="store_true", help="smaller simulations")
    p.add_argument("--no-pdf", action="store_true", help="write LaTeX but do not compile it")
    p.add_argument("--issue", type=int, default=int(os.environ.get("MEDUSA_ISSUE_NUMBER") or 0) or None)
    p.add_argument("--comment-id", type=int, default=int(os.environ.get("MEDUSA_COMMENT_ID") or 0) or None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("demo", help="offline demo cycle (no API key, no network)")
    p.add_argument("--theme", default="SNSにおける新語の拡散と言語進化")
    p.add_argument("--keywords", default="naming game, language evolution, social network")
    p.add_argument("--mode", default="hybrid", choices=["in-silico", "human", "hybrid"])
    p.add_argument("--outputs", default="demo-outputs")
    p.add_argument("--full", action="store_true", help="full-size simulations instead of quick ones")
    p.add_argument("--no-pdf", action="store_true")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("status", help="show the lab status")
    p.add_argument("--pixel", action="store_true", help="truecolor pixel art (needs ~160 columns)")
    p.add_argument("--agent", choices=["scout", "analyst", "coder", "writer", "reviewer", "director"])
    p.add_argument("--watch", action="store_true", help="animate and refresh until Ctrl+C")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("render", help="re-render the dashboard, badges, README block and archive")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("serve", help="serve outputs/ locally (live dashboard)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--outputs", help="directory to serve (default: paths.outputs)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("notify-complete", help="(CI) final Issue comment + chat notification")
    p.add_argument("--cycle-id", required=True)
    p.add_argument("--pr-url", default="")
    p.add_argument("--issue", type=int)
    p.add_argument("--comment-id", type=int)
    p.set_defaults(func=cmd_notify_complete)

    p = sub.add_parser("gallery", help="render showcase images (demo lab + sprite sheet) for the docs")
    p.add_argument("--out", default="docs/assets")
    p.set_defaults(func=cmd_gallery)

    p = sub.add_parser("recipes", help="list the offline research recipes")
    p.set_defaults(func=cmd_recipes)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        return int(args.func(args) or 0)
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["build_parser", "main", "dataclasses"]
