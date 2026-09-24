"""🧠 Analyst — theory building, hypotheses, and human-experiment design.

For every theme the Analyst produces (1) a formal model with testable in-silico
hypotheses for the fully autonomous track and (2) interesting hypotheses that
need human hands (participants, surveys, manual data collection), each with an
experiment design, power analysis and ethics checklist for the Director.
"""

from __future__ import annotations

from ..llm import LLMError, arr, enum, integer, num, obj, s
from ..models import (
    AnalysisReport,
    HumanExperimentIdea,
    Hypothesis,
    Mode,
    ModelParameter,
    ScoutReport,
    SimulationPlan,
    TheoryModel,
    Track,
)
from ..recipes import HumanIdeaTemplate, Recipe, RecipeMatch
from ..recipes.catalog import INTUITION_IDEA
from ..routing import needs_humans
from ..state import AgentState
from ..stats import sample_size
from ..utils import write_json
from .base import UNTRUSTED_NOTE, Agent, documents_block

SYSTEM = ("You are Analyst, the theorist of Medusa Lab, an autonomous multi-agent research lab. You build simple, "
          "formal, simulable models of social and cognitive phenomena, derive falsifiable hypotheses, and design "
          "rigorous human experiments for questions that simulation alone cannot answer. You are honest about "
          "assumptions and prefer parsimonious models with few parameters.")

ANALYSIS_SCHEMA = obj({
    "summary": s("3-4 sentences: the modelling approach and why it fits the theme"),
    "model": obj({
        "name": s(), "summary": s("2-4 sentences"),
        "equations": arr(s("a LaTeX math expression without $ delimiters, using only standard amsmath commands")),
        "assumptions": arr(s()),
        "parameters": arr(obj({"name": s("python identifier"), "symbol": s("LaTeX symbol"), "description": s(),
                               "default": num(), "sweep": arr(num())})),
        "observables": arr(s()),
    }),
    "hypotheses": arr(obj({
        "statement": s(), "rationale": s(), "track": enum(["in_silico", "human"]),
        "predictions": arr(s()), "independent_variable": s(), "dependent_variable": s(),
        "routing_reason": s("why this track: simulation suffices, or which human input is needed"),
    })),
    "human_ideas": arr(obj({
        "hypothesis_index": integer("0-based index into hypotheses (a human-track hypothesis)"),
        "title": s(), "title_en": s("English title"), "hypothesis": s(), "why_human": s(), "fun_factor": s(),
        "design_type": enum(["between", "within", "observational", "survey"]),
        "participants": s(), "conditions": arr(s()), "procedure": arr(s()), "measures": arr(s()),
        "analysis_plan": s(), "effect_size_d": num("expected Cohen's d (0.2-1.5)"), "ethics": arr(s()),
        "materials": arr(s()), "duration": s(), "cost_estimate": s(), "risks": arr(s()), "in_silico_link": s(),
    })),
    "simulation_plan": obj({
        "sweep_parameter": s(), "sweep_values": arr(num()), "replicates": integer(),
        "metrics": arr(s()), "notes": s(),
    }),
})


def idea_from_template(tpl: HumanIdeaTemplate, *, idea_id: str, hypothesis_id: str, lang: str,
                       fmt: dict[str, str] | None = None) -> HumanExperimentIdea:
    fmt = fmt or {}

    def t(d: dict[str, str]) -> str:
        text = d.get(lang) or d["en"]
        return text.format(**fmt) if fmt else text

    def tl(d: dict[str, list[str]]) -> list[str]:
        return [x.format(**fmt) if fmt else x for x in (d.get(lang) or d["en"])]

    return HumanExperimentIdea(
        id=idea_id, title=t(tpl.title), title_en=tpl.title["en"].format(**fmt) if fmt else tpl.title["en"],
        hypothesis_id=hypothesis_id, hypothesis=t(tpl.hypothesis), why_human=t(tpl.why_human),
        fun_factor=t(tpl.fun_factor), design_type=tpl.design_type, participants=t(tpl.participants),
        conditions=tl(tpl.conditions), procedure=tl(tpl.procedure), measures=tl(tpl.measures),
        analysis_plan=t(tpl.analysis_plan), effect_size_d=tpl.effect_size_d, ethics=tl(tpl.ethics),
        materials=tl(tpl.materials), duration=t(tpl.duration), cost_estimate=t(tpl.cost), risks=tl(tpl.risks),
        in_silico_link=t(tpl.link),
        sample_size=sample_size(tpl.effect_size_d, design=tpl.design_type),
    )


