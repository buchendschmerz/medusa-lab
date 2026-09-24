"""Typed configuration loaded from ``config.yaml`` (+ environment overrides)."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .utils import env_flag

MODES = ("in-silico", "human", "hybrid")
PROVIDERS = ("auto", "anthropic", "offline")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SANDBOXES = ("basic", "strict")
LATEX_ENGINES = ("auto", "latexmk", "pdflatex", "lualatex", "tectonic")
PERSONAS = ("methodologist", "domain_expert", "skeptic")

CONFIG_FILENAME = "config.yaml"
PACKAGE_ROOT = Path(__file__).resolve().parent


class ConfigError(ValueError):
    pass


@dataclass
class LabConfig:
    name: str = "Medusa Lab"
    director: str = "所長"
    language: str = "ja"
    timezone: str = "Asia/Tokyo"


@dataclass
class ThemeConfig:
    current: str = ""
    keywords: list[str] = field(default_factory=list)
    mode: str = "hybrid"
    notes: str = ""


@dataclass
class LLMConfig:
    provider: str = "auto"
    model: str = "claude-opus-5"
    effort: str = "high"
    max_tokens: int = 64000
    thinking: str = "adaptive"
    fallbacks: str | None = "default"
    timeout_sec: float = 900.0


@dataclass
class ScoutConfig:
    sources: list[str] = field(default_factory=lambda: ["arxiv", "openalex"])
    max_papers: int = 12
    network: bool = True
    timeout_sec: float = 30.0


@dataclass
class AnalystConfig:
    max_hypotheses: int = 4
    max_human_proposals: int = 2


@dataclass
class CoderConfig:
    timeout_sec: float = 300.0
    max_attempts: int = 3
    sandbox: str = "basic"
    require_isolation: bool = False  # strict mode: fail instead of falling back to basic isolation
    memory_mb: int = 2048
    quick: bool = False


@dataclass
class WriterConfig:
    paper_language: str = "en"
    compile_pdf: bool = True
    latex_engine: str = "auto"


@dataclass
class ReviewerConfig:
    personas: list[str] = field(default_factory=lambda: list(PERSONAS))
    max_revision_rounds: int = 2
    accept_threshold: float = 3.5


@dataclass
class NotifyConfig:
    github_issue: bool = True
    issue_label: str = "medusa:theme-request"
    slack_webhook_env: str = "SLACK_WEBHOOK_URL"
    discord_webhook_env: str = "DISCORD_WEBHOOK_URL"
    live_status_comment: bool = True
    dashboard_url: str = ""


@dataclass
class DashboardConfig:
    scale: int = 4
    gif_scale: int = 3
    animate: bool = True
    gif: bool = True
    update_readme: bool = True


@dataclass
class PathsConfig:
    outputs: str = "outputs"
    templates: str = "templates"


_SECTIONS: dict[str, type] = {
    "lab": LabConfig,
    "theme": ThemeConfig,
    "llm": LLMConfig,
    "scout": ScoutConfig,
    "analyst": AnalystConfig,
    "coder": CoderConfig,
    "writer": WriterConfig,
    "reviewer": ReviewerConfig,
    "notify": NotifyConfig,
    "dashboard": DashboardConfig,
    "paths": PathsConfig,
}


def _coerce(value: Any, default: Any, where: str) -> Any:
    """Coerce YAML/env values to the type of the field's default."""
    if value is None:
        return None
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            return value.strip().lower() in {"1", "true", "yes", "on"}
        raise ConfigError(f"{where}: expected a boolean, got {value!r}")
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: expected an integer, got {value!r}") from exc
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: expected a number, got {value!r}") from exc
    if isinstance(default, list):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (list, tuple)):
            return [str(v).strip() for v in value if str(v).strip()]
        raise ConfigError(f"{where}: expected a list, got {value!r}")
    return str(value) if not isinstance(value, str) else value


def _build_section(cls: type, data: Mapping[str, Any] | None, name: str, warnings: list[str]) -> Any:
    instance = cls()
    if data is None:
        return instance
    if not isinstance(data, Mapping):
        raise ConfigError(f"section '{name}' must be a mapping")
    known = {f.name for f in dataclasses.fields(cls)}
    for key, value in data.items():
        if key not in known:
            warnings.append(f"unknown config key '{name}.{key}' (ignored)")
            continue
        setattr(instance, key, _coerce(value, getattr(instance, key), f"{name}.{key}"))
    return instance


