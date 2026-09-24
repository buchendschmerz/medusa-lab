"""Small statistics helpers for experiment planning."""

from __future__ import annotations

import math
from statistics import NormalDist

_Z = NormalDist()


def sample_size(effect_size_d: float, *, alpha: float = 0.05, power: float = 0.8, design: str = "between") -> int:
    """Units needed for a two-sided t-test (normal approximation with Guenther's small-sample correction).

    ``between``: per group of a two-group comparison; ``within``/paired: total pairs.
    ``survey``/``observational`` are treated like ``between``.
    For d = 0.5 this gives 64 per group (between) and 34 pairs (within), matching G*Power.
    """
    if effect_size_d <= 0:
        raise ValueError("effect size must be positive")
    z_a = _Z.inv_cdf(1 - alpha / 2)
    z_b = _Z.inv_cdf(power)
    if design == "within":
        n = ((z_a + z_b) / effect_size_d) ** 2 + z_a ** 2 / 2
    else:
        n = 2 * ((z_a + z_b) / effect_size_d) ** 2 + z_a ** 2 / 4
    return max(2, math.ceil(n))


def total_participants(n_units: int, *, design: str, conditions: int, unit_size: int = 1) -> int:
    groups = 1 if design == "within" else max(1, conditions)
    return n_units * groups * max(1, unit_size)
