# Peer review — round 1

**Decision:** `minor_revision` — Round 1: mean score 3.37/5 across 3 reviewers (votes: minor_revision, minor_revision, major_revision). Decision: minor revision.

## Automated checks

- ✅ Simulation ran successfully — recipe, 1.7s
- ✅ At least one figure from archived data — 2 figure(s)
- ✅ Three or more replicates per setting — 5 replicates
- ✅ Uncertainty reported (confidence bands) — 95% intervals in figures
- ✅ Random seed recorded — seed 20260901
- ✅ Three or more references — 16 references
- ✅ All sections written — complete
- ✅ Limitations discussed — 72 words
- ✅ Every in-silico hypothesis discussed — all mentioned
- ⚠️ No overclaiming language — confirm that
- ✅ PDF compiled — latexmk/lualatex
- ✅ Simulation written for this study (not a fallback) — recipe

## Reviewer 1 (Methodologist) — `minor_revision` (mean 3.50)

Reviewer 1 (Methodologist) (checklist review, round 1): the study runs end to end; mean score 3.50.

| novelty | rigor | clarity | reproducibility | significance |
|---|---|---|---|---|
| 3.0 | 3.5 | 3.5 | 4.5 | 3.0 |

**Strengths**

- Systematic parameter sweep with 5 replicates per setting.
- Seeded, archived code and raw data make the figures reproducible.

**Weaknesses**

- No overclaiming language: confirm that.

**Requests**

- Report the uncertainty of fitted quantities (e.g. confidence intervals for exponents).
- Show robustness to the main modelling choices (system size, update rule).

## Reviewer 2 (Domain expert) — `minor_revision` (mean 3.40)

Reviewer 2 (Domain expert) (checklist review, round 1): the study runs end to end; mean score 3.40.

| novelty | rigor | clarity | reproducibility | significance |
|---|---|---|---|---|
| 2.5 | 3.5 | 3.5 | 4.0 | 3.5 |

**Strengths**

- The model is a well-established baseline and its known behaviour is reproduced.
- Human-experiment proposals connect the simulation to real behaviour.

**Weaknesses**

- The mapping from the weekly theme to a classic model is stylised; novelty is modest.
- No overclaiming language: confirm that.

**Requests**

- Relate the results to empirical data on the theme ('LLMはオノマトペを接地・創発できるか').
- Position the findings against the retrieved recent literature more explicitly.

## Reviewer 3 (Skeptic) — `major_revision` (mean 3.20)

Reviewer 3 (Skeptic) (checklist review, round 1): the study runs end to end; mean score 3.20.

| novelty | rigor | clarity | reproducibility | significance |
|---|---|---|---|---|
| 3.0 | 3.0 | 3.5 | 4.0 | 2.5 |

**Strengths**

- Limitations are stated candidly.

**Weaknesses**

- A stylised model can reproduce the macro pattern for many different micro reasons.
- No overclaiming language: confirm that.

**Requests**

- Avoid generalising from the stylised model to real-world behaviour without data.
- Discuss at least one alternative mechanism that would produce the same pattern.

## Required changes

- Report the uncertainty of fitted quantities (e.g. confidence intervals for exponents).
- Show robustness to the main modelling choices (system size, update rule).
- Relate the results to empirical data on the theme ('LLMはオノマトペを接地・創発できるか').
- Position the findings against the retrieved recent literature more explicitly.
- Avoid generalising from the stylised model to real-world behaviour without data.
- Discuss at least one alternative mechanism that would produce the same pattern.
