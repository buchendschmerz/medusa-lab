"""medusa_sim — helper API for simulation scripts run inside the Medusa Lab sandbox.

This file is copied next to the simulation script. Scripts import it as::

    import medusa_sim as sim

    n = sim.param("population", 100)
    sim.seed(sim.param("seed", 42))
    ...
    sim.save_table("sweep", ["n", "t_mean", "t_lo", "t_hi"], rows)
    sim.metric("scaling_exponent", 1.48, "fitted exponent of t_conv ~ N^alpha")
    sim.figure("fig_sweep", table="sweep", x="n", y=["t_mean"], lower=["t_lo"], upper=["t_hi"],
               xlabel="Population N", ylabel="Convergence time", logx=True, logy=True,
               caption="Convergence time grows super-linearly with N.")
    sim.finish(summary="Convergence time scales as N^1.5 (95% CI ...)")

Everything is written to the working directory: ``results.json`` and ``data/*.dat``.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import statistics
import sys
import time

__all__ = ["params", "param", "seed", "log", "progress", "mean_ci", "save_table", "metric", "finding",
           "figure", "finish", "linear_fit", "loglog_fit"]

_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,40}$")
_COL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
_START = time.time()
_RESULTS: dict = {"metrics": {}, "metric_notes": {}, "tables": {}, "figures": [], "findings": [],
                  "summary": "", "seed": None}


def _load_params() -> dict:
    try:
        with open("params.json", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


_PARAMS = _load_params()


def params() -> dict:
    """All parameters passed by the Coder agent (a copy)."""
    return dict(_PARAMS)


def param(name: str, default=None):
    return _PARAMS.get(name, default)


def seed(value: int | None = None) -> int:
    """Seed ``random`` (and numpy, if installed) and record the seed for reproducibility."""
    value = int(value if value is not None else _PARAMS.get("seed", 12345))
    random.seed(value)
    try:
        import numpy as np  # noqa: PLC0415

        np.random.seed(value % (2**32))
    except ImportError:
        pass
    _RESULTS["seed"] = value
    return value


def log(*parts) -> None:
    print(*parts, flush=True)


def progress(fraction: float, message: str = "") -> None:
    """Report progress (0..1); shown live on the lab dashboard."""
    fraction = max(0.0, min(1.0, float(fraction)))
    print(f"[medusa-progress] {fraction:.3f} {message}".rstrip(), flush=True)


_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
         10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def _t_crit(df: int) -> float:
    if df <= 0:
        return float("nan")
    if df in _T975:
        return _T975[df]
    keys = sorted(_T975)
    if df > keys[-1]:
        return 1.96
    lo = max(k for k in keys if k < df)
    hi = min(k for k in keys if k > df)
    return _T975[lo] + (_T975[hi] - _T975[lo]) * (df - lo) / (hi - lo)


def mean_ci(values, level: float = 0.95):
    """Mean and 95% t-interval: returns (mean, lower, upper)."""
    vals = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not vals:
        return float("nan"), float("nan"), float("nan")
    m = statistics.fmean(vals)
    if len(vals) < 2:
        return m, m, m
    if abs(level - 0.95) > 1e-9:
        raise ValueError("only 95% intervals are supported")
    half = _t_crit(len(vals) - 1) * statistics.stdev(vals) / math.sqrt(len(vals))
    return m, m - half, m + half


def linear_fit(xs, ys):
    """Ordinary least squares y = a + b x. Returns (a, b, r2)."""
    xs = [float(x) for x in xs]
    ys = [float(y) for y in ys]
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two points")
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    b = sxy / sxx if sxx else float("nan")
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


def loglog_fit(xs, ys):
    """Fit y = C x^alpha on log-log axes. Returns (C, alpha, r2)."""
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys, strict=True) if x > 0 and y > 0]
    a, b, r2 = linear_fit([p[0] for p in pts], [p[1] for p in pts])
    return math.exp(a), b, r2


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    value = float(value)
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.6g}"


def save_table(name: str, columns, rows) -> str:
    """Write ``data/<name>.dat`` (whitespace separated, header line) — pgfplots-ready."""
    if not _NAME_RE.match(name):
        raise ValueError(f"invalid table name {name!r}")
    columns = list(columns)
    for col in columns:
        if not _COL_RE.match(col):
            raise ValueError(f"invalid column name {col!r} (letters, digits, underscore)")
    os.makedirs("data", exist_ok=True)
    lines = [" ".join(columns)]
    for row in rows:
        row = list(row)
        if len(row) != len(columns):
            raise ValueError(f"row has {len(row)} values, expected {len(columns)}")
        lines.append(" ".join(_fmt(v) for v in row))
    path = os.path.join("data", f"{name}.dat")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    _RESULTS["tables"][name] = columns
    return path


def metric(name: str, value, description: str = "") -> None:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        value = None
    _RESULTS["metrics"][str(name)] = value
    if description:
        _RESULTS["metric_notes"][str(name)] = description


def finding(text: str) -> None:
    """A one-sentence, evidence-backed result statement (used by the Writer)."""
    _RESULTS["findings"].append(str(text))


def figure(fig_id: str, table: str, x: str, y, *, xlabel: str = "", ylabel: str = "", title: str = "",
           caption: str = "", labels=None, lower=None, upper=None, logx: bool = False, logy: bool = False) -> None:
    """Declare a line chart of columns from a saved table (one y-axis; <= 3 series recommended)."""
    ys = [y] if isinstance(y, str) else list(y)
    if table not in _RESULTS["tables"]:
        raise ValueError(f"figure {fig_id!r}: save_table({table!r}, ...) first")
    cols = _RESULTS["tables"][table]
    for col in [x, *ys, *(lower or []), *(upper or [])]:
        if col not in cols:
            raise ValueError(f"figure {fig_id!r}: column {col!r} not in table {table!r}")
    if not _NAME_RE.match(fig_id):
        raise ValueError(f"invalid figure id {fig_id!r}")
    _RESULTS["figures"].append({
        "id": fig_id, "table": table, "x": x, "y": ys, "title": title, "xlabel": xlabel, "ylabel": ylabel,
        "caption": caption, "labels": list(labels or ys), "lower": list(lower or []), "upper": list(upper or []),
        "logx": bool(logx), "logy": bool(logy),
    })


def finish(summary: str = "", **extra) -> None:
    """Write results.json. Call exactly once at the end of the script."""
    _RESULTS["summary"] = str(summary)
    _RESULTS["runtime_sec"] = round(time.time() - _START, 3)
    _RESULTS["python"] = sys.version.split()[0]
    _RESULTS["params"] = _PARAMS
    _RESULTS.update({k: v for k, v in extra.items() if k not in _RESULTS})
    tmp = "results.json.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_RESULTS, fh, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, "results.json")
    progress(1.0, "done")
