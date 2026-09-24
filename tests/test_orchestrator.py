from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import have_latex
from fakes import FakeLLM

from medusa.cli import main
from medusa.models import Mode, ResearchTheme
from medusa.orchestrator import Orchestrator
from medusa.utils import read_json


def _run(cfg, title: str, mode: Mode = Mode.HYBRID, **kw):  # type: ignore[no-untyped-def]
    orch = Orchestrator(cfg, console=False, **kw)
    outcome = orch.run_cycle(ResearchTheme(title=title, mode=mode, cycle_id="2026-W39"))
    return orch, outcome


def test_offline_hybrid_cycle_produces_everything(cfg) -> None:  # type: ignore[no-untyped-def]
    orch, outcome = _run(cfg, "SNSにおける新語の拡散と言語進化")
    d = outcome.cycle_dir
    record = outcome.record
    assert record.status == "done" and record.recipe == "naming_game"
    for rel in ("scout/literature.json", "scout/references.bib", "analyst/analysis.json", "routing.json",
                "coder/results.json", "coder/data/convergence.dat", "paper/paper.tex", "review/review.md",
                "proposals/README.md", "report.html", "summary.md", "pr_body.md", "dashboard.svg", "cycle.json"):
        assert (d / rel).exists(), rel
    assert len(record.proposals) == 2 and record.decision in ("accept", "minor_revision", "major_revision")
    tex = (d / "paper/paper.tex").read_text()
    assert "\\begin{axis}" in tex and "\\bibitem" in tex and "AI-generated manuscript" in tex
    snap = orch.board.snapshot
    assert snap.cycle_status == "done" and snap.director.state == "reviewing"
    assert all(v in ("done", "skipped") for v in snap.stages.values())
    # nobody is left "working" once the cycle is published
    assert all(a.style.tone in ("done", "wait", "idle") for a in snap.agents.values()), snap.agents
    history = read_json(cfg.outputs_dir / "history.json")
    assert history[-1]["cycle_id"] == "2026-W39"
    assert (cfg.outputs_dir / "index.html").exists() and (cfg.dashboard_dir / "lab.svg").exists()
    proposal = next((d / "proposals").glob("E1-*.md")).read_text()
    assert "【実験提案書】" in proposal and "n = 12" in proposal and "Reviewer Agent の査読コメント" in proposal


def test_human_only_mode_skips_simulation(cfg) -> None:  # type: ignore[no-untyped-def]
    orch, outcome = _run(cfg, "世論の分断とエコーチェンバー", Mode.HUMAN)
    assert outcome.record.status == "done" and not outcome.record.paper_tex
    assert outcome.record.proposals
    assert orch.board.snapshot.stages["coder"] == "skipped"
    assert not (outcome.cycle_dir / "paper").exists()


def test_in_silico_mode_skips_proposals(cfg) -> None:  # type: ignore[no-untyped-def]
    _, outcome = _run(cfg, "Why do audiences clap in sync?", Mode.IN_SILICO)
    assert outcome.record.recipe == "kuramoto" and outcome.record.paper_tex and not outcome.record.proposals
    routing = read_json(outcome.cycle_dir / "routing.json")
    assert routing["deferred"] and not routing["write_proposals"]


def test_second_theme_in_same_week_gets_new_cycle_id(cfg) -> None:  # type: ignore[no-untyped-def]
    _run(cfg, "Opinion polarization", Mode.HUMAN)
    orch = Orchestrator(cfg, console=False)
    outcome = orch.run_cycle(ResearchTheme(title="Zipf law of words", mode=Mode.HUMAN, cycle_id="2026-W39"))
    assert outcome.record.cycle_id == "2026-W39-2"


def test_llm_mode_with_fake_model(cfg) -> None:  # type: ignore[no-untyped-def]
    fake = FakeLLM(bad_code_first=True)
    orch, outcome = _run(cfg, "How slang words spread", llm=fake)
    record = outcome.record
    assert record.status == "done" and record.llm_mode == "anthropic"
    sim = read_json(outcome.cycle_dir / "coder/simulation.json")
    assert sim["source"] == "llm" and sim["attempts"] == 2  # screening rejected attempt 1, attempt 2 ran
    attempts = read_json(outcome.cycle_dir / "coder/attempts.json")
    assert attempts[0]["stage"] == "screen" and any("os" in p for p in attempts[0]["problems"])
    routing = read_json(outcome.cycle_dir / "routing.json")
    assert "H2" in routing["human"]  # the mislabelled survey hypothesis was re-routed / proposed
    tex = (outcome.cycle_dir / "paper/paper.tex").read_text()
    assert "\\citep{steels1995selforganizing}" in tex and "unknown2020" not in tex
    assert "\\input{/etc/passwd}" not in tex and "textbackslash{}input" in tex
    purposes = {c["purpose"] for c in fake.calls}
    assert {"scout", "analyst", "coder", "writer", "reviewer"} <= purposes
    reviewer_calls = [c for c in fake.calls if c["purpose"] == "reviewer" and c["cache_prefix"]]
    assert reviewer_calls and all(c["cache_prefix"] == reviewer_calls[0]["cache_prefix"] for c in reviewer_calls)
    assert record.usage["total"]["calls"] == len(fake.calls)


