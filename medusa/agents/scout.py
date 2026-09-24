"""🔍 Scout — literature search and research-gap extraction."""

from __future__ import annotations

import time

from ..integrations.literature import (
    SEARCHERS,
    assign_keys,
    mine_gap_sentences,
    rank_and_dedupe,
    to_bibtex,
)
from ..llm import LLMError, arr, enum, obj, s
from ..models import LiteratureItem, ResearchProblem, ScoutReport
from ..recipes import RecipeMatch
from ..state import AgentState
from ..utils import dedupe, write_json
from .base import UNTRUSTED_NOTE, Agent, documents_block

SYSTEM = ("You are Scout, the literature specialist of Medusa Lab, an autonomous research lab. You turn a research "
          "theme chosen by the human Director into precise English search queries and extract concrete, testable "
          "research gaps from retrieved abstracts. Be specific and conservative: only claim what the abstracts "
          "support, and cite them by their document id.")

QUERY_SCHEMA = obj({"queries": arr(s("an English literature-search query of 2-6 words")),
                    "rationale": s("one sentence")})

PROBLEM_SCHEMA = obj({
    "summary": s("3-5 sentence overview of what the literature says about the theme"),
    "problems": arr(obj({
        "statement": s("a concrete open research question"),
        "motivation": s("why it matters, 1-2 sentences"),
        "evidence": arr(s("document id supporting this gap")),
        "kind": enum(["gap", "open_question", "contradiction", "extension"]),
    })),
})


