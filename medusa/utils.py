"""Small shared helpers: time/week handling, text width, atomic file IO."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("medusa")

# "2026-W39" or, for a second cycle in the same week, "2026-W39-2".
CYCLE_ID_RE = re.compile(r"^(\d{4})-W(\d{2})(?:-(\d{1,2}))?$")
WEEK_IN_TEXT_RE = re.compile(r"\b(\d{4}-W\d{2})\b")

_CJK_RANGES = (
    (0x3000, 0x303F),  # CJK symbols & punctuation
    (0x3040, 0x30FF),  # hiragana, katakana
    (0x3400, 0x4DBF),  # CJK ext A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7AF),  # hangul
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF00, 0xFFEF),  # half/full-width forms
)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat()


def iso_week(when: dt.datetime | None = None, tz: str = "Asia/Tokyo") -> str:
    """ISO week label (e.g. ``2026-W39``) of ``when`` in the lab's timezone."""
    when = when or now_utc()
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    year, week, _ = when.astimezone(ZoneInfo(tz)).isocalendar()
    return f"{year}-W{week:02d}"


def week_of(cycle_id: str) -> str:
    """Strip the per-week sequence suffix: ``2026-W39-2`` -> ``2026-W39``."""
    m = CYCLE_ID_RE.match(cycle_id)
    if not m:
        raise ValueError(f"invalid cycle id: {cycle_id!r}")
    return f"{m[1]}-W{m[2]}"


def week_start(cycle_id: str) -> dt.date:
    m = CYCLE_ID_RE.match(cycle_id)
    if not m:
        raise ValueError(f"invalid cycle id: {cycle_id!r}")
    return dt.date.fromisocalendar(int(m[1]), int(m[2]), 1)


def is_cycle_id(text: str) -> bool:
    return bool(CYCLE_ID_RE.match(text or ""))


def slugify(text: str, max_len: int = 48) -> str:
    """ASCII slug; falls back to a short hash for non-Latin text."""
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()[:max_len].strip("-")
    if len(slug) < 3:
        slug = "theme-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return slug


def contains_cjk(text: str) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in _CJK_RANGES)


def char_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text: str) -> int:
    """Terminal/monospace display width (CJK and emoji count as 2 cells)."""
    return sum(char_width(ch) for ch in text)


def truncate_display(text: str, width: int, ellipsis: str = "…") -> str:
    if display_width(text) <= width:
        return text
    budget = width - display_width(ellipsis)
    out, used = [], 0
    for ch in text:
        w = char_width(ch)
        if used + w > budget:
            break
        out.append(ch)
        used += w
    return "".join(out) + ellipsis


def pad_display(text: str, width: int) -> str:
    text = truncate_display(text, width)
    return text + " " * max(0, width - display_width(text))


def one_line(text: str, limit: int | None = None) -> str:
    flat = " ".join((text or "").split())
    if limit and len(flat) > limit:
        return flat[: limit - 1].rstrip() + "…"
    return flat


def dedupe(items: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    out = []
    for item in items:
        key = item.lower() if isinstance(item, str) else item
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def env_flag(name: str, env: dict[str, str] | None = None) -> bool:
    value = (env if env is not None else os.environ).get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def atomic_write_text(path: Path, text: str) -> Path:
    """Write via a temp file + rename so readers (e.g. the live dashboard) never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=_json_default) + "\n"


def write_json(path: Path, data: Any) -> Path:
    return atomic_write_text(path, to_json(data))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        log.warning("could not parse %s: %s", path, exc)
        return default


def relpath(path: Path, start: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(start).resolve()).as_posix()
    except ValueError:
        return Path(os.path.relpath(path, start)).as_posix()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