def model_from_recipe(recipe: Recipe, quick: bool = False) -> TheoryModel:
    """The recipe's model, with the sweep of the swept parameter set to the values actually run."""
    run_sweep = recipe.sweep_values(quick)
    params = []
    for p in recipe.parameters:
        sweep = run_sweep if (p.name == recipe.sweep_parameter and run_sweep) else list(p.sweep)
        params.append(ModelParameter(p.name, p.symbol, p.description, p.default, sweep))
    return TheoryModel(name=recipe.title, summary=recipe.mechanism, equations=list(recipe.equations),
                       assumptions=list(recipe.assumptions), parameters=params,
                       observables=list(recipe.observables), recipe=recipe.id)


class AnalystAgent(Agent):
    key = "analyst"

    def run(self, scout: ScoutReport, match: RecipeMatch, mode: Mode) -> AnalysisReport:
        self.status(AgentState.THINKING, self.msg("理論モデルを構築中", "Building the theory model"), 0.1)
        report: AnalysisReport | None = None
        if not self.llm.offline:
            try:
                report = self._llm(scout, match, mode)
            except LLMError as exc:
                self.note(f"LLM analysis failed ({exc}); using the recipe model '{match.recipe.id}'.")
        if report is None:
            report = self._offline(scout, match)
        self.status(AgentState.WRITING, self.msg("仮説と実験デザインを整理中", "Writing up hypotheses and designs"), 0.8)
        for hyp in report.hypotheses:
            _strong, hyp.human_cues = needs_humans(hyp)
        for idea in report.human_ideas:
            idea.sample_size = sample_size(max(0.1, idea.effect_size_d), alpha=idea.alpha, power=idea.power,
                                           design=idea.design_type)
        self._save(report)
        n_sim = sum(1 for h in report.hypotheses if h.track == Track.IN_SILICO)
        n_hum = sum(1 for h in report.hypotheses if h.track == Track.HUMAN)
        self.status(AgentState.DONE, self.msg(f"仮説{len(report.hypotheses)}件（計算{n_sim}・人間{n_hum}）を構築",
                                              f"{len(report.hypotheses)} hypotheses ({n_sim} sim, {n_hum} human)"), 1.0)
        return report

    # ------------------------------------------------------------------ offline
    def _offline(self, scout: ScoutReport, match: RecipeMatch) -> AnalysisReport:
        recipe = match.recipe
        lang = self.ctx.lang
        acfg = self.cfg.analyst
        hypotheses: list[Hypothesis] = []
        for i, tpl in enumerate(recipe.hypotheses, 1):
            hypotheses.append(Hypothesis(
                id=f"H{i}", statement=tpl.statement, rationale=tpl.rationale, track=Track.IN_SILICO,
                predictions=list(tpl.predictions), independent_variable=tpl.independent_variable,
                dependent_variable=tpl.dependent_variable,
                routing_reason="The claim concerns the model's own dynamics and is settled by simulation."))
        ideas: list[HumanExperimentIdea] = []
        templates = [*recipe.human_ideas, INTUITION_IDEA][: max(0, acfg.max_human_proposals)]
        for j, tpl in enumerate(templates, 1):
            hid = f"H{len(hypotheses) + 1}"
            fmt = None
            if tpl is INTUITION_IDEA:
                headline = recipe.headline.get(lang) or recipe.headline.get("en") or recipe.summary
                fmt = {"prediction": headline, "recipe": recipe.title_ja if lang == "ja" else recipe.title}
            idea = idea_from_template(tpl, idea_id=f"E{j}", hypothesis_id=hid, lang=lang, fmt=fmt)
            ideas.append(idea)
            hypotheses.append(Hypothesis(
                id=hid, statement=idea.hypothesis, rationale=idea.why_human, track=Track.HUMAN,
                predictions=list(idea.measures[:1]), independent_variable=", ".join(idea.conditions[:2]),
                dependent_variable=idea.measures[0] if idea.measures else "",
                routing_reason="Needs human participants: " + idea.why_human))
        hypotheses = hypotheses[: max(acfg.max_hypotheses, len(recipe.hypotheses) + len(ideas))]
        quick = self.cfg.coder.quick
        run_params = recipe.run_params(quick)
        plan = SimulationPlan(sweep_parameter=recipe.sweep_parameter, sweep_values=recipe.sweep_values(quick),
                              replicates=int(run_params.get("replicates", 3)), params=run_params,
                              metrics=list(recipe.observables), notes=f"Recipe '{recipe.id}' ({recipe.script}).")
        framing = ("No model in the offline catalogue matched the theme, so the generic contagion model is used as a "
                   "stand-in; enable LLM mode for a tailored model." if match.is_default else
                   f"The theme maps onto the {recipe.title} (matched terms: {', '.join(match.matched_terms)}).")
        if match.is_default:
            self.note("No recipe matched the theme; used the default contagion model.")
        return AnalysisReport(model=model_from_recipe(recipe, quick), hypotheses=hypotheses, human_ideas=ideas, plan=plan,
                              recipe=recipe.id, summary=f"{framing} {recipe.summary}")

    # ------------------------------------------------------------------ LLM
    def _llm(self, scout: ScoutReport, match: RecipeMatch, mode: Mode) -> AnalysisReport:
        acfg = self.cfg.analyst
        lang_name = "Japanese" if self.ctx.lang == "ja" else "English"
        recipe = match.recipe
        problems = "\n".join(f"- {p.id} ({p.kind}): {p.statement} [evidence: {', '.join(p.evidence)}]"
                             for p in scout.problems) or "- (none)"
        docs = documents_block([(it.key, f"{it.title} ({it.year}): {it.abstract[:600]}")
                                for it in scout.literature[:12]])
        prompt = (
            f"Weekly theme from the Director: {self.theme.title}\nKeywords: {', '.join(self.theme.keywords) or '-'}\n"
            f"Director's notes: {self.theme.notes or '-'}\nMode this week: {mode.value} "
            "(in-silico = autonomous simulation paper; human = experiment proposals only; hybrid = both)\n\n"
            f"Scout summary: {scout.summary}\nResearch gaps:\n{problems}\n\n{docs}\n\n"
            "Reference model you MAY adapt if it fits (you can also design a different one): "
            f"{recipe.title} — {recipe.mechanism} Equations: {'; '.join(recipe.equations)}\n\n"
            "Tasks:\n"
            "1. Specify ONE formal model that can be simulated in plain Python/numpy within a few minutes.\n"
            f"2. Give up to {acfg.max_hypotheses} hypotheses. Mark a hypothesis 'in_silico' only if the simulation "
            "can settle it; mark it 'human' if it needs participants, surveys, interviews, field observation or "
            "manual data collection.\n"
            f"3. For up to {acfg.max_human_proposals} of the 'human' hypotheses, design an experiment a small lab "
            "could run: design type, conditions, procedure, measures, pre-registrable analysis plan, a realistic "
            "effect size, ethics, materials, duration, cost, risks, and how the simulation informs it. Make them fun "
            f"and genuinely interesting. Write ALL human_ideas text fields in {lang_name}, except title_en.\n"
            "4. A simulation plan: which parameter to sweep, its values (5-12), and the number of replicates (>=3).\n"
            "Equations must be LaTeX math without $ delimiters. Everything except human_ideas must be in English.")
        data = self.ask(system=SYSTEM + " " + UNTRUSTED_NOTE, prompt=prompt, schema=ANALYSIS_SCHEMA)
        m = data["model"]
        model = TheoryModel(
            name=m.get("name", ""), summary=m.get("summary", ""), equations=list(m.get("equations", []))[:6],
            assumptions=list(m.get("assumptions", []))[:8],
            parameters=[ModelParameter(p.get("name", "x"), p.get("symbol", "x"), p.get("description", ""),
                                       float(p.get("default", 0.0)), [float(v) for v in p.get("sweep", [])][:12])
                        for p in m.get("parameters", [])[:10]],
            observables=list(m.get("observables", []))[:6])
        hypotheses = []
        for i, h in enumerate(data.get("hypotheses", [])[: acfg.max_hypotheses + acfg.max_human_proposals], 1):
            hypotheses.append(Hypothesis(
                id=f"H{i}", statement=h.get("statement", ""), rationale=h.get("rationale", ""),
                track=Track(h.get("track", "in_silico")), predictions=list(h.get("predictions", [])),
                independent_variable=h.get("independent_variable", ""),
                dependent_variable=h.get("dependent_variable", ""), routing_reason=h.get("routing_reason", "")))
        ideas = []
        for j, idea in enumerate(data.get("human_ideas", [])[: acfg.max_human_proposals], 1):
            idx = int(idea.get("hypothesis_index", -1))
            hid = hypotheses[idx].id if 0 <= idx < len(hypotheses) else ""
            if hid:
                hypotheses[idx].track = Track.HUMAN
            ideas.append(HumanExperimentIdea(
                id=f"E{j}", title=idea.get("title", ""), title_en=idea.get("title_en", ""), hypothesis_id=hid,
                hypothesis=idea.get("hypothesis", ""), why_human=idea.get("why_human", ""),
                fun_factor=idea.get("fun_factor", ""), design_type=idea.get("design_type", "between"),
                participants=idea.get("participants", ""), conditions=list(idea.get("conditions", [])),
                procedure=list(idea.get("procedure", [])), measures=list(idea.get("measures", [])),
                analysis_plan=idea.get("analysis_plan", ""),
                effect_size_d=min(2.0, max(0.1, float(idea.get("effect_size_d", 0.5)))),
                ethics=list(idea.get("ethics", [])), materials=list(idea.get("materials", [])),
                duration=idea.get("duration", ""), cost_estimate=idea.get("cost_estimate", ""),
                risks=list(idea.get("risks", [])), in_silico_link=idea.get("in_silico_link", "")))
        sp = data.get("simulation_plan", {})
        plan = SimulationPlan(sweep_parameter=sp.get("sweep_parameter", ""),
                              sweep_values=[float(v) for v in sp.get("sweep_values", [])][:12],
                              replicates=max(3, min(20, int(sp.get("replicates", 5)))),
                              metrics=list(sp.get("metrics", [])), notes=sp.get("notes", ""))
        return AnalysisReport(model=model, hypotheses=hypotheses, human_ideas=ideas, plan=plan, recipe=recipe.id,
                              summary=data.get("summary", ""))

    # ------------------------------------------------------------------ outputs
    def _save(self, report: AnalysisReport) -> None:
        out = self.workdir()
        write_json(out / "analysis.json", report.to_dict())
        m = report.model
        lines = [f"# Analyst report — {self.theme.title}", "", report.summary, "", f"## Model: {m.name}", "",
                 m.summary, "", "### Equations", ""]
        lines += [f"$$ {eq} $$" for eq in m.equations]
        lines += ["", "### Assumptions", ""] + [f"- {a}" for a in m.assumptions]
        lines += ["", "### Parameters", "", "| name | symbol | description | default | sweep |", "|---|---|---|---|---|"]
        lines += [f"| {p.name} | ${p.symbol}$ | {p.description} | {p.default:g} | {', '.join(f'{v:g}' for v in p.sweep)} |"
                  for p in m.parameters]
        lines += ["", "## Hypotheses", ""]
        for h in report.hypotheses:
            cues = f" — human cues: {', '.join(h.human_cues)}" if h.human_cues else ""
            lines.append(f"- **{h.id}** [{h.track.value}] {h.statement}{cues}")
        if report.human_ideas:
            lines += ["", "## Human experiment ideas", ""]
            lines += [f"- **{i.id}** {i.title} (n = {i.sample_size} per condition, d = {i.effect_size_d})"
                      for i in report.human_ideas]
        (out / "model.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
