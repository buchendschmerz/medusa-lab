"""🖍️ Reviewer — inter-agent peer review.

Three reviewer personas (a methodologist, a domain expert and the proverbial
skeptical "Reviewer 2") score the paper on novelty, rigor, clarity,
reproducibility and significance. Automated checks (did the simulation run?
are there replicates, confidence intervals, references, limitations?) feed every
review, and a meta-review decides whether the Writer must revise.
"""

from __future__ import annotations

import re
from statistics import fmean

from ..llm import LLMError, arr, enum, integer, num, obj, s
from ..models import (
    DECISIONS,
    PAPER_SECTIONS,
    REVIEW_CRITERIA,
    AnalysisReport,
    AutomatedCheck,
    HumanExperimentIdea,
    MetaReview,
    PaperDraft,
    Review,
    ScoutReport,
    SimulationResult,
    Track,
)
from ..state import AgentState
from ..utils import write_json
from .base import Agent

PERSONAS = {
    "methodologist": {
        "name": "Reviewer 1 (Methodologist)", "ja": "方法論レビュアー",
        "focus": "statistical rigor, experimental design, uncertainty quantification and reproducibility",
    },
    "domain_expert": {
        "name": "Reviewer 2 (Domain expert)", "ja": "分野専門レビュアー",
        "focus": "novelty, positioning in the literature, and whether the model captures the phenomenon",
    },
    "skeptic": {
        "name": "Reviewer 3 (Skeptic)", "ja": "懐疑派レビュアー（通称Reviewer 2）",
        "focus": "overclaiming, alternative explanations, hidden assumptions and failure modes",
    },
}

REVIEW_SCHEMA = obj({
    "summary": s("2-4 sentences"),
    "scores": obj({c: num("1 (poor) to 5 (excellent)") for c in REVIEW_CRITERIA}),
    "strengths": arr(s()), "weaknesses": arr(s()), "requests": arr(s("a concrete, actionable change")),
    "decision": enum(list(DECISIONS)), "confidence": integer("1-5"),
})

OVERCLAIM = re.compile(r"\b(prove[sd]?|proof that|definitive(ly)?|undeniabl[ey]|conclusively|beyond doubt|"
                       r"clearly demonstrates?|confirms? that)\b", re.I)


def _clamp(x: float) -> float:
    return max(1.0, min(5.0, round(x * 2) / 2))


def _decision(mean: float, major_failures: int, threshold: float) -> str:
    if mean < 2.0:
        return "reject"
    if major_failures or mean < threshold - 0.75:
        return "major_revision"
    if mean >= 4.0:
        return "accept"
    return "minor_revision" if mean >= threshold - 0.25 else "major_revision"


def paper_text(draft: PaperDraft, sim: SimulationResult) -> str:
    parts = [f"Title: {draft.title}", f"Abstract: {draft.abstract}"]
    parts += [f"[{name}]\n{draft.sections.get(name, '')}" for name in PAPER_SECTIONS]
    parts.append("Metrics: " + "; ".join(f"{k}={v}" for k, v in sim.metrics.items()))
    parts.append("Figures: " + "; ".join(f"{f.id}: {f.caption}" for f in sim.figures))
    if draft.response_to_reviewers:
        parts.append(f"[response to reviewers]\n{draft.response_to_reviewers}")
    return "\n\n".join(parts)


