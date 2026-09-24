"""Test doubles: a scripted LLM that returns schema-shaped JSON for every agent."""

from __future__ import annotations

from typing import Any

from medusa.llm import LLM, LLMResult, Usage

GOOD_CODE = '''
import random
import medusa_sim as sim

sim.seed(sim.param("seed", 1))
values = sim.param("sweep_values", [0.1, 0.2, 0.4])
reps = int(sim.param("replicates", 3))
rows = []
for i, p in enumerate(values):
    finals = []
    for _ in range(reps):
        x = 0.0
        for _step in range(200):
            x += p if random.random() < 0.5 else -p
        finals.append(abs(x))
    m, lo, hi = sim.mean_ci(finals)
    rows.append([p, m, lo, hi])
    sim.progress((i + 1) / len(values), f"p={p}")
sim.save_table("walk", ["step", "distance", "lo", "hi"], rows)
_, slope, r2 = sim.linear_fit([r[0] for r in rows], [r[1] for r in rows])
sim.metric("slope", round(slope, 3), "growth of distance with step size")
sim.metric("r2", round(r2, 3), "R^2 of the linear fit")
sim.figure("fig_walk", "walk", "step", ["distance"], lower=["lo"], upper=["hi"], labels=["mean distance"],
           xlabel="Step size $s$", ylabel="Mean distance", caption="Distance after 200 steps.")
sim.finding(f"Mean distance grows linearly with step size (slope {slope:.1f}, R^2 = {r2:.2f}).")
sim.finish(summary="Random-walk distance scales with step size.")
'''

BAD_CODE = "import os\nos.system('echo hi')\n"


