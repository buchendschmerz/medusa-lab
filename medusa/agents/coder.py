"""💻 Coder — writes, runs and debugs the simulation in the sandbox.

LLM mode: the Coder writes a standalone script against the ``medusa_sim`` helper
API, statically screens it, runs it in the sandbox and feeds any screening error,
crash or invalid output back to the model (up to ``coder.max_attempts``). If it
still fails, the vetted recipe for the theme is run instead so the cycle can
continue — and the paper says so.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path
from typing import Any

from ..llm import LLMError, obj, s
from ..models import AnalysisReport, FigureSpec, SimulationResult
from ..recipes import Recipe
from ..sandbox import ALLOWED_IMPORTS, Sandbox, screen_code
from ..state import AgentState
from ..utils import read_json, write_json
from .base import Agent

RUNTIME_PATH = Path(__file__).resolve().parent.parent / "runtime" / "medusa_sim.py"
PROGRESS_RE = re.compile(r"^\[medusa-progress\]\s+([0-9.]+)\s*(.*)$")

SYSTEM = ("You are Coder, the computational scientist of Medusa Lab. You write correct, efficient, well-commented, "
          "self-contained Python simulations of formal models and report results with appropriate statistics "
          "(replicates, means, 95% confidence intervals, fitted exponents). Your code runs in a locked-down "
          "sandbox: no files, network, subprocesses or dynamic code execution.")

CODE_SCHEMA = obj({"code": s("the complete Python script"), "explanation": s("2-4 sentences on the design")})

API_DOC = """medusa_sim helper API (import medusa_sim as sim):
  sim.param(name, default)            -> value from params.json (sweep values, replicates, seed ...)
  sim.seed(value=None)                -> seeds random (and numpy); call once at start
  sim.progress(fraction, message="")  -> report progress 0..1 (shown live on the dashboard)
  sim.mean_ci(values)                 -> (mean, lower95, upper95) t-interval
  sim.linear_fit(xs, ys)              -> (intercept, slope, r2);  sim.loglog_fit(xs, ys) -> (C, exponent, r2)
  sim.save_table(name, columns, rows) -> writes data/<name>.dat (column names: letters/digits/underscore)
  sim.metric(name, value, description)-> a scalar result (numbers or short strings)
  sim.finding(text)                   -> one evidence-backed sentence stating a result (with numbers)
  sim.figure(fig_id, table, x, y, xlabel=, ylabel=, caption=, labels=, lower=, upper=, logx=, logy=)
                                      -> a line chart of saved columns: ONE y-axis, <= 3 series,
                                         optional 95% CI columns in lower/upper (same order as y)
  sim.finish(summary)                 -> MUST be called exactly once at the end (writes results.json)"""


def _available_modules() -> list[str]:
    return sorted(m for m in ALLOWED_IMPORTS if m == "medusa_sim" or importlib.util.find_spec(m) is not None)


class CoderAgent(Agent):
    key = "coder"

    def __init__(self, ctx) -> None:  # type: ignore[no-untyped-def]
        super().__init__(ctx)
        cc = self.cfg.coder
        self.sandbox = Sandbox(mode=cc.sandbox, timeout_sec=cc.timeout_sec, memory_mb=cc.memory_mb)
        self._attempt = 1

    def run(self, analysis: AnalysisReport, recipe: Recipe) -> SimulationResult:
        out = self.workdir()
        result: SimulationResult | None = None
        if not self.llm.offline:
            try:
                result = self._run_llm(analysis, out)
            except LLMError as exc:
                self.note(f"LLM code generation failed ({exc}).")
            if result is None or not result.ok:
                self.note(f"Falling back to the vetted '{recipe.id}' recipe simulation.")
                self.status(AgentState.DEBUGGING, self.msg("自作コードを断念し、検証済みレシピに切替",
                                                           "Switching to the vetted recipe"))
        if result is None or not result.ok:
            result = self._run_recipe(recipe, out, source="recipe" if self.llm.offline else "recipe-fallback")
        if result.ok:
            self.status(AgentState.DONE, self.msg(f"計算完了：図{len(result.figures)}枚・指標{len(result.metrics)}個",
                                                  f"Done: {len(result.figures)} figures, {len(result.metrics)} metrics"), 1.0)
        else:
            self.status(AgentState.ERROR, self.msg("シミュレーションに失敗しました", "Simulation failed"))
        write_json(out / "simulation.json", result.to_dict())
        return result

    # ------------------------------------------------------------------ recipe
    def _run_recipe(self, recipe: Recipe, out: Path, *, source: str) -> SimulationResult:
        self.status(AgentState.CODING, self.msg(f"レシピ「{recipe.title_ja}」を準備中", f"Preparing {recipe.title}"), 0.05)
        params = {"seed": 20260901, **recipe.run_params(self.cfg.coder.quick)}
        return self._execute(recipe.script_source(), params, out, source=source, attempts=1)

    # ------------------------------------------------------------------ LLM
    def _run_llm(self, analysis: AnalysisReport, out: Path) -> SimulationResult | None:
        cc = self.cfg.coder
        plan = analysis.plan
        params: dict[str, Any] = {"seed": 20260901, "sweep_parameter": plan.sweep_parameter,
                                  "sweep_values": plan.sweep_values, "replicates": plan.replicates,
                                  "quick": cc.quick, **plan.params}
        model = analysis.model
        hyps = "\n".join(f"- {h.id}: {h.statement} (predictions: {'; '.join(h.predictions)})"
                         for h in analysis.hypotheses if h.track.value == "in_silico")
        base_prompt = (
            f"Theme: {self.theme.title}\nModel: {model.name}\n{model.summary}\n"
            f"Equations: {'; '.join(model.equations)}\nAssumptions: {'; '.join(model.assumptions)}\n"
            "Parameters: " + "; ".join(f"{p.name} ({p.symbol}) default {p.default} sweep {p.sweep}: {p.description}"
                                       for p in model.parameters) +
            f"\nObservables: {'; '.join(model.observables)}\nHypotheses to test:\n{hyps}\n"
            f"Simulation plan: sweep {plan.sweep_parameter} over {plan.sweep_values} with {plan.replicates} "
            f"replicates; metrics: {', '.join(plan.metrics)}. {plan.notes}\n\n"
            f"params.json will contain: {json.dumps(params)}\n\n{API_DOC}\n\n"
            f"Allowed imports: {', '.join(_available_modules())}. Nothing else may be imported. Do not use open(), "
            "eval/exec, getattr/setattr, dunder attributes or any file/network/process functions.\n"
            f"The script must finish within {int(cc.timeout_sec * 0.6)} seconds on one CPU core (budget the sweep "
            "accordingly), call sim.seed() first, report progress with sim.progress(), save at least one table, "
            "declare 1-3 figures (one y-axis each), record the key metrics and findings with numbers, and end with "
            "sim.finish(summary).")
        attempts_log: list[dict[str, Any]] = []
        self.status(AgentState.CODING, self.msg("シミュレーションコードを執筆中", "Writing the simulation code"), 0.05)
        code = self.ask(system=SYSTEM, schema=CODE_SCHEMA, prompt=base_prompt)["code"]
        for attempt in range(1, cc.max_attempts + 1):
            self._attempt = attempt
            problems = screen_code(code)
            if problems:
                feedback = "Static screening rejected the script:\n" + "\n".join(f"- {p}" for p in problems)
                attempts_log.append({"attempt": attempt, "stage": "screen", "problems": problems})
            else:
                result = self._execute(code, params, out, source="llm", attempts=attempt)
                attempts_log.append({"attempt": attempt, "stage": "run", "status": result.status,
                                     "error": result.error[-2000:]})
                if result.ok:
                    write_json(out / "attempts.json", attempts_log)
                    return result
                feedback = f"The script failed:\n{result.error[-3000:]}"
            if attempt == cc.max_attempts:
                break
            self.status(AgentState.DEBUGGING, self.msg(f"デバッグ中（試行{attempt + 1}/{cc.max_attempts}）",
                                                       f"Debugging (attempt {attempt + 1}/{cc.max_attempts})"))
            code = self.ask(system=SYSTEM, schema=CODE_SCHEMA, prompt=(
                f"{base_prompt}\n\nYour previous script:\n```python\n{code}\n```\n\n{feedback}\n\n"
                "Return a corrected complete script."))["code"]
        write_json(out / "attempts.json", attempts_log)
        return None

    # ------------------------------------------------------------------ execution
    def _on_line(self, line: str) -> None:
        m = PROGRESS_RE.match(line.strip())
        if m:
            try:
                frac = float(m.group(1))
            except ValueError:
                return
            label = m.group(2) or ""
            self.status(AgentState.RUNNING, self.msg(f"計算実行中 {label}".strip(), f"Running {label}".strip()), frac)

    def _execute(self, code: str, params: dict[str, Any], out: Path, *, source: str, attempts: int) -> SimulationResult:
        for stale in ("results.json", "run_log.txt"):
            (out / stale).unlink(missing_ok=True)
        shutil.rmtree(out / "data", ignore_errors=True)
        (out / "sim.py").write_text(code, encoding="utf-8")
        write_json(out / "params.json", params)
        self.status(AgentState.RUNNING, self.msg("サンドボックスで計算実行中", "Running in the sandbox"), 0.0)
        files = {"sim.py": code, "medusa_sim.py": RUNTIME_PATH.read_text(encoding="utf-8"),
                 "params.json": json.dumps(params)}
        run = self.sandbox.execute(files, "sim.py", out, on_line=self._on_line)
        (out / "run_log.txt").write_text(run.tail(200) + "\n", encoding="utf-8")
        result = SimulationResult(status="failed", source=source, attempts=attempts, runtime_sec=run.runtime_sec,
                                  script="coder/sim.py", seed=int(params.get("seed", 0)), params=params,
                                  log_tail=run.tail(30), isolation=run.isolation)
        for note in run.notes:
            self.note(note)
        if run.timed_out:
            result.error = f"Timed out after {self.cfg.coder.timeout_sec:.0f}s.\n{run.tail(20)}"
            return result
        if not run.ok:
            result.error = f"Exit code {run.returncode}.\n{run.tail(40)}"
            return result
        data = read_json(out / "results.json")
        if not isinstance(data, dict):
            result.error = "The script did not call sim.finish(), so results.json is missing."
            return result
        problems = self._validate(data, out)
        if problems:
            result.error = "Invalid results: " + "; ".join(problems)
            return result
        result.status = "success"
        result.metrics = data.get("metrics", {})
        result.metric_notes = {str(k): str(v) for k, v in (data.get("metric_notes") or {}).items()}
        result.tables = data.get("tables", {})
        result.figures = [FigureSpec.from_dict(f) for f in data.get("figures", [])]
        result.summary = str(data.get("summary", ""))
        result.findings = [str(f) for f in data.get("findings", [])]
        result.seed = int(data.get("seed") or result.seed)
        return result

    @staticmethod
    def _validate(data: dict[str, Any], out: Path) -> list[str]:
        problems = []
        tables = data.get("tables") or {}
        if not tables:
            problems.append("no table saved (use sim.save_table)")
        for name in tables:
            if not (out / "data" / f"{name}.dat").is_file():
                problems.append(f"table file data/{name}.dat missing")
        if not data.get("figures"):
            problems.append("no figure declared (use sim.figure)")
        if not data.get("metrics"):
            problems.append("no metric recorded (use sim.metric)")
        return problems