@dataclass
class Config:
    lab: LabConfig = field(default_factory=LabConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    scout: ScoutConfig = field(default_factory=ScoutConfig)
    analyst: AnalystConfig = field(default_factory=AnalystConfig)
    coder: CoderConfig = field(default_factory=CoderConfig)
    writer: WriterConfig = field(default_factory=WriterConfig)
    reviewer: ReviewerConfig = field(default_factory=ReviewerConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    root: Path = field(default_factory=Path.cwd)
    source: Path | None = None
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ loading
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None, *, root: Path | None = None) -> Config:
        data = data or {}
        if not isinstance(data, Mapping):
            raise ConfigError("config root must be a mapping")
        warnings: list[str] = []
        sections = {name: _build_section(sec, data.get(name), name, warnings) for name, sec in _SECTIONS.items()}
        for key in data:
            if key not in _SECTIONS:
                warnings.append(f"unknown config section '{key}' (ignored)")
        cfg = cls(**sections, root=Path(root or Path.cwd()).resolve(), warnings=warnings)
        return cfg

    @classmethod
    def load(cls, path: str | Path | None = None, *, root: str | Path | None = None,
             env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        cfg_path = Path(path) if path else find_config(Path(root) if root else Path.cwd())
        data: Any = {}
        if cfg_path is not None:
            if not cfg_path.is_file():
                raise ConfigError(f"config file not found: {cfg_path}")
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        base = Path(root) if root else (cfg_path.parent if cfg_path else Path.cwd())
        cfg = cls.from_dict(data, root=base)
        cfg.source = cfg_path.resolve() if cfg_path else None
        cfg.apply_env(env)
        cfg.validate()
        return cfg

    def apply_env(self, env: Mapping[str, str]) -> None:
        env = dict(env)
        if env_flag("MEDUSA_OFFLINE", env):
            self.llm.provider = "offline"
        if env.get("MEDUSA_MODEL"):
            self.llm.model = env["MEDUSA_MODEL"].strip()
        if env.get("MEDUSA_SANDBOX"):
            self.coder.sandbox = env["MEDUSA_SANDBOX"].strip().lower()
        if env_flag("MEDUSA_NO_NETWORK", env):
            self.scout.network = False
        if env_flag("MEDUSA_QUICK", env):
            self.coder.quick = True
        if env_flag("MEDUSA_REQUIRE_ISOLATION", env):
            self.coder.require_isolation = True

    def validate(self) -> None:
        checks = [
            ("theme.mode", self.theme.mode, MODES),
            ("llm.provider", self.llm.provider, PROVIDERS),
            ("llm.effort", self.llm.effort, EFFORTS),
            ("llm.thinking", self.llm.thinking, ("adaptive", "none")),
            ("coder.sandbox", self.coder.sandbox, SANDBOXES),
            ("writer.latex_engine", self.writer.latex_engine, LATEX_ENGINES),
            ("writer.paper_language", self.writer.paper_language, ("en", "ja")),
            ("lab.language", self.lab.language, ("en", "ja")),
        ]
        for where, value, allowed in checks:
            if value not in allowed:
                raise ConfigError(f"{where} must be one of {', '.join(allowed)} (got {value!r})")
        unknown = [p for p in self.reviewer.personas if p not in PERSONAS]
        if unknown:
            raise ConfigError(f"reviewer.personas: unknown persona(s) {unknown}; choose from {PERSONAS}")
        if self.llm.fallbacks in ("", "null", "none", "None"):
            self.llm.fallbacks = None
        if self.coder.max_attempts < 1:
            raise ConfigError("coder.max_attempts must be >= 1")
        if not 1 <= self.dashboard.scale <= 16 or not 1 <= self.dashboard.gif_scale <= 16:
            raise ConfigError("dashboard scales must be between 1 and 16")

    # ------------------------------------------------------------------ paths
    @property
    def outputs_dir(self) -> Path:
        return (self.root / self.paths.outputs).resolve()

    @property
    def templates_dir(self) -> Path:
        candidate = (self.root / self.paths.templates).resolve()
        if candidate.is_dir():
            return candidate
        bundled = PACKAGE_ROOT.parent / "templates"  # editable install / repo checkout
        return bundled if bundled.is_dir() else candidate

    @property
    def dashboard_dir(self) -> Path:
        return self.outputs_dir / "dashboard"

    @property
    def readme_path(self) -> Path:
        return self.root / "README.md"

    def cycle_dir(self, cycle_id: str) -> Path:
        return self.outputs_dir / "weeks" / cycle_id


def find_config(start: Path) -> Path | None:
    """Look for config.yaml in ``start`` and its parents (stops at a git root)."""
    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break
    return None
