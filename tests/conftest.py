from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medusa.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    """An offline, network-free, quick config writing into a temporary outputs dir."""
    config = Config.from_dict({
        "llm": {"provider": "offline"},
        "scout": {"network": False},
        "coder": {"quick": True, "timeout_sec": 120},
        "writer": {"compile_pdf": False},
        "dashboard": {"update_readme": False, "gif": False},
        "paths": {"outputs": str(tmp_path / "outputs"), "templates": str(ROOT / "templates")},
    }, root=tmp_path)
    config.validate()
    return config


def have_latex() -> bool:
    return bool(shutil.which("pdflatex") or shutil.which("lualatex") or shutil.which("tectonic"))