def test_llm_major_revision_triggers_rewrite(cfg) -> None:  # type: ignore[no-untyped-def]
    fake = FakeLLM(bad_code_first=False, review_decision="major_revision", review_score=2.5)
    cfg.reviewer.max_revision_rounds = 1
    _, outcome = _run(cfg, "How slang words spread", llm=fake)
    assert (outcome.cycle_dir / "review/round2.json").exists()
    draft = read_json(outcome.cycle_dir / "paper/draft.json")
    assert draft["revision"] == 1 and draft["response_to_reviewers"]
    assert "Response to reviewers" in (outcome.cycle_dir / "paper/paper.tex").read_text()


def test_recipe_fallback_paper_describes_the_recipe(cfg) -> None:  # type: ignore[no-untyped-def]
    # Every LLM code attempt is a screening-rejected payload, so the Coder falls back to the vetted
    # recipe. The paper must then describe the recipe's model/equations, not the abandoned LLM design.
    cfg.coder.max_attempts = 2
    fake = FakeLLM(always_bad_code=True)
    _, outcome = _run(cfg, "How slang words spread", Mode.IN_SILICO, llm=fake)
    sim = read_json(outcome.cycle_dir / "coder/simulation.json")
    assert sim["source"] == "recipe-fallback"
    analysis = read_json(outcome.cycle_dir / "analyst/analysis.json")
    recipe_id = analysis["recipe"]
    # the persisted model was rewritten to the recipe's, and every in-silico hypothesis matches it
    from medusa.agents.analyst import insilico_from_recipe
    from medusa.recipes import get_recipe

    model, _, hyps = insilico_from_recipe(get_recipe(recipe_id), cfg.coder.quick)
    assert analysis["model"]["name"] == model.name
    assert analysis["model"]["equations"] == model.equations
    # the equations block is rendered from analysis.model, so the abandoned LLM equation must be gone
    # and the recipe's own equations present (the LLM's free-text title/prose is not our concern here)
    tex = (outcome.cycle_dir / "paper/paper.tex").read_text()
    assert "x_{t+1}" not in tex
    assert any(frag in tex for frag in ("N_w", "convergence", "consensus"))  # naming-game observables


@pytest.mark.skipif(not have_latex(), reason="no LaTeX engine installed")
def test_offline_cycle_builds_pdf(cfg) -> None:  # type: ignore[no-untyped-def]
    cfg.writer.compile_pdf = True
    _, outcome = _run(cfg, "Residential segregation in cities", Mode.IN_SILICO)
    assert outcome.record.paper_pdf == "paper/paper.pdf"
    assert (outcome.cycle_dir / "paper/paper.pdf").stat().st_size > 10_000


def test_cli_resolve_theme_from_comment(cfg, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(f"paths:\n  outputs: {cfg.outputs_dir}\n")
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("EVENT_NAME", "issue_comment")
    monkeypatch.setenv("COMMENT_BODY", "/theme 拍手の同期\n/mode human")
    monkeypatch.setenv("ISSUE_TITLE", "🐍 [Medusa Lab] 2026-W38 今週の研究テーマ")
    monkeypatch.setenv("ISSUE_NUMBER", "12")
    monkeypatch.setenv("COMMENT_ID", "345")
    theme_file = tmp_path / "theme.json"
    assert main(["--config", str(cfg_path), "resolve-theme", "--out", str(theme_file), "--github-output", str(out_file)]) == 0
    outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines())
    assert outputs["should_run"] == "true" and outputs["cycle_id"] == "2026-W38" and outputs["mode"] == "human"
    data = json.loads(theme_file.read_text())
    assert data["title"] == "拍手の同期" and data["issue_number"] == 12 and data["comment_id"] == 345

    monkeypatch.setenv("COMMENT_BODY", "thanks!")
    out_file.write_text("")
    assert main(["--config", str(cfg_path), "resolve-theme", "--out", str(theme_file), "--github-output", str(out_file)]) == 0
    assert "should_run=false" in out_file.read_text()
