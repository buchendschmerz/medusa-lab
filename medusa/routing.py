"""Routing research questions to the in-silico track or to human experiments.

The Analyst proposes a track for every hypothesis; :func:`route` double-checks it
with a cue detector (a hypothesis that needs participants, surveys or manual data
collection cannot be settled by simulation alone) and applies the weekly mode.
"""

from __future__ import annotations

import re
import unicodedata

from .models import AnalysisReport, Hypothesis, Mode, RoutingDecision, Track

# (pattern, label) — English patterns are matched at word starts, Japanese as substrings.
HUMAN_CUES: tuple[tuple[str, str], ...] = (
    ("participant", "participants"), ("human subject", "human subjects"), ("subjects", "subjects"),
    ("survey", "survey"), ("questionnaire", "questionnaire"), ("interview", "interviews"),
    ("focus group", "focus groups"), ("field experiment", "field experiment"), ("field study", "field study"),
    ("fieldwork", "fieldwork"), ("ethnograph", "ethnography"), ("lab experiment", "lab experiment"),
    ("laboratory experiment", "lab experiment"), ("behavioral experiment", "behavioural experiment"),
    ("behavioural experiment", "behavioural experiment"), ("recruit", "recruitment"), ("volunteer", "volunteers"),
    ("crowdsourc", "crowdsourcing"), ("annotat", "manual annotation"), ("hand-cod", "manual coding"),
    ("manual", "manual work"), ("diary", "diary study"), ("clinical", "clinical data"), ("patient", "patients"),
    ("eye-track", "eye tracking"), ("eeg", "EEG"), ("fmri", "fMRI"), ("in-person", "in-person sessions"),
    ("informed consent", "informed consent"), ("irb", "ethics review"), ("vignette", "vignette study"),
    ("被験者", "被験者"), ("参加者", "実験参加者"), ("アンケート", "アンケート"), ("質問紙", "質問紙"),
    ("インタビュー", "インタビュー"), ("フィールド", "フィールド調査"), ("観察調査", "観察調査"), ("現地", "現地調査"),
    ("手作業", "手作業"), ("手動", "手動でのデータ収集"), ("募集", "参加者募集"), ("日誌", "日誌調査"),
    ("臨床", "臨床データ"), ("脳波", "脳波計測"), ("視線", "視線計測"), ("対面", "対面実施"),
    ("同意", "インフォームド・コンセント"), ("倫理審査", "倫理審査"), ("聞き取り", "聞き取り調査"),
)
STRONG_CUES = frozenset({"participants", "human subjects", "survey", "questionnaire", "interviews", "field experiment",
                         "field study", "lab experiment", "behavioural experiment", "被験者", "実験参加者", "アンケート",
                         "質問紙", "インタビュー", "フィールド調査", "vignette study"})


def detect_human_requirements(text: str) -> list[str]:
    """Return labels of cues suggesting that human hands/participants are required."""
    norm = unicodedata.normalize("NFKC", text or "").lower()
    found: list[str] = []
    for pattern, label in HUMAN_CUES:
        if pattern.isascii():
            hit = re.search(rf"(?<![a-z]){re.escape(pattern)}", norm) is not None
        else:
            hit = pattern in norm
        if hit and label not in found:
            found.append(label)
    return found


def needs_humans(hypothesis: Hypothesis) -> tuple[bool, list[str]]:
    cues = detect_human_requirements(" ".join([hypothesis.statement, hypothesis.rationale,
                                               hypothesis.dependent_variable, " ".join(hypothesis.predictions)]))
    return any(c in STRONG_CUES for c in cues), cues


def route(analysis: AnalysisReport, mode: Mode) -> RoutingDecision:
    decision = RoutingDecision()
    for hyp in analysis.hypotheses:
        strong, cues = needs_humans(hyp)
        hyp.human_cues = cues
        if hyp.track == Track.IN_SILICO and strong:
            hyp.track = Track.HUMAN
            hyp.routing_reason = ("Re-routed: the hypothesis needs data only humans can provide ("
                                  + ", ".join(cues) + ").")
        elif not hyp.routing_reason:
            hyp.routing_reason = ("Testable by simulation of the theory model." if hyp.track == Track.IN_SILICO
                                  else "Requires human participants or manual data collection.")
        target = decision.in_silico if hyp.track == Track.IN_SILICO else decision.human
        if (hyp.track == Track.IN_SILICO and not mode.runs_in_silico) or (hyp.track == Track.HUMAN and not mode.runs_human):
            decision.deferred.append(hyp.id)
            decision.reasons[hyp.id] = f"deferred: mode '{mode.value}' skips the {hyp.track.value} track"
        else:
            target.append(hyp.id)
            decision.reasons[hyp.id] = hyp.routing_reason
    decision.run_simulation = mode.runs_in_silico and bool(decision.in_silico)
    decision.write_paper = decision.run_simulation
    decision.write_proposals = mode.runs_human and bool(analysis.human_ideas)
    return decision
