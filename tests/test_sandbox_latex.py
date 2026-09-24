from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import ROOT, have_latex

from medusa.latex import Sanitizer, TexSafe, build_pdf, escape_text, latex_env, mathify
from medusa.sandbox import Sandbox, screen_code

RUNTIME = (ROOT / "medusa" / "runtime" / "medusa_sim.py").read_text()


@pytest.mark.parametrize("code", [
    "import os\nos.system('ls')",
    "open('/etc/passwd').read()",
    "().__class__.__base__.__subclasses__()",
    "import numpy as np\nnp.load('x.npy')",
    "from scipy import io",
    "import operator\noperator.attrgetter('__class__')(1)",
    "getattr(1, 'real')",
    "g = (i for i in [1])\ng.gi_frame.f_globals",
    "import medusa_sim as sim\nsim._RESULTS.clear()",
    "import socket",
    # aliasing a banned builtin must not slip past the call-only check
    "e = eval\ne('1 + 1')",
    "g = getattr\ng(object, 'x')",
    # reaching builtins/globals through a dunder *string* (subscript or getattr)
    "d = {}\nb = d['__builtins__']",
    "k = '__globals__'",
    # low-level os/ctypes/frame primitives as attributes
    "import numpy\nnumpy.getppid()",
    "import numpy\nnumpy.arange(3).read(0)",
    "x = (1).__reduce__()",
])
def test_screen_rejects(code: str) -> None:
    assert screen_code(code)


def test_screen_accepts_normal_simulation() -> None:
    code = ("import math, random\nimport medusa_sim as sim\nclass A:\n    def __init__(self):\n        self.spread = 1\n"
            "sim.seed(1)\nsim.save_table('t', ['x', 'y'], [[1, 2]])\nsim.finish('ok')\n")
    assert screen_code(code) == []


def test_screen_accepts_every_recipe_script() -> None:
    from medusa.recipes import all_recipes

    for recipe in all_recipes():
        assert screen_code(recipe.script_source()) == [], recipe.id


def test_figure_metadata_is_coerced_so_bad_types_cannot_crash_parsing(tmp_path: Path, monkeypatch) -> None:
    # A generated script passing a non-string label/caption must not raise TypeError in FigureSpec.from_dict;
    # medusa_sim.figure() coerces the metadata to strings so the cycle survives (counts as a normal figure).
    import importlib.util

    from medusa.models import FigureSpec

    monkeypatch.chdir(tmp_path)
    (tmp_path / "params.json").write_text("{}")
    runtime_path = ROOT / "medusa" / "runtime" / "medusa_sim.py"
    spec = importlib.util.spec_from_file_location("medusa_sim_test", runtime_path)
    sim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sim)
    sim.save_table("t", ["a", "b"], [[1, 2]])
    sim.figure("fig_x", "t", "a", ["b"], labels=[1], caption=42)
    figures = [FigureSpec.from_dict(f) for f in sim._RESULTS["figures"]]
    assert figures[0].labels == ["1"] and figures[0].caption == "42"


def test_sandbox_runs_and_collects(tmp_path: Path) -> None:
    code = ("import medusa_sim as sim\nsim.seed(3)\nsim.progress(0.5, 'half')\n"
            "sim.save_table('t', ['x', 'y'], [[1, 2], [2, 4]])\nsim.metric('m', 1.5)\n"
            "sim.figure('f', 't', 'x', ['y'])\nsim.finish('done')\n")
    lines: list[str] = []
    res = Sandbox(timeout_sec=30).execute({"sim.py": code, "medusa_sim.py": RUNTIME, "params.json": "{}"}, "sim.py",
                                          tmp_path, on_line=lines.append)
    assert res.ok, res.tail()
    data = json.loads((tmp_path / "results.json").read_text())
    assert data["metrics"]["m"] == 1.5 and data["seed"] == 3
    assert (tmp_path / "data" / "t.dat").read_text().startswith("x y")
    assert any(line.startswith("[medusa-progress] 0.500") for line in lines)
    assert not (tmp_path / "sim.py").exists()  # inputs are not copied back


def test_sandbox_env_is_scrubbed_and_timeouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    res = Sandbox(timeout_sec=10).execute({"p.py": "import os\nprint(os.environ.get('ANTHROPIC_API_KEY'))\n"},
                                          "p.py", tmp_path / "a")
    assert res.ok and "sk-secret" not in res.stdout
    slow = Sandbox(timeout_sec=1).execute({"p.py": "import time\ntime.sleep(30)\n"}, "p.py", tmp_path / "b")
    assert slow.timed_out and not slow.ok


def test_sandbox_does_not_follow_symlinks(tmp_path: Path) -> None:
    code = "import os\nos.symlink('/etc/hostname', 'data/leak.dat')\nopen('data/ok.dat', 'w').write('x 1\\n')\n"
    Sandbox(timeout_sec=10).execute({"p.py": code}, "p.py", tmp_path)
    assert (tmp_path / "data" / "ok.dat").exists()
    assert not (tmp_path / "data" / "leak.dat").exists()


def test_sanitizer_blocks_dangerous_latex() -> None:
    s = Sanitizer(cite_keys={"good2020a"}, labels={"fig:x"})
    out = s.paragraph_text(r"See \citep{good2020a,bad} and Figure~\ref{fig:x}. \input{/etc/passwd} "
                           r"$\directlua{os.exit()}$ $x^2 + \alpha$ 50% & #1")
    assert r"\citep{good2020a}" in out and "bad" not in out
    assert r"\input" not in out.replace(r"\textbackslash{}input", "")
    assert r"\directlua" not in out.replace(r"\textbackslash{}directlua", "")
    assert r"$x^2 + \alpha$" in out and r"50\% \& \#1" in out
    assert "cite:bad" in s.dropped


def test_markdown_lists_and_escape() -> None:
    out = Sanitizer().paragraph_text("Intro\n- one\n- two\n\n1. a\n2. b")
    assert r"\begin{itemize}" in out and r"\end{enumerate}" in out
    assert escape_text("a_b & {c}") == r"a\_b \& \{c\}"
    assert escape_text("中文") == "??" and escape_text("中文", unicode_ok=True) == "中文"
    assert mathify("grows as N^1.75 (R^2=1.00)") == "grows as $N^{1.75}$ ($R^{2}$=1.00)"


def test_latex_env_escapes_by_default(tmp_path: Path) -> None:
    (tmp_path / "t.tex").write_text(r"\VAR{plain} | \VAR{safe}")
    env = latex_env(tmp_path)
    out = env.get_template("t.tex").render(plain="50% & $", safe=TexSafe(r"\emph{x}"))
    assert out == r"50\% \& \$ | \emph{x}"


@pytest.mark.skipif(not have_latex(), reason="no LaTeX engine installed")
def test_build_pdf_minimal(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-VALUE\n")
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "paper.tex").write_text(
        f"\\documentclass{{article}}\\begin{{document}}Leak: \\input{{{secret}}}\\end{{document}}\n")
    result = build_pdf(evil / "paper.tex")
    # openin_any=p forbids reading absolute paths outside the working directory
    assert not result.ok
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "paper.tex").write_text("\\documentclass{article}\\begin{document}Hello $x^2$\\end{document}\n")
    good = build_pdf(ok / "paper.tex")
    assert good.ok and good.pdf and good.pdf.stat().st_size > 1000
