"""Data model shared by the agents, the orchestrator and the visualizer.

Every record is a dataclass that round-trips through JSON (``to_dict`` /
``from_dict``), so each phase of a research cycle can be persisted and resumed.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T", bound="Record")


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _from_jsonable(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        for arg in args:
            try:
                return _from_jsonable(arg, value)
            except (TypeError, ValueError, KeyError):
                continue
        return value
    if origin in (list, tuple):
        (item_tp, *_) = typing.get_args(tp) or (Any,)
        return [_from_jsonable(item_tp, v) for v in value]
    if origin is dict:
        _, val_tp = typing.get_args(tp) or (str, Any)
        return {k: _from_jsonable(val_tp, v) for k, v in value.items()}
    if isinstance(tp, type):
        if issubclass(tp, Record):
            return tp.from_dict(value)
        if issubclass(tp, enum.Enum):
            return tp(value)
        if tp is float and isinstance(value, (int, float)):
            return float(value)
        if tp in (int, str, bool) and not isinstance(value, tp):
            raise TypeError(f"expected {tp.__name__}, got {type(value).__name__}")
    return value


class Record:
    """Mixin giving dataclasses a lossless JSON round trip."""

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        if isinstance(data, cls):
            return data
        hints = typing.get_type_hints(cls)
        kwargs = {}
        for f in dataclasses.fields(cls):  # type: ignore[arg-type]
            if f.name in data:
                kwargs[f.name] = _from_jsonable(hints[f.name], data[f.name])
        return cls(**kwargs)


class Mode(str, enum.Enum):
    """Which tracks of the weekly cycle run."""

    IN_SILICO = "in-silico"  # fully autonomous: theory -> simulation -> paper -> review
    HUMAN = "human"          # only human-experiment proposals
    HYBRID = "hybrid"        # both

    @classmethod
    def parse(cls, text: str | None, default: Mode | None = None) -> Mode:
        key = (text or "").strip().lower().replace("_", "-").replace(" ", "")
        aliases = {
            "in-silico": cls.IN_SILICO, "insilico": cls.IN_SILICO, "silico": cls.IN_SILICO,
            "sim": cls.IN_SILICO, "simulation": cls.IN_SILICO, "auto": cls.IN_SILICO,
            "autonomous": cls.IN_SILICO, "完全自律": cls.IN_SILICO, "自律": cls.IN_SILICO,
            "human": cls.HUMAN, "human-proposal": cls.HUMAN, "proposal": cls.HUMAN,
            "人間": cls.HUMAN, "人間介入": cls.HUMAN, "実験提案": cls.HUMAN,
            "hybrid": cls.HYBRID, "both": cls.HYBRID, "ハイブリッド": cls.HYBRID, "両方": cls.HYBRID,
        }
        if key in aliases:
            return aliases[key]
        if default is not None and not key:
            return default
        raise ValueError(f"unknown mode {text!r} (use in-silico | human | hybrid)")

    @property
    def runs_in_silico(self) -> bool:
        return self in (Mode.IN_SILICO, Mode.HYBRID)

    @property
    def runs_human(self) -> bool:
        return self in (Mode.HUMAN, Mode.HYBRID)


class Track(str, enum.Enum):
    IN_SILICO = "in_silico"
    HUMAN = "human"


# --------------------------------------------------------------------------- theme
@dataclass
class ResearchTheme(Record):
    title: str
    keywords: list[str] = field(default_factory=list)
    mode: Mode = Mode.HYBRID
    notes: str = ""
    cycle_id: str = ""
    source: str = "cli"  # cli | config | issue | dispatch
    issue_number: int | None = None
    requested_by: str = ""

    def describe(self) -> str:
        parts = [self.title]
        if self.keywords:
            parts.append("keywords: " + ", ".join(self.keywords))
        if self.notes:
            parts.append("notes: " + self.notes)
        return "\n".join(parts)


# --------------------------------------------------------------------------- scout
@dataclass
class LiteratureItem(Record):
    key: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    url: str = ""
    abstract: str = ""
    source: str = ""  # arxiv | openalex | foundational
    doi: str = ""
    arxiv_id: str = ""
    citations: int | None = None
    relevance: float = 0.0
    foundational: bool = False

    def short_authors(self) -> str:
        if not self.authors:
            return "Anonymous"
        last = [a.split()[-1] if a.split() else a for a in self.authors]
        if len(last) == 1:
            return last[0]
        if len(last) == 2:
            return f"{last[0]} and {last[1]}"
        return f"{last[0]} et al."


@dataclass
class ResearchProblem(Record):
    id: str
    statement: str
    motivation: str = ""
    evidence: list[str] = field(default_factory=list)  # literature keys
    kind: str = "gap"  # gap | open_question | contradiction | extension


@dataclass
class ScoutReport(Record):
    queries: list[str] = field(default_factory=list)
    literature: list[LiteratureItem] = field(default_factory=list)
    problems: list[ResearchProblem] = field(default_factory=list)
    summary: str = ""
    sources_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def by_key(self) -> dict[str, LiteratureItem]:
        return {item.key: item for item in self.literature}


# --------------------------------------------------------------------------- analyst
@dataclass
class ModelParameter(Record):
    name: str
    symbol: str
    description: str
    default: float = 0.0
    sweep: list[float] = field(default_factory=list)


@dataclass
class TheoryModel(Record):
    name: str
    summary: str
    equations: list[str] = field(default_factory=list)  # LaTeX math (no $ delimiters)
    assumptions: list[str] = field(default_factory=list)
    parameters: list[ModelParameter] = field(default_factory=list)
    observables: list[str] = field(default_factory=list)
    recipe: str = ""


@dataclass
class Hypothesis(Record):
    id: str
    statement: str
    rationale: str = ""
    track: Track = Track.IN_SILICO
    predictions: list[str] = field(default_factory=list)
    independent_variable: str = ""
    dependent_variable: str = ""
    human_cues: list[str] = field(default_factory=list)
    routing_reason: str = ""


@dataclass
class HumanExperimentIdea(Record):
    id: str
    title: str
    hypothesis_id: str
    hypothesis: str
    why_human: str
    fun_factor: str
    title_en: str = ""  # used when an English paper refers to the proposal
    design_type: str = "between"  # between | within | observational | survey
    participants: str = ""
    conditions: list[str] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    analysis_plan: str = ""
    effect_size_d: float = 0.5
    alpha: float = 0.05
    power: float = 0.8
    sample_size: int = 0
    ethics: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    duration: str = ""
    cost_estimate: str = ""
    risks: list[str] = field(default_factory=list)
    in_silico_link: str = ""


@dataclass
class SimulationPlan(Record):
    sweep_parameter: str = ""
    sweep_values: list[float] = field(default_factory=list)
    replicates: int = 5
    params: dict[str, Any] = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class AnalysisReport(Record):
    model: TheoryModel
    hypotheses: list[Hypothesis] = field(default_factory=list)
    human_ideas: list[HumanExperimentIdea] = field(default_factory=list)
    plan: SimulationPlan = field(default_factory=SimulationPlan)
    recipe: str = ""
    summary: str = ""


@dataclass
class RoutingDecision(Record):
    in_silico: list[str] = field(default_factory=list)  # hypothesis ids
    human: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    run_simulation: bool = True
    write_paper: bool = True
    write_proposals: bool = True


# --------------------------------------------------------------------------- coder
@dataclass
class FigureSpec(Record):
    id: str
    table: str
    x: str
    y: list[str]
    title: str = ""
    xlabel: str = ""
    ylabel: str = ""
    caption: str = ""
    labels: list[str] = field(default_factory=list)
    lower: list[str] = field(default_factory=list)  # CI lower-bound columns (optional)
    upper: list[str] = field(default_factory=list)  # CI upper-bound columns (optional)
    logx: bool = False
    logy: bool = False


@dataclass
class SimulationResult(Record):
    status: str = "skipped"  # success | failed | skipped
    source: str = ""  # llm | recipe | recipe-fallback
    attempts: int = 0
    runtime_sec: float = 0.0
    script: str = ""
    seed: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    metric_notes: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[str]] = field(default_factory=dict)  # table name -> columns
    figures: list[FigureSpec] = field(default_factory=list)
    summary: str = ""
    findings: list[str] = field(default_factory=list)
    log_tail: str = ""
    error: str = ""
    isolation: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"


# --------------------------------------------------------------------------- writer
PAPER_SECTIONS = (
    "introduction", "related_work", "model", "methods", "results", "discussion",
    "limitations", "conclusion",
)


@dataclass
class PaperDraft(Record):
    title: str
    abstract: str
    keywords: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    figure_captions: dict[str, str] = field(default_factory=dict)
    language: str = "en"
    revision: int = 0
    response_to_reviewers: str = ""
    tex_path: str = ""
    pdf_path: str = ""
    build_ok: bool = False
    build_engine: str = ""
    build_log: str = ""


@dataclass
class ProposalDoc(Record):
    idea_id: str
    title: str
    path: str
    sample_size: int = 0


# --------------------------------------------------------------------------- reviewer
REVIEW_CRITERIA = ("novelty", "rigor", "clarity", "reproducibility", "significance")
DECISIONS = ("accept", "minor_revision", "major_revision", "reject")


@dataclass
class Review(Record):
    reviewer: str
    persona: str
    target: str = "paper"
    scores: dict[str, float] = field(default_factory=dict)
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    requests: list[str] = field(default_factory=list)
    decision: str = "minor_revision"
    confidence: int = 3
    round: int = 1

    @property
    def mean_score(self) -> float:
        vals = [float(v) for v in self.scores.values()]
        return sum(vals) / len(vals) if vals else 0.0


@dataclass
class AutomatedCheck(Record):
    id: str
    label: str
    passed: bool
    detail: str = ""
    severity: str = "minor"  # minor | major


@dataclass
class MetaReview(Record):
    decision: str
    mean_score: float
    summary: str
    required_changes: list[str] = field(default_factory=list)
    checks: list[AutomatedCheck] = field(default_factory=list)
    round: int = 1


# --------------------------------------------------------------------------- cycle
@dataclass
class CycleRecord(Record):
    cycle_id: str
    theme: ResearchTheme
    status: str = "running"  # running | done | error
    started_at: str = ""
    finished_at: str = ""
    phases_done: list[str] = field(default_factory=list)
    llm_mode: str = "offline"
    model: str = ""
    recipe: str = ""
    paper_title: str = ""
    paper_pdf: str = ""
    paper_tex: str = ""
    decision: str = ""
    review_score: float = 0.0
    proposals: list[ProposalDoc] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    pr_url: str = ""
    run_url: str = ""