class ScoutAgent(Agent):
    key = "scout"

    def run(self, match: RecipeMatch | None, *, include_foundational: bool = True) -> ScoutReport:
        sc = self.cfg.scout
        self.status(AgentState.THINKING, self.msg("検索クエリを検討中", "Planning search queries"), 0.05)
        queries = self._queries(match)
        report = ScoutReport(queries=queries)
        found: list[LiteratureItem] = []
        if sc.network and sc.sources:
            per_query = max(3, sc.max_papers // max(1, len(queries)) + 2)
            jobs = [(q, src) for q in queries for src in sc.sources if src in SEARCHERS]
            for i, (query, source) in enumerate(jobs):
                self.status(AgentState.SEARCHING,
                            self.msg(f"{source} で「{query}」を検索中", f"Searching {source}: {query}"),
                            0.1 + 0.5 * i / max(1, len(jobs)))
                try:
                    items = SEARCHERS[source](query, per_query, sc.timeout_sec)
                    found.extend(items)
                    if source not in report.sources_used:
                        report.sources_used.append(source)
                except Exception as exc:  # network errors must not stop the cycle
                    report.notes.append(f"{source} search failed for '{query}': {type(exc).__name__}: {exc}")
                    self.log.warning("%s search failed: %s", source, exc)
                if source == "arxiv" and i < len(jobs) - 1:
                    time.sleep(3)  # arXiv API etiquette: at most one request every 3 seconds
        else:
            report.notes.append("Literature retrieval skipped (network disabled).")
        literature = rank_and_dedupe(found, queries, sc.max_papers)
        foundational = list(match.recipe.references) if (match and include_foundational) else []
        assign_keys(foundational)
        assign_keys(literature, taken=[f.key for f in foundational])
        report.literature = foundational + literature

        self.status(AgentState.READING, self.msg(f"{len(report.literature)}本の文献を読解中",
                                                 f"Reading {len(report.literature)} papers"), 0.7)
        if self.llm.offline:
            self._offline_problems(report, match)
        else:
            try:
                self._llm_problems(report)
            except LLMError as exc:
                self.note(f"LLM problem extraction failed ({exc}); using heuristic extraction.")
                self._offline_problems(report, match)
        self._save(report)
        self.status(AgentState.DONE, self.msg(f"文献{len(report.literature)}本・課題{len(report.problems)}件を抽出",
                                              f"{len(report.literature)} papers, {len(report.problems)} gaps"), 1.0)
        return report

    # ------------------------------------------------------------------ queries
    def _queries(self, match: RecipeMatch | None) -> list[str]:
        theme = self.theme
        ascii_keywords = [k for k in theme.keywords if k.isascii()]
        base = ascii_keywords[:3]
        if self.llm.offline:
            queries = list(base)
            if theme.title.isascii():
                queries.insert(0, theme.title)
            if match:
                queries += list(match.recipe.search_terms[:2])
            return dedupe(q for q in queries if q.strip())[:4] or ["collective behavior agent-based model"]
        try:
            data = self.ask(system=SYSTEM, schema=QUERY_SCHEMA, effort="low", prompt=(
                f"Research theme from the Director (may be Japanese): {theme.title}\n"
                f"Keywords: {', '.join(theme.keywords) or '(none)'}\nNotes: {theme.notes or '(none)'}\n\n"
                "Write 3-4 short English queries for arXiv/OpenAlex that cover the theme from complementary angles "
                "(core phenomenon, computational models, empirical/human studies)."))
            queries = [q.strip() for q in data.get("queries", []) if q.strip()]
        except LLMError as exc:
            self.note(f"query generation failed ({exc}); falling back to keywords")
            queries = []
        if match and not queries:
            queries = list(match.recipe.search_terms[:3])
        return dedupe(base + queries)[:5] or ["collective behavior model"]

    # ------------------------------------------------------------------ problems
    def _offline_problems(self, report: ScoutReport, match: RecipeMatch | None) -> None:
        problems = []
        for sentence, key in mine_gap_sentences([i for i in report.literature if not i.foundational], limit=3):
            problems.append(ResearchProblem(id="", statement=sentence, motivation="Stated as open in the literature.",
                                            evidence=[key], kind="gap"))
        if match:
            for text in match.recipe.open_problems:
                problems.append(ResearchProblem(id="", statement=text, motivation=match.recipe.summary,
                                                evidence=[r.key for r in match.recipe.references[:2]], kind="open_question"))
        for i, p in enumerate(problems, 1):
            p.id = f"P{i}"
        report.problems = problems[:6]
        retrieved = len([i for i in report.literature if not i.foundational])
        model = match.recipe.title if match else "the theme"
        report.summary = (f"Offline scouting: {retrieved} retrieved paper(s) plus the foundational literature of "
                          f"{model}. Gaps were extracted heuristically from abstract sentences that state open questions.")

    def _llm_problems(self, report: ScoutReport) -> None:
        docs = documents_block([(it.key, f"{it.title} ({it.year}). {it.venue}\n{it.abstract[:1200]}")
                                for it in report.literature])
        data = self.ask(system=SYSTEM + " " + UNTRUSTED_NOTE, schema=PROBLEM_SCHEMA, prompt=(
            f"Theme: {self.theme.title}\nKeywords: {', '.join(self.theme.keywords) or '(none)'}\n"
            f"Director's notes: {self.theme.notes or '(none)'}\n\n{docs}\n\n"
            "Summarise the state of the art and list 3-6 concrete research gaps. Prefer gaps that can be studied "
            "with a computational model, and also flag questions that need human participants or field data. "
            "Use only document ids that appear above as evidence."))
        valid = {it.key for it in report.literature}
        report.summary = data.get("summary", "")
        report.problems = []
        for i, p in enumerate(data.get("problems", [])[:6], 1):
            report.problems.append(ResearchProblem(
                id=f"P{i}", statement=p.get("statement", ""), motivation=p.get("motivation", ""),
                evidence=[k for k in p.get("evidence", []) if k in valid], kind=p.get("kind", "gap")))

    # ------------------------------------------------------------------ outputs
    def _save(self, report: ScoutReport) -> None:
        out = self.workdir()
        write_json(out / "literature.json", report.to_dict())
        (out / "references.bib").write_text(to_bibtex(report.literature), encoding="utf-8")
        lines = [f"# Scout report — {self.theme.title}", "", f"**Queries:** {', '.join(report.queries)}", "",
                 report.summary, "", "## Research gaps", ""]
        for p in report.problems:
            ev = ", ".join(p.evidence)
            lines.append(f"- **{p.id}** ({p.kind}) {p.statement}" + (f" — _{ev}_" if ev else ""))
        lines += ["", "## Literature", ""]
        for it in report.literature:
            tag = " (foundational)" if it.foundational else ""
            link = f" <{it.url}>" if it.url else ""
            lines.append(f"- `{it.key}` {it.short_authors()} ({it.year}). *{it.title}*. {it.venue}{tag}{link}")
        if report.notes:
            lines += ["", "## Notes", ""] + [f"- {n}" for n in report.notes]
        (out / "problems.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