class FakeLLM(LLM):
    """Deterministic stand-in for Claude, dispatching on the calling agent (``purpose``)."""

    offline = False

    def __init__(self, *, bad_code_first: bool = True, review_decision: str = "minor_revision",
                 review_score: float = 4.0) -> None:
        super().__init__()
        self.model = "fake-claude"
        self.calls: list[dict[str, Any]] = []
        self.bad_code_first = bad_code_first
        self.review_decision = review_decision
        self.review_score = review_score
        self._code_calls = 0

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any] | None = None, effort: str | None = None,
                 cache_prefix: str | None = None, purpose: str = "") -> LLMResult:
        self.calls.append({"purpose": purpose, "schema": schema, "prompt": prompt, "cache_prefix": cache_prefix,
                           "effort": effort})
        props = set((schema or {}).get("properties", {}))
        self.usage.setdefault(purpose, Usage()).add(Usage(calls=1, input_tokens=1000, output_tokens=500))
        data = self._respond(purpose, props, prompt)
        return LLMResult(text="", data=data, model=self.model, stop_reason="end_turn")

    def _respond(self, purpose: str, props: set[str], prompt: str) -> dict[str, Any]:
        if "queries" in props:
            return {"queries": ["random walk diffusion", "step size scaling"], "rationale": "two angles"}
        if "problems" in props:
            key = "steels1995selforganizing"
            return {"summary": "Diffusion scales with step size.", "problems": [
                {"statement": "How does step size shape displacement?", "motivation": "basic", "evidence": [key],
                 "kind": "gap"},
                {"statement": "Do people judge random walks correctly?", "motivation": "intuition", "evidence": [],
                 "kind": "open_question"}]}
        if "simulation_plan" in props:
            return {
                "summary": "A random-walk model of idea diffusion.",
                "model": {"name": "Random walk", "summary": "Agents take +-s steps.",
                          "equations": ["x_{t+1} = x_t \\pm s", "\\langle |x_T| \\rangle \\propto s \\sqrt{T}"],
                          "assumptions": ["independent steps"],
                          "parameters": [{"name": "step", "symbol": "s", "description": "step size", "default": 0.2,
                                          "sweep": [0.1, 0.2, 0.4]}],
                          "observables": ["mean distance"]},
                "hypotheses": [
                    {"statement": "Distance grows linearly with step size.", "rationale": "scaling",
                     "track": "in_silico", "predictions": ["slope > 0"], "independent_variable": "s",
                     "dependent_variable": "distance", "routing_reason": "simulation suffices"},
                    {"statement": "Survey participants underestimate random-walk spread.", "rationale": "intuition",
                     "track": "in_silico", "predictions": ["underestimation"], "independent_variable": "info",
                     "dependent_variable": "error", "routing_reason": "mislabelled on purpose"},
                ],
                "human_ideas": [{
                    "hypothesis_index": 1, "title": "ランダムウォーク直感調査", "title_en": "Random-walk intuition survey",
                    "hypothesis": "人は拡散を過小評価する", "why_human": "直感は人間でしか測れない", "fun_factor": "クイズ形式",
                    "design_type": "survey", "participants": "成人", "conditions": ["説明のみ", "説明+動画"],
                    "procedure": ["説明", "予測", "答え合わせ"], "measures": ["予測誤差"], "analysis_plan": "t検定",
                    "effect_size_d": 0.5, "ethics": ["同意取得"], "materials": ["フォーム"], "duration": "1週間",
                    "cost_estimate": "少額", "risks": ["理解不足"], "in_silico_link": "シミュレーションが正解"}],
                "simulation_plan": {"sweep_parameter": "step", "sweep_values": [0.1, 0.2, 0.4], "replicates": 3,
                                    "metrics": ["slope"], "notes": ""},
            }
        if "code" in props:
            self._code_calls += 1
            if self.bad_code_first and self._code_calls == 1:
                return {"code": BAD_CODE, "explanation": "first try"}
            return {"code": GOOD_CODE, "explanation": "random walk sweep"}
        if "response_to_reviewers" in props:
            return {"abstract": "Revised abstract.", "response_to_reviewers": "We addressed every point.",
                    **{name: f"Revised {name} text with \\citep{{steels1995selforganizing}} and H1." for name in
                       ("introduction", "related_work", "model", "methods", "results", "discussion", "limitations",
                        "conclusion")}}
        if "figure_captions" in props:
            pad = (" This paragraph is deliberately long enough to pass the automated completeness check, which "
                   "requires every section to contain at least twenty-five words of substantive prose.")
            paper = self._paper()
            return {k: (v + pad if k in ("introduction", "related_work", "model", "methods", "results",
                                        "discussion", "limitations", "conclusion") else v) for k, v in paper.items()}
        if "scores" in props:
            s = self.review_score
            return {"summary": "Solid baseline study.", "scores": {c: s for c in (
                "novelty", "rigor", "clarity", "reproducibility", "significance")},
                    "strengths": ["clear"], "weaknesses": ["simple"], "requests": ["discuss alternatives"],
                    "decision": self.review_decision, "confidence": 3}
        raise AssertionError(f"unexpected LLM call: {purpose} {sorted(props)}")

    @staticmethod
    def _paper() -> dict[str, Any]:
        return {"title": "Random walks and idea diffusion", "abstract": "We study $x_t$ with 95\\% CIs.",
                    "keywords": ["random walk", "diffusion"],
                    "introduction": "Ideas spread like walkers \\citep{steels1995selforganizing}. See Figure~\\ref{fig:fig_walk}.",
                    "related_work": "Prior work \\citet{baronchelli2006sharp} and \\cite{unknown2020}.",
                    "model": "The model follows Equation~\\ref{eq:1}; parameters are in Table~\\ref{tab:params}.",
                    "methods": "We swept $s$ with 3 replicates. \\input{/etc/passwd}",
                    "results": "H1 is supported: distance grows with $s$ (Table~\\ref{tab:metrics}).",
                    "discussion": "- linear scaling\n- intuition may fail",
                    "limitations": "Only one dimension was studied; the model ignores memory, social structure and "
                                   "heterogeneous agents, so the results are a stylised baseline at best.",
                    "conclusion": "Random walks provide a baseline.",
                    "figure_captions": [{"id": "fig:fig_walk", "caption": "Mean distance versus step size."}]}
