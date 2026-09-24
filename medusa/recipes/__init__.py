"""Offline research recipes: vetted computational models with ready-made studies.

A recipe bundles a classic, well-understood model (equations, assumptions,
parameters), a runnable simulation script, testable hypotheses, human-experiment
ideas and its *foundational* references. Recipes power the deterministic
offline mode and serve as a safe fallback when LLM-written code fails.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import LiteratureItem, ModelParameter, ResearchTheme

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

Text = dict[str, str]           # {"ja": ..., "en": ...}
TextList = dict[str, list[str]]


@dataclass(frozen=True)
class HumanIdeaTemplate:
    title: Text
    hypothesis: Text
    why_human: Text
    fun_factor: Text
    design_type: str
    participants: Text
    conditions: TextList
    procedure: TextList
    measures: TextList
    analysis_plan: Text
    effect_size_d: float
    ethics: TextList
    materials: TextList
    duration: Text
    cost: Text
    risks: TextList
    link: Text  # how the in-silico predictions inform this experiment


Verdict = tuple[str, str]  # ("supported" | "partially supported" | "not supported" | "inconclusive", explanation)


@dataclass(frozen=True)
class HypothesisTemplate:
    statement: str
    rationale: str
    predictions: tuple[str, ...]
    independent_variable: str
    dependent_variable: str
    evaluate: Callable[[dict[str, Any]], Verdict] | None = None

    def verdict(self, metrics: dict[str, Any]) -> Verdict:
        if self.evaluate is None:
            return "inconclusive", "no automatic criterion"
        try:
            return self.evaluate(metrics)
        except (KeyError, TypeError, ValueError):
            return "inconclusive", "the required metrics are missing"


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    title_ja: str
    field: str
    keywords: tuple[str, ...]
    search_terms: tuple[str, ...]
    summary: str
    summary_ja: str
    background: str
    mechanism: str
    equations: tuple[str, ...]
    assumptions: tuple[str, ...]
    parameters: tuple[ModelParameter, ...]
    observables: tuple[str, ...]
    hypotheses: tuple[HypothesisTemplate, ...]
    human_ideas: tuple[HumanIdeaTemplate, ...]
    references: tuple[LiteratureItem, ...]
    open_problems: tuple[str, ...]
    discussion: tuple[str, ...]
    limitations: tuple[str, ...]
    script: str
    sweep_parameter: str
    sweep_key: str = ""  # name of the script parameter holding the sweep values
    headline: dict[str, str] = field(default_factory=dict)  # lay-language key prediction {"ja","en"}
    params: dict[str, Any] = field(default_factory=dict)
    quick_params: dict[str, Any] = field(default_factory=dict)

    @property
    def script_path(self) -> Path:
        return SCRIPTS_DIR / self.script

    def script_source(self) -> str:
        return self.script_path.read_text(encoding="utf-8")

    def run_params(self, quick: bool = False) -> dict[str, Any]:
        """Parameters for the script; sweep values default to the declared parameter sweep."""
        params = {**self.params, **(self.quick_params if quick else {})}
        if self.sweep_key and self.sweep_key not in params:
            sweep = next((p.sweep for p in self.parameters if p.name == self.sweep_parameter), [])
            if sweep:
                params[self.sweep_key] = list(sweep)
        return params

    def sweep_values(self, quick: bool = False) -> list[float]:
        return [float(v) for v in self.run_params(quick).get(self.sweep_key, [])]


@dataclass(frozen=True)
class RecipeMatch:
    recipe: Recipe
    score: float
    matched_terms: tuple[str, ...]

    @property
    def is_default(self) -> bool:
        return not self.matched_terms


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _term_hits(text: str, term: str) -> bool:
    term = _normalise(term)
    if term.isascii():
        return re.search(rf"(?<![a-z]){re.escape(term)}", text) is not None
    return term in text


def match_recipe(theme: ResearchTheme | str, *, default: str = "sir_network") -> RecipeMatch:
    """Pick the recipe whose keywords best match the theme (title + keywords + notes)."""
    from .catalog import RECIPES

    if isinstance(theme, ResearchTheme):
        text = " ".join([theme.title, " ".join(theme.keywords), theme.notes])
    else:
        text = theme
    norm = _normalise(text)
    best: RecipeMatch | None = None
    for recipe in RECIPES.values():
        hits = tuple(t for t in recipe.keywords if _term_hits(norm, t))
        score = sum(1.0 + 0.15 * len(t) for t in hits)
        if hits and (best is None or score > best.score):
            best = RecipeMatch(recipe, score, hits)
    if best is None:
        return RecipeMatch(RECIPES[default], 0.0, ())
    return best


def get_recipe(recipe_id: str) -> Recipe:
    from .catalog import RECIPES

    return RECIPES[recipe_id]


def all_recipes() -> list[Recipe]:
    from .catalog import RECIPES

    return list(RECIPES.values())