class ReviewerAgent(Agent):
    key = "reviewer"

    # ------------------------------------------------------------------ checks
    def automated_checks(self, draft: PaperDraft, sim: SimulationResult, scout: ScoutReport,
                         analysis: AnalysisReport) -> list[AutomatedCheck]:
        text = " ".join([draft.abstract, *draft.sections.values()])
        checks = [
            AutomatedCheck("simulation", "Simulation ran successfully", sim.ok,
                           sim.error[:200] if not sim.ok else f"{sim.source}, {sim.runtime_sec:.1f}s", "major"),
            AutomatedCheck("figures", "At least one figure from archived data", bool(sim.figures),
                           f"{len(sim.figures)} figure(s)", "major"),
            AutomatedCheck("replicates", "Three or more replicates per setting", analysis.plan.replicates >= 3,
                           f"{analysis.plan.replicates} replicates", "major"),
            AutomatedCheck("uncertainty", "Uncertainty reported (confidence bands)",
                           any(f.lower and f.upper for f in sim.figures) or "confidence" in text.lower(),
                           "95% intervals in figures" if any(f.lower for f in sim.figures) else "no CI bands"),
            AutomatedCheck("seed", "Random seed recorded", bool(sim.seed), f"seed {sim.seed}"),
            AutomatedCheck("references", "Three or more references", len(scout.literature) >= 3,
                           f"{len(scout.literature)} references"),
            AutomatedCheck("sections", "All sections written",
                           all(len(draft.sections.get(n, "").split()) >= 25 for n in PAPER_SECTIONS),
                           ", ".join(n for n in PAPER_SECTIONS if len(draft.sections.get(n, "").split()) < 25)
                           or "complete", "major"),
            AutomatedCheck("limitations", "Limitations discussed",
                           len(draft.sections.get("limitations", "").split()) >= 30,
                           f"{len(draft.sections.get('limitations', '').split())} words"),
            AutomatedCheck("hypotheses", "Every in-silico hypothesis discussed",
                           all(h.id in text for h in analysis.hypotheses if h.track == Track.IN_SILICO),
                           ", ".join(h.id for h in analysis.hypotheses if h.track == Track.IN_SILICO and h.id not in text)
                           or "all mentioned"),
            AutomatedCheck("overclaiming", "No overclaiming language", not OVERCLAIM.search(text),
                           ", ".join(sorted({m.group(0).lower() for m in OVERCLAIM.finditer(text)})) or "none found"),
            AutomatedCheck("pdf", "PDF compiled", draft.build_ok or not self.cfg.writer.compile_pdf,
                           draft.build_engine or "not built"),
            AutomatedCheck("own_code", "Simulation written for this study (not a fallback)",
                           sim.source != "recipe-fallback", sim.source),
        ]
        return checks

    # ------------------------------------------------------------------ paper review
    def review_paper(self, draft: PaperDraft, sim: SimulationResult, scout: ScoutReport,
                     analysis: AnalysisReport, round_no: int) -> tuple[list[Review], MetaReview]:
        personas = self.cfg.reviewer.personas
        checks = self.automated_checks(draft, sim, scout, analysis)
        reviews: list[Review] = []
        shared = paper_text(draft, sim)
        for i, persona in enumerate(personas):
            info = PERSONAS[persona]
            self.status(AgentState.REVIEWING, self.msg(f"{info['ja']}が査読中（第{round_no}ラウンド）",
                                                       f"{info['name']} reviewing (round {round_no})"),
                        (i + 0.5) / len(personas))
            review = None
            if not self.llm.offline:
                try:
                    review = self._llm_review(persona, shared, checks, round_no)
                except LLMError as exc:
                    self.note(f"LLM review by {persona} failed ({exc}); using the checklist review.")
            reviews.append(review or self._offline_review(persona, checks, sim, analysis, round_no))
        meta = self._meta(reviews, checks, round_no)
        self._save(reviews, meta, round_no)
        return reviews, meta

    def _llm_review(self, persona: str, paper: str, checks: list[AutomatedCheck], round_no: int) -> Review:
        info = PERSONAS[persona]
        check_text = "\n".join(f"- [{'PASS' if c.passed else 'FAIL'}] {c.label}: {c.detail}" for c in checks)
        data = self.ask(
            system=("You are a peer reviewer for Medusa Lab's internal preprint series. Be constructive, specific "
                    "and calibrated: reward honest limitations, penalise overclaiming."),
            cache_prefix=f"<paper>\n{paper}\n</paper>",
            prompt=(f"You are {info['name']}; focus on {info['focus']}. Review round {round_no}.\n"
                    f"Automated checks:\n{check_text}\n\nScore each criterion from 1 to 5, list strengths, weaknesses "
                    "and concrete requests, and give a decision."),
            schema=REVIEW_SCHEMA, effort="medium")
        scores = {c: _clamp(float(data["scores"].get(c, 3))) for c in REVIEW_CRITERIA}
        return Review(reviewer=info["name"], persona=persona, scores=scores, summary=data.get("summary", ""),
                      strengths=list(data.get("strengths", []))[:6], weaknesses=list(data.get("weaknesses", []))[:6],
                      requests=list(data.get("requests", []))[:6], decision=data.get("decision", "minor_revision"),
                      confidence=int(data.get("confidence", 3)), round=round_no)

    def _offline_review(self, persona: str, checks: list[AutomatedCheck], sim: SimulationResult,
                        analysis: AnalysisReport, round_no: int) -> Review:
        info = PERSONAS[persona]
        failed = {c.id for c in checks if not c.passed}
        sc = {"novelty": 3.0, "rigor": 3.5, "clarity": 3.5, "reproducibility": 4.0, "significance": 3.0}
        if "simulation" in failed:
            sc["rigor"], sc["significance"] = 1.0, 1.0
        if "figures" in failed:
            sc["clarity"] -= 1
            sc["rigor"] -= 1
        if "replicates" in failed:
            sc["rigor"] -= 1
        if "uncertainty" in failed:
            sc["rigor"] -= 0.5
        if "references" in failed:
            sc["novelty"] -= 0.5
        if "sections" in failed:
            sc["clarity"] -= 1.5
        if "pdf" in failed:
            sc["clarity"] -= 0.5
        if "overclaiming" in failed:
            sc["rigor"] -= 0.5
        if "own_code" in failed:
            sc["novelty"] -= 0.5
        if "uncertainty" not in failed and "replicates" not in failed:
            sc["rigor"] += 0.5
        strengths, weaknesses, requests = [], [], []
        reps = analysis.plan.replicates
        if persona == "methodologist":
            sc["reproducibility"] += 0.5 if "seed" not in failed else -1
            strengths += [f"Systematic parameter sweep with {reps} replicates per setting.",
                          "Seeded, archived code and raw data make the figures reproducible."]
            requests += ["Report the uncertainty of fitted quantities (e.g. confidence intervals for exponents).",
                         "Show robustness to the main modelling choices (system size, update rule)."]
        elif persona == "domain_expert":
            sc["novelty"] -= 0.5 if self.llm.offline else 0
            sc["significance"] += 0.5 if analysis.human_ideas else 0
            strengths += ["The model is a well-established baseline and its known behaviour is reproduced.",
                          "Human-experiment proposals connect the simulation to real behaviour."
                          if analysis.human_ideas else "Clear link between theme and mechanism."]
            weaknesses.append("The mapping from the weekly theme to a classic model is stylised; novelty is modest.")
            requests += [f"Relate the results to empirical data on the theme ('{self.theme.title}').",
                         "Position the findings against the retrieved recent literature more explicitly."]
        else:  # skeptic
            sc["significance"] -= 0.5
            sc["rigor"] -= 0.25
            weaknesses.append("A stylised model can reproduce the macro pattern for many different micro reasons.")
            requests += ["Avoid generalising from the stylised model to real-world behaviour without data.",
                         "Discuss at least one alternative mechanism that would produce the same pattern."]
            strengths.append("Limitations are stated candidly.")
        for c in checks:
            if not c.passed:
                weaknesses.append(f"{c.label}: {c.detail}.")
        scores = {k: _clamp(v) for k, v in sc.items()}
        mean = fmean(scores.values())
        major = sum(1 for c in checks if not c.passed and c.severity == "major")
        decision = _decision(mean, major, self.cfg.reviewer.accept_threshold)
        summary = (f"{info['name']} (checklist review, round {round_no}): the study "
                   f"{'runs end to end' if sim.ok else 'lacks usable simulation results'}; mean score {mean:.2f}.")
        return Review(reviewer=info["name"], persona=persona, scores=scores, summary=summary, strengths=strengths,
                      weaknesses=weaknesses, requests=requests, decision=decision, confidence=3, round=round_no)

    def _meta(self, reviews: list[Review], checks: list[AutomatedCheck], round_no: int) -> MetaReview:
        mean = round(fmean(r.mean_score for r in reviews), 2) if reviews else 0.0
        major = [c for c in checks if not c.passed and c.severity == "major"]
        decision = _decision(mean, len(major), self.cfg.reviewer.accept_threshold)
        if any(c.id == "simulation" for c in major):
            decision = "reject"
        votes = [r.decision for r in reviews]
        if decision == "minor_revision" and votes.count("major_revision") > len(votes) / 2:
            decision = "major_revision"
        required = [f"Fix: {c.label} ({c.detail})" for c in major]
        for r in reviews:
            required += [q for q in r.requests[:2] if q not in required]
        summary = (f"Round {round_no}: mean score {mean:.2f}/5 across {len(reviews)} reviewers "
                   f"(votes: {', '.join(votes)}). Decision: {decision.replace('_', ' ')}.")
        return MetaReview(decision=decision, mean_score=mean, summary=summary, required_changes=required[:8],
                          checks=checks, round=round_no)

    def _save(self, reviews: list[Review], meta: MetaReview, round_no: int) -> None:
        out = self.workdir("review")
        write_json(out / f"round{round_no}.json", {"reviews": [r.to_dict() for r in reviews], "meta": meta.to_dict()})
        write_json(out / "latest.json", {"reviews": [r.to_dict() for r in reviews], "meta": meta.to_dict()})
        lines = [f"# Peer review — round {round_no}", "", f"**Decision:** `{meta.decision}` — {meta.summary}", "",
                 "## Automated checks", ""]
        lines += [f"- {'✅' if c.passed else ('❌' if c.severity == 'major' else '⚠️')} {c.label} — {c.detail}"
                  for c in meta.checks]
        for r in reviews:
            lines += ["", f"## {r.reviewer} — `{r.decision}` (mean {r.mean_score:.2f})", "", r.summary, "",
                      "| " + " | ".join(REVIEW_CRITERIA) + " |", "|" + "---|" * len(REVIEW_CRITERIA),
                      "| " + " | ".join(f"{r.scores.get(c, 0):.1f}" for c in REVIEW_CRITERIA) + " |"]
            for title, items in (("Strengths", r.strengths), ("Weaknesses", r.weaknesses), ("Requests", r.requests)):
                if items:
                    lines += ["", f"**{title}**", ""] + [f"- {x}" for x in items]
        if meta.required_changes:
            lines += ["", "## Required changes", ""] + [f"- {x}" for x in meta.required_changes]
        (out / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------ proposal review
    def review_proposals(self, ideas: list[HumanExperimentIdea]) -> dict[str, Review]:
        out: dict[str, Review] = {}
        for i, idea in enumerate(ideas):
            self.status(AgentState.REVIEWING, self.msg(f"実験提案書 {idea.id} を査読中", f"Reviewing proposal {idea.id}"),
                        (i + 0.5) / max(1, len(ideas)))
            review = None
            if not self.llm.offline:
                try:
                    review = self._llm_proposal_review(idea)
                except LLMError as exc:
                    self.note(f"LLM proposal review failed ({exc}); using the checklist review.")
            out[idea.id] = review or self._offline_proposal_review(idea)
        return out

    def _llm_proposal_review(self, idea: HumanExperimentIdea) -> Review:
        lang = "Japanese" if self.ctx.lang == "ja" else "English"
        data = self.ask(
            system="You review human-subject experiment proposals for feasibility, rigor and research ethics.",
            prompt=(f"Proposal:\n{idea.to_dict()}\n\nAssess design validity, power (n = {idea.sample_size} per "
                    f"condition for d = {idea.effect_size_d}), confounds, ethics and practicality for a small lab. "
                    f"Write summary, strengths, weaknesses and requests in {lang}."),
            schema=REVIEW_SCHEMA, effort="low")
        return Review(reviewer=PERSONAS["methodologist"]["name"], persona="methodologist", target=f"proposal:{idea.id}",
                      scores={c: _clamp(float(data["scores"].get(c, 3))) for c in REVIEW_CRITERIA},
                      summary=data.get("summary", ""), strengths=list(data.get("strengths", []))[:5],
                      weaknesses=list(data.get("weaknesses", []))[:5], requests=list(data.get("requests", []))[:5],
                      decision=data.get("decision", "minor_revision"), confidence=int(data.get("confidence", 3)))

    def _offline_proposal_review(self, idea: HumanExperimentIdea) -> Review:
        ja = self.ctx.lang == "ja"
        strengths, weaknesses, requests = [], [], []
        sc = {"novelty": 3.5, "rigor": 3.5, "clarity": 4.0, "reproducibility": 3.5, "significance": 3.5}
        if idea.sample_size:
            strengths.append(f"検出力分析に基づくサンプルサイズ（各条件 n={idea.sample_size}）が示されている。" if ja else
                             f"Sample size justified by a power analysis (n = {idea.sample_size} per condition).")
        if idea.ethics:
            strengths.append("倫理的配慮のチェックリストが具体的。" if ja else "Concrete ethics checklist.")
        else:
            sc["rigor"] -= 1
            weaknesses.append("倫理的配慮が未記載。" if ja else "Ethics considerations are missing.")
        if idea.in_silico_link:
            strengths.append("シミュレーション予測との接続が明確で、理論と実証の往復になっている。" if ja else
                             "Clear link to the simulation's predictions.")
        if idea.effect_size_d >= 1.0:
            weaknesses.append(f"想定効果量 d={idea.effect_size_d} は大きめ。パイロット研究で確認すべき。" if ja else
                              f"The assumed effect size d = {idea.effect_size_d} is large; verify it in a pilot.")
            requests.append("小規模なパイロットで効果量と手続きの理解度を確認する。" if ja else
                            "Run a small pilot to calibrate the effect size and instructions.")
        requests.append("主要指標・除外基準・分析を実施前に事前登録する。" if ja else
                        "Pre-register the primary outcome, exclusions and analysis before data collection.")
        if idea.design_type in ("between", "survey"):
            requests.append("条件への割り当てを完全ランダム化し、割り当て手続きを記録する。" if ja else
                            "Fully randomise condition assignment and log the procedure.")
        scores = {k: _clamp(v) for k, v in sc.items()}
        mean = fmean(scores.values())
        summary = ((f"実施可能性の高い提案です（平均 {mean:.1f}/5）。パイロットと事前登録を経て実施を推奨します。") if ja else
                   f"A feasible proposal (mean {mean:.1f}/5); recommended after a pilot and pre-registration.")
        return Review(reviewer=PERSONAS["methodologist"]["name"], persona="methodologist", target=f"proposal:{idea.id}",
                      scores=scores, summary=summary, strengths=strengths, weaknesses=weaknesses, requests=requests,
                      decision="minor_revision" if weaknesses else "accept", confidence=3)
