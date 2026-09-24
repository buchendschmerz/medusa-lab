"""The weekly research cycle.

Monday — :meth:`Orchestrator.request_theme` puts the lab to sleep, renders the
"waiting for the Director" dashboard and asks for a theme (GitHub Issue, Slack,
Discord).

After the Director answers — :meth:`Orchestrator.run_cycle` runs::

    theme ─▶ Scout ─▶ Analyst ─▶ route ─┬─▶ Coder ─▶ Writer (paper, PDF) ─┐
                                        │                                ├─▶ Reviewer (+ revisions) ─▶ publish
                                        └─▶ Writer (human proposals) ────┘

``route`` sends each hypothesis to the fully autonomous in-silico track or to a
human-experiment proposal, depending on what it needs and on the weekly mode.
Every phase persists its output, so an interrupted cycle can be resumed.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import jinja2

from .agents import AgentContext, AnalystAgent, CoderAgent, ReviewerAgent, ScoutAgent, WriterAgent
from .config import Config, ConfigError
from .llm import LLM, create_llm
from .models import (
    AnalysisReport,
    CycleRecord,
    Mode,
    PaperDraft,
    ProposalDoc,
    ResearchTheme,
    RoutingDecision,
    ScoutReport,
    SimulationResult,
    Track,
)
from .notifier import IssueLiveReporter, Notifier
from .recipes import all_recipes, get_recipe, match_recipe
from .report import render_cycle_report, render_index
from .routing import route
from .state import (
    AGENT_KEYS,
    AGENT_PROFILES,
    STAGES,
    STATE_STYLES,
    AgentState,
    LabSnapshot,
    StatusBoard,
)
from .utils import atomic_write_text, iso_now, iso_week, read_json, week_of, write_json
from .visualizer import DashboardRenderer, render_lab_svg, render_status_markdown

log = logging.getLogger("medusa.orchestrator")
REQUIRED_TEMPLATES = ("paper_template.tex", "human_proposal_template.md", "weekly_issue.md")
R = TypeVar("R")


class ConsoleReporter:
    """Prints agent transitions; uses collapsible log groups on GitHub Actions."""

    def __init__(self, stream: Any = None, github_actions: bool | None = None) -> None:
        self.stream = stream or sys.stderr
        self.gha = os.environ.get("GITHUB_ACTIONS") == "true" if github_actions is None else github_actions
        self._group_open = False
        self._last: dict[str, tuple[str, str]] = {}
        self._stage = ""

    def __call__(self, snap: LabSnapshot, kind: str) -> None:
        if snap.stage != self._stage and snap.stages.get(snap.stage) == "active":
            self._stage = snap.stage
            info = next((s for s in STAGES if s.key == snap.stage), None)
            if info:
                if self.gha:
                    if self._group_open:
                        print("::endgroup::", file=self.stream)
                    print(f"::group::{info.emoji} {info.en} — {info.ja}", file=self.stream)
                    self._group_open = True
                else:
                    print(f"\n━━ {info.emoji} {info.en} ━━", file=self.stream)
        for key in AGENT_KEYS:
            st = snap.agents[key]
            sig = (st.state.value, st.message)
            if self._last.get(key) != sig:
                self._last[key] = sig
                style = STATE_STYLES[st.state]
                bar = f" {round(st.progress * 100):3d}%" if style.tone == "active" and st.progress else ""
                print(f"  {AGENT_PROFILES[key].emoji} {AGENT_PROFILES[key].name:<8} {style.en:<10}{bar} {st.message}",
                      file=self.stream)
        self.stream.flush()

    def close(self) -> None:
        if self._group_open:
            print("::endgroup::", file=self.stream)
            self._group_open = False


@dataclass
class CycleOutcome:
    record: CycleRecord
    cycle_dir: Path
    summary_md: str
    pr_body_path: Path | None = None


class Orchestrator:
    def __init__(self, cfg: Config, *, llm: LLM | None = None, board: StatusBoard | None = None,
                 notifier: Notifier | None = None, console: bool = True) -> None:
        missing = [name for name in REQUIRED_TEMPLATES if not (cfg.templates_dir / name).is_file()]
        if missing:
            raise ConfigError(f"templates not found in {cfg.templates_dir}: {', '.join(missing)} — run Medusa Lab "
                              "from a checkout of the repository (pip install -e .) or set paths.templates")
        self.cfg = cfg
        self.llm = llm or create_llm(cfg.llm)
        self.board = board or StatusBoard.load(cfg.dashboard_dir / "status.json", lab_name=cfg.lab.name)
        self.renderer = DashboardRenderer.from_config(cfg)
        self.board.subscribe(self.renderer)
        self.console = ConsoleReporter() if console else None
        if self.console:
            self.board.subscribe(self.console)
        self.notifier = notifier

    # ================================================================== Monday
    def request_theme(self, *, dry_run: bool = False, cycle_id: str | None = None) -> dict[str, Any]:
        cfg = self.cfg
        cycle_id = cycle_id or iso_week(tz=cfg.lab.timezone)
        ja = cfg.lab.language == "ja"
        self.board.sleep_all("所長のテーマ待ち" if ja else "waiting for the Director")
        self.board.cycle(cycle_id=cycle_id, theme="", mode=cfg.theme.mode, cycle_status="waiting", stage="theme",
                         stages={s.key: ("active" if s.key == "theme" else "pending") for s in STAGES},
                         counters={}, links={})
        self.board.director("waiting", "Issueで /theme を待っています" if ja else "Waiting for /theme on the Issue")
        self.renderer.render_all(self.board.snapshot)
        title = (f"🐍 [{cfg.lab.name}] {cycle_id} 今週の研究テーマを決めてください" if ja else
                 f"🐍 [{cfg.lab.name}] {cycle_id} What should we research this week?")
        body = self._issue_body(cycle_id)
        notifier = self.notifier or Notifier(cfg)
        result = notifier.ask_director(cycle_id, title, body, dry_run=dry_run)
        if result.issue_url:
            self.board.link("theme_issue", result.issue_url)
        return {"cycle_id": cycle_id, "issue_url": result.issue_url, "issue_number": result.issue_number,
                "sent": result.sent, "printed": result.printed, "errors": result.errors}

    def _issue_body(self, cycle_id: str) -> str:
        cfg = self.cfg
        lang = cfg.lab.language
        history = read_json(cfg.outputs_dir / "history.json", []) or []
        last = history[-1] if history else None
        if last:
            parts = [f"**{last.get('cycle_id')}** — {last.get('theme')} (`{last.get('mode')}`)"]
            if last.get("decision"):
                parts.append(f"査読判定: `{last['decision']}`" if lang == "ja" else f"review: `{last['decision']}`")
            if last.get("pr_url"):
                parts.append(last["pr_url"])
            last_text = " ｜ ".join(parts) if lang == "ja" else " | ".join(parts)
        else:
            last_text = "（まだ研究サイクルの記録はありません）" if lang == "ja" else "(no research cycles yet)"
        recipes = all_recipes()
        week_no = int(cycle_id.split("-W")[1][:2]) if "-W" in cycle_id else 0
        picks = [recipes[(week_no + k * 3) % len(recipes)] for k in range(3)]
        suggestions = [f"{r.title_ja}：{r.summary_ja}" if lang == "ja" else f"{r.title}: {r.summary}" for r in picks]
        if last and last.get("open_question"):
            suggestions.insert(0, ("前回からの宿題：" if lang == "ja" else "Follow-up: ") + last["open_question"])
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(cfg.templates_dir)), autoescape=False,
                                 trim_blocks=True, lstrip_blocks=True)
        return env.get_template("weekly_issue.md").render(
            lang=lang, cycle_id=cycle_id, director=cfg.lab.director, lab_name=cfg.lab.name,
            dashboard_url=cfg.notify.dashboard_url, suggestions=suggestions, last_cycle=last_text,
            example_theme="SNSにおける新語の拡散と言語進化" if lang == "ja" else "How new words spread on social media",
            example_keywords="naming game, language evolution, social network")

    # ================================================================== cycle
    def allocate_cycle_id(self, theme: ResearchTheme) -> str:
        base = theme.cycle_id or iso_week(tz=self.cfg.lab.timezone)
        week = week_of(base)
        for n in range(1, 20):
            candidate = week if n == 1 else f"{week}-{n}"
            existing = read_json(self.cfg.cycle_dir(candidate) / "cycle.json")
            if not existing:
                return candidate
            same = existing.get("theme", {}).get("title") == theme.title
            if same and existing.get("status") != "done":
                return candidate  # resume the unfinished cycle with this theme
        raise RuntimeError(f"too many cycles in {week}")

    def run_cycle(self, theme: ResearchTheme, *, resume: bool = False,
                  live_reporter: IssueLiveReporter | None = None) -> CycleOutcome:
        cfg = self.cfg
        theme.cycle_id = self.allocate_cycle_id(theme)
        cycle_dir = cfg.cycle_dir(theme.cycle_id)
        cycle_dir.mkdir(parents=True, exist_ok=True)
        previous = read_json(cycle_dir / "cycle.json") if resume else None
        record = CycleRecord.from_dict(previous) if previous else CycleRecord(cycle_id=theme.cycle_id, theme=theme)
        record.theme = theme
        record.status = "running"
        record.started_at = record.started_at or iso_now()
        record.error = ""
        record.llm_mode = "offline" if self.llm.offline else "anthropic"
        record.model = self.llm.describe()
        if not resume:
            record.phases_done = []
        write_json(cycle_dir / "cycle.json", record.to_dict())
        if live_reporter:
            self.board.subscribe(live_reporter)
        ctx = AgentContext(cfg, self.llm, self.board, cycle_dir, theme)
        self.board.reset_for_cycle(cycle_id=theme.cycle_id, theme=theme.title, mode=theme.mode.value)
        self.board.stage("theme", "done")
        match = match_recipe(theme)
        record.recipe = match.recipe.id
        current = "scout"
        try:
            # ---------------------------------------------------------- scout
            current = "scout"
            scout = self._phase(record, cycle_dir, "scout", resume, ScoutReport, "scout/literature.json",
                                lambda: ScoutAgent(ctx).run(match, include_foundational=self.llm.offline
                                                            or not match.is_default))
            self.board.counter("papers", len(scout.literature))
            # ---------------------------------------------------------- analyst
            current = "analyst"
            analysis = self._phase(record, cycle_dir, "analyst", resume, AnalysisReport, "analyst/analysis.json",
                                   lambda: AnalystAgent(ctx).run(scout, match, theme.mode))
            routing = route(analysis, theme.mode)
            write_json(cycle_dir / "routing.json", routing.to_dict())
            write_json(cycle_dir / "analyst" / "analysis.json", analysis.to_dict())  # with routing annotations
            self.board.counter("hypotheses_in_silico", len(routing.in_silico))
            self.board.counter("hypotheses_human", len(routing.human))
            if routing.human and routing.write_proposals:
                self.board.agent("analyst", AgentState.WAITING,
                                 self._msg(f"人間向けの仮説{len(routing.human)}件は所長の出番です",
                                           f"{len(routing.human)} hypotheses need the Director"))
            # ---------------------------------------------------------- coder
            current = "coder"
            recipe = get_recipe(analysis.recipe or match.recipe.id)
            if routing.run_simulation:
                sim = self._phase(record, cycle_dir, "coder", resume, SimulationResult, "coder/simulation.json",
                                  lambda: CoderAgent(ctx).run(analysis, recipe))
                self.board.counter("figures", len(sim.figures))
            else:
                sim = SimulationResult(status="skipped")
                self.board.stage("coder", "skipped")
                self.board.agent("coder", AgentState.IDLE, self._msg("今週は計算の出番なし", "No simulation this week"))
            # ---------------------------------------------------------- writer
            current = "writer"
            self.board.stage("writer", "active")
            writer = WriterAgent(ctx)
            draft: PaperDraft | None = None
            if routing.write_paper and sim.ok:
                draft = writer.write_paper(scout, analysis, routing, sim, recipe)
                draft = writer.render_and_build(draft, scout, analysis, sim, routing)
            elif routing.write_paper:
                ctx.notes.append("No paper: the simulation produced no usable results.")
            proposals: list[ProposalDoc] = []
            if routing.write_proposals:
                proposals = writer.write_proposals(analysis, routing, sim, scout)
            if not draft and not proposals:
                self.board.agent("writer", AgentState.IDLE, self._msg("今週は執筆なし", "Nothing to write"))
            else:
                self.board.agent("writer", AgentState.DONE, self._msg(
                    f"論文{'1本' if draft else 'なし'}・提案書{len(proposals)}件", f"paper: {'yes' if draft else 'no'}, "
                    f"{len(proposals)} proposal(s)"), 1.0)
            self.board.stage("writer", "done")
            self.board.counter("proposals", len(proposals))
            # ---------------------------------------------------------- review
            current = "review"
            self.board.stage("review", "active")
            reviewer = ReviewerAgent(ctx)
            if draft:
                round_no = 1
                reviews, meta = reviewer.review_paper(draft, sim, scout, analysis, round_no)
                while meta.decision == "major_revision" and round_no <= cfg.reviewer.max_revision_rounds:
                    self.board.agent("reviewer", AgentState.WAITING,
                                     self._msg(f"改訂待ち（{meta.decision}）", f"Waiting for revision ({meta.decision})"))
                    draft = writer.revise_paper(draft, meta, reviews)
                    draft = writer.render_and_build(draft, scout, analysis, sim, routing)
                    round_no += 1
                    previous = meta.mean_score
                    reviews, meta = reviewer.review_paper(draft, sim, scout, analysis, round_no)
                    if meta.decision == "major_revision" and meta.mean_score <= previous:
                        ctx.notes.append("The revision did not improve the reviews (the remaining issues need new "
                                         "experiments, not rewriting); the revision loop was stopped.")
                        break
                record.decision = meta.decision
                record.review_score = meta.mean_score
                self.board.counter("review_score", round(meta.mean_score, 1))
                self.board.counter("decision", meta.decision)
            if proposals:
                ideas = [i for i in analysis.human_ideas if i.id in {p.idea_id for p in proposals}]
                proposal_reviews = reviewer.review_proposals(ideas)
                proposals = writer.write_proposals(analysis, routing, sim, scout, reviews=proposal_reviews)
                write_json(cycle_dir / "review" / "proposals.json", {k: v.to_dict() for k, v in proposal_reviews.items()})
            if draft or proposals:
                stamp = {"accept": "採択", "minor_revision": "軽微な修正で採択", "major_revision": "大幅修正",
                         "reject": "不採択"}.get(record.decision, "査読完了")
                self.board.agent("reviewer", AgentState.DONE, self._msg(
                    f"判定: {stamp}" + (f"（{record.review_score:.2f}/5）" if record.review_score else ""),
                    f"decision: {record.decision or 'reviewed'}"), 1.0)
                self.board.stage("review", "done")
            else:
                self.board.stage("review", "skipped")
                self.board.agent("reviewer", AgentState.IDLE, self._msg("今週は査読なし", "Nothing to review"))
            # ---------------------------------------------------------- publish
            current = "publish"
            self.board.stage("publish", "active")
            record.proposals = proposals
            if draft:
                record.paper_title = draft.title
                record.paper_tex = draft.tex_path
                record.paper_pdf = draft.pdf_path
            record.counts = {"papers": len(scout.literature), "hypotheses": len(analysis.hypotheses),
                             "in_silico": len(routing.in_silico), "human": len(routing.human),
                             "figures": len(sim.figures), "proposals": len(proposals)}
            record.status = "done"
            record.finished_at = iso_now()
            record.usage = self.llm.usage_report()
            outcome = self._publish(record, cycle_dir, scout, analysis, routing, sim, draft, ctx.notes)
            return outcome
        except Exception as exc:
            record.status = "error"
            record.error = f"{type(exc).__name__}: {exc}"
            record.finished_at = iso_now()
            log.error("cycle failed in %s: %s\n%s", current, exc, traceback.format_exc())
            stage = current if current in {s.key for s in STAGES} else "publish"
            self.board.stage(stage, "error")
            agent = {"review": "reviewer", "publish": "writer"}.get(current, current)
            if agent in AGENT_KEYS:
                self.board.agent(agent, AgentState.ERROR, f"{type(exc).__name__}: {str(exc)[:80]}")
            self.board.cycle(cycle_status="error")
            write_json(cycle_dir / "cycle.json", record.to_dict())
            summary = self._summary_md(record, None, None, None, [], cycle_dir)
            atomic_write_text(cycle_dir / "summary.md", summary)
            self.renderer.render_all(self.board.snapshot)
            raise
        finally:
            if self.console:
                self.console.close()

    # ------------------------------------------------------------------ phases
    def _phase(self, record: CycleRecord, cycle_dir: Path, name: str, resume: bool, kind: type[R], artifact: str,
               run: Callable[[], R]) -> R:
        path = cycle_dir / artifact
        if resume and name in record.phases_done and path.exists():
            data = read_json(path)
            if data is not None:
                self.board.stage(name, "done")
                self.board.agent(name, AgentState.DONE, self._msg("前回の成果を再利用", "Reused previous result"), 1.0)
                return kind.from_dict(data)  # type: ignore[attr-defined]
        self.board.stage(name, "active")
        result = run()
        self.board.stage(name, "done")
        if name not in record.phases_done:
            record.phases_done.append(name)
        write_json(cycle_dir / "cycle.json", record.to_dict())
        return result

    def _msg(self, ja: str, en: str) -> str:
        return ja if self.cfg.lab.language == "ja" else en

    # ------------------------------------------------------------------ publish
    def _publish(self, record: CycleRecord, cycle_dir: Path, scout: ScoutReport, analysis: AnalysisReport,
                 routing: RoutingDecision, sim: SimulationResult, draft: PaperDraft | None,
                 notes: list[str]) -> CycleOutcome:
        cfg = self.cfg
        self.board.director("reviewing", self._msg("PRで論文と実験提案書をご確認ください",
                                                   "Please review the paper and proposals in the PR"))
        self.board.cycle(cycle_status="done")
        self.board.stage("publish", "done")
        snap = self.board.snapshot
        atomic_write_text(cycle_dir / "dashboard.svg", render_lab_svg(snap, scale=cfg.dashboard.scale,
                                                                       lang=cfg.lab.language))
        write_json(cycle_dir / "cycle.json", record.to_dict())
        summary = self._summary_md(record, analysis, routing, sim, notes, cycle_dir, draft=draft)
        atomic_write_text(cycle_dir / "summary.md", summary)
        pr_body = self._pr_body(record, summary)
        pr_path = atomic_write_text(cycle_dir / "pr_body.md", pr_body)
        atomic_write_text(cycle_dir / "report.html", render_cycle_report(cycle_dir, record, lang=cfg.lab.language))
        history = [h for h in (read_json(cfg.outputs_dir / "history.json", []) or []) if h.get("cycle_id") != record.cycle_id]
        open_q = next((p.statement for p in scout.problems if p.kind in ("open_question", "gap")), "")
        history.append({"cycle_id": record.cycle_id, "theme": record.theme.title, "mode": record.theme.mode.value,
                        "status": record.status, "decision": record.decision, "review_score": record.review_score,
                        "paper_title": record.paper_title, "paper_pdf": record.paper_pdf, "paper_tex": record.paper_tex,
                        "proposals": [p.to_dict() for p in record.proposals], "recipe": record.recipe,
                        "llm": record.model, "finished_at": record.finished_at, "pr_url": record.pr_url,
                        "open_question": open_q[:200]})
        write_json(cfg.outputs_dir / "history.json", history)
        atomic_write_text(cfg.outputs_dir / "index.html", render_index(history, lab_name=cfg.lab.name,
                                                                        lang=cfg.lab.language))
        self.renderer.render_all(snap)
        return CycleOutcome(record=record, cycle_dir=cycle_dir, summary_md=summary, pr_body_path=pr_path)

    def _summary_md(self, record: CycleRecord, analysis: AnalysisReport | None, routing: RoutingDecision | None,
                    sim: SimulationResult | None, notes: list[str], cycle_dir: Path, *, draft: PaperDraft | None = None) -> str:
        ja = self.cfg.lab.language == "ja"
        rel = f"{self.cfg.paths.outputs}/weeks/{record.cycle_id}"
        lines = [f"## 🐍 {self.cfg.lab.name} {record.cycle_id} — " + (("研究サイクル完了" if record.status == "done" else
                                                                      "研究サイクル中断") if ja else
                                                                     ("research cycle finished" if record.status == "done"
                                                                      else "research cycle interrupted")), ""]
        lines.append(f"**{'テーマ' if ja else 'Theme'}:** {record.theme.title} ｜ **{'モード' if ja else 'Mode'}:** "
                     f"`{record.theme.mode.value}` ｜ **LLM:** `{record.model}`")
        lines.append("")
        if record.status != "done":
            lines += [f"❌ {record.error}", ""]
        if draft:
            pdf = f"[PDF]({rel}/{draft.pdf_path})" if draft.pdf_path else ("PDF未生成" if ja else "no PDF")
            lines.append(f"📄 **{'論文' if ja else 'Paper'}:** {draft.title} — {pdf} · [LaTeX]({rel}/{draft.tex_path})")
            if record.decision:
                lines.append(f"🖍️ **{'査読判定' if ja else 'Review decision'}:** `{record.decision}` "
                             f"({record.review_score:.2f}/5) · [{'査読記録' if ja else 'reviews'}]({rel}/review/review.md)")
        if sim and sim.ok:
            lines.append("")
            lines.append(f"📊 **{'主な結果' if ja else 'Key findings'}:**")
            lines += [f"- {f}" for f in sim.findings[:4]]
        if record.proposals:
            lines.append("")
            lines.append(f"🧪 **{'【実験提案書】人間がやると面白い仮説＆実験プロトコル' if ja else 'Human-experiment proposals'}:**")
            lines += [f"- [{p.idea_id}: {p.title}]({rel}/{p.path}) — n = {p.sample_size}"
                      f"{' / 条件' if ja else ' per condition'}" for p in record.proposals]
        if analysis and routing:
            lines += ["", f"<details><summary>{'仮説と振り分け' if ja else 'Hypotheses and routing'}</summary>", ""]
            for h in analysis.hypotheses:
                where = ("deferred" if h.id in routing.deferred else h.track.value)
                lines.append(f"- **{h.id}** `{where}` {h.statement}")
            lines += ["", "</details>"]
        if notes:
            lines += ["", f"<details><summary>{'エージェントのメモ' if ja else 'Agent notes'}</summary>", ""]
            lines += [f"- {n}" for n in notes[:20]] + ["", "</details>"]
        usage = record.usage or {}
        cost = usage.get("estimated_cost_usd")
        if cost is not None:
            tot = usage.get("total", {})
            lines += ["", f"<sub>LLM: {tot.get('calls', 0)} calls · {tot.get('input_tokens', 0):,} in / "
                          f"{tot.get('output_tokens', 0):,} out tokens · ≈ ${cost:.2f}</sub>"]
        lines += ["", f"[📑 {'週次レポート' if ja else 'Weekly report'}]({rel}/report.html) · "
                      f"[{'成果物フォルダ' if ja else 'All outputs'}]({rel}/)"]
        return "\n".join(lines) + "\n"

    def _pr_body(self, record: CycleRecord, summary: str) -> str:
        ja = self.cfg.lab.language == "ja"
        status = render_status_markdown(self.board.snapshot, lang=self.cfg.lab.language, heading=False)
        disclosure = ("> [!IMPORTANT]\n> この Pull Request の論文・提案書は Medusa Lab のAIエージェントが自律的に生成したものです。"
                      "マージ前に所長（人間）が内容・引用・倫理面を確認してください。" if ja else
                      "> [!IMPORTANT]\n> The paper and proposals in this PR were generated autonomously by AI agents. "
                      "Please check content, citations and ethics before merging.")
        return f"{summary}\n{disclosure}\n\n<details><summary>🕹️ Lab status</summary>\n\n{status}\n</details>\n"

    def render_dashboard(self) -> list[Path]:
        return self.renderer.render_all(self.board.snapshot)


def theme_track_counts(analysis: AnalysisReport) -> tuple[int, int]:
    return (sum(1 for h in analysis.hypotheses if h.track == Track.IN_SILICO),
            sum(1 for h in analysis.hypotheses if h.track == Track.HUMAN))


__all__ = ["CycleOutcome", "ConsoleReporter", "Mode", "Orchestrator"]
