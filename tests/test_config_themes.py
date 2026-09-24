from __future__ import annotations

from pathlib import Path

import pytest

from medusa.config import Config, ConfigError
from medusa.models import Mode
from medusa.themes import ThemeError, parse_theme_comment, split_keywords, theme_from_inputs

ROOT = Path(__file__).resolve().parents[1]


def test_repo_config_loads_with_defaults() -> None:
    cfg = Config.load(ROOT / "config.yaml", env={})
    assert cfg.llm.model == "claude-opus-5"
    assert cfg.llm.fallbacks == "default"
    assert cfg.theme.mode == "hybrid"
    assert cfg.warnings == []
    assert cfg.templates_dir.name == "templates"


def test_env_overrides_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("llm:\n  provider: anthropic\n  fallbacks: null\ncoder:\n  timeout_sec: '60'\nbogus: 1\n")
    cfg = Config.load(path, env={"MEDUSA_OFFLINE": "1", "MEDUSA_SANDBOX": "strict", "MEDUSA_NO_NETWORK": "yes"})
    assert cfg.llm.provider == "offline"
    assert cfg.llm.fallbacks is None
    assert cfg.coder.sandbox == "strict"
    assert cfg.coder.timeout_sec == 60.0
    assert cfg.scout.network is False
    assert any("bogus" in w for w in cfg.warnings)
    bad = tmp_path / "bad.yaml"
    bad.write_text("theme:\n  mode: sideways\n")
    with pytest.raises(ConfigError):
        Config.load(bad, env={})


def test_mode_aliases() -> None:
    assert Mode.parse("In-Silico") is Mode.IN_SILICO
    assert Mode.parse("ハイブリッド") is Mode.HYBRID
    assert Mode.parse("人間") is Mode.HUMAN
    assert Mode.parse("", Mode.HYBRID) is Mode.HYBRID
    with pytest.raises(ValueError):
        Mode.parse("banana")


def test_parse_theme_comment_full() -> None:
    body = """ありがとう！
> /theme quoted theme must be ignored
/theme SNSにおける新語の拡散と言語進化
特に若者言葉に注目したい

/keywords naming game, language evolution、social network
/mode in-silico
/note 被験者実験のアイデアも
"""
    cmd = parse_theme_comment(body)
    assert cmd is not None
    assert cmd.title == "SNSにおける新語の拡散と言語進化"
    assert cmd.keywords == ["naming game", "language evolution", "social network"]
    assert cmd.mode is Mode.IN_SILICO
    assert "若者言葉" in cmd.notes and "被験者実験" in cmd.notes


def test_parse_theme_comment_variants() -> None:
    assert parse_theme_comment("just chatting, no command") is None
    cmd = parse_theme_comment("/theme: Why do audiences clap in sync?")
    assert cmd and cmd.title == "Why do audiences clap in sync?" and cmd.mode is Mode.HYBRID
    with pytest.raises(ThemeError):
        parse_theme_comment("/theme")
    with pytest.raises(ThemeError):
        parse_theme_comment("/theme ok\n/mode sideways")


def test_theme_from_inputs_and_keywords() -> None:
    cmd = theme_from_inputs("  Opinion   dynamics  ", "a, b, A ,c", "human")
    assert cmd.title == "Opinion dynamics"
    assert cmd.keywords == ["a", "b", "c"]
    assert cmd.mode is Mode.HUMAN
    assert split_keywords("x; y；z\nw") == ["x", "y", "z", "w"]
    with pytest.raises(ThemeError):
        theme_from_inputs("   ")
