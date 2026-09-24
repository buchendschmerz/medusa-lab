"""Turning the Director's input (Issue comment, workflow inputs, config.yaml) into a research theme.

Issue comment syntax::

    /theme SNSにおける新語の拡散と言語進化
    (optional extra lines describing the theme)
    /keywords naming game, language evolution
    /mode hybrid
    /note 被験者実験のアイデアも多めに

Quoted lines (``> ...``, e.g. from a reply that quotes the Issue body) are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Config
from .models import Mode, ResearchTheme

COMMAND_RE = re.compile(r"^/(theme|keywords?|mode|notes?)\b[:：]?\s*(.*)$", re.I)
MAX_THEME_CHARS = 300
MAX_NOTES_CHARS = 2000


class ThemeError(ValueError):
    pass


@dataclass
class ThemeCommand:
    title: str
    keywords: list[str] = field(default_factory=list)
    mode: Mode = Mode.HYBRID
    notes: str = ""

    def to_theme(self, *, cycle_id: str = "", source: str = "cli", issue_number: int | None = None,
                 requested_by: str = "") -> ResearchTheme:
        return ResearchTheme(title=self.title, keywords=self.keywords, mode=self.mode, notes=self.notes,
                             cycle_id=cycle_id, source=source, issue_number=issue_number, requested_by=requested_by)


def split_keywords(text: str) -> list[str]:
    parts = re.split(r"[,、，;；\n]", text or "")
    out: list[str] = []
    for part in parts:
        part = " ".join(part.split())
        if part and part.lower() not in (p.lower() for p in out):
            out.append(part[:60])
    return out[:12]


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text or "")
    return " ".join(text.split())[:limit].strip()


def parse_theme_comment(body: str, default_mode: Mode = Mode.HYBRID) -> ThemeCommand | None:
    """Parse ``/theme`` commands; returns None when the comment has no /theme."""
    title_lines: list[str] = []
    notes: list[str] = []
    keywords: list[str] = []
    mode = default_mode
    current: str | None = None
    seen_theme = False
    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line.startswith(">") or line.startswith("```"):
            continue
        m = COMMAND_RE.match(line)
        if m:
            cmd, rest = m.group(1).lower(), m.group(2).strip()
            if cmd == "theme":
                seen_theme = True
                current = "theme"
                if rest:
                    title_lines.append(rest)
            elif cmd.startswith("keyword"):
                current = "keywords"
                keywords += split_keywords(rest)
            elif cmd == "mode":
                current = None
                try:
                    mode = Mode.parse(rest.split()[0] if rest else "", default_mode)
                except ValueError as exc:
                    raise ThemeError(str(exc)) from exc
            else:
                current = "notes"
                if rest:
                    notes.append(rest)
            continue
        if not line:
            if current == "theme" and title_lines:
                current = "theme-details"
            continue
        if current == "theme":
            title_lines.append(line)
        elif current == "theme-details":
            notes.append(line)
        elif current == "keywords":
            keywords += split_keywords(line)
        elif current == "notes":
            notes.append(line)
    if not seen_theme:
        return None
    title = _clean(title_lines[0] if title_lines else "", MAX_THEME_CHARS)
    if len(title_lines) > 1:
        notes = [*title_lines[1:], *notes]
    if not title:
        raise ThemeError("the /theme command needs a theme, e.g. `/theme SNSにおける新語の拡散`")
    return ThemeCommand(title=title, keywords=keywords[:12], mode=mode, notes=_clean(" ".join(notes), MAX_NOTES_CHARS))


def theme_from_inputs(theme: str, keywords: str = "", mode: str = "", notes: str = "",
                      default_mode: Mode = Mode.HYBRID) -> ThemeCommand:
    title = _clean(theme, MAX_THEME_CHARS)
    if not title:
        raise ThemeError("empty theme")
    return ThemeCommand(title=title, keywords=split_keywords(keywords), mode=Mode.parse(mode, default_mode),
                        notes=_clean(notes, MAX_NOTES_CHARS))


def theme_from_config(cfg: Config) -> ThemeCommand | None:
    if not cfg.theme.current.strip():
        return None
    return ThemeCommand(title=_clean(cfg.theme.current, MAX_THEME_CHARS), keywords=list(cfg.theme.keywords)[:12],
                        mode=Mode.parse(cfg.theme.mode, Mode.HYBRID), notes=_clean(cfg.theme.notes, MAX_NOTES_CHARS))
