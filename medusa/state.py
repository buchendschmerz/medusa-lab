"""Live lab status: what every agent is doing right now.

The :class:`StatusBoard` is the single source of truth for the dashboard.
Agents report state transitions (``board.agent("coder", AgentState.CODING, ...)``);
subscribers (the pixel-art renderer, the GitHub live-status comment, the console)
are notified on every change, and the board is persisted to ``status.json`` so the
web dashboard can poll it.
"""

from __future__ import annotations

import enum
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Record
from .utils import iso_now, read_json, write_json


class AgentState(str, enum.Enum):
    SLEEPING = "sleeping"
    IDLE = "idle"
    SEARCHING = "searching"
    READING = "reading"
    THINKING = "thinking"
    CODING = "coding"
    RUNNING = "running"
    DEBUGGING = "debugging"
    WRITING = "writing"
    BUILDING = "building"
    REVIEWING = "reviewing"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class StateStyle:
    en: str
    ja: str
    emoji: str
    tone: str  # idle | active | wait | done | error


STATE_STYLES: dict[AgentState, StateStyle] = {
    AgentState.SLEEPING: StateStyle("SLEEPING", "おやすみ中", "💤", "idle"),
    AgentState.IDLE: StateStyle("IDLE", "待機中", "☕", "idle"),
    AgentState.SEARCHING: StateStyle("SEARCHING", "論文棚を探索中", "🔍", "active"),
    AgentState.READING: StateStyle("READING", "論文を読解中", "📖", "active"),
    AgentState.THINKING: StateStyle("THINKING", "思考中", "💭", "active"),
    AgentState.CODING: StateStyle("CODING", "コーディング中", "⌨️", "active"),
    AgentState.RUNNING: StateStyle("RUNNING", "計算実行中", "⚙️", "active"),
    AgentState.DEBUGGING: StateStyle("DEBUGGING", "デバッグ中", "🐛", "active"),
    AgentState.WRITING: StateStyle("WRITING", "執筆中", "✍️", "active"),
    AgentState.BUILDING: StateStyle("BUILDING", "ビルド中", "🏗️", "active"),
    AgentState.REVIEWING: StateStyle("REVIEWING", "査読中", "🖍️", "active"),
    AgentState.WAITING: StateStyle("WAITING", "所長待ち", "⏳", "wait"),
    AgentState.DONE: StateStyle("DONE", "完了", "✅", "done"),
    AgentState.ERROR: StateStyle("ERROR", "エラー", "❌", "error"),
}

TONE_EMOJI = {"idle": "⚪", "active": "🔵", "wait": "🟡", "done": "🟢", "error": "🔴"}


@dataclass(frozen=True)
class AgentProfile:
    key: str
    name: str
    emoji: str
    title_ja: str
    role_ja: str
    role_en: str
    color: str  # identity color (badges / labels)


AGENT_PROFILES: dict[str, AgentProfile] = {
    "scout": AgentProfile("scout", "Kepler", "🔍", "ケプラー", "偵察 · 論文収集と課題抽出",
                          "Scout · literature search & gap finding", "#eb6834"),
    "analyst": AgentProfile("analyst", "Hypatia", "🧠", "ヒパティア", "分析 · 理論モデル構築と仮説・実験デザイン",
                            "Analyst · theory building & experiment design", "#6a4fd6"),
    "coder": AgentProfile("coder", "Turing", "💻", "チューリング", "実装 · 数理・計算シミュレーション",
                          "Coder · computational simulation", "#1baf7a"),
    "writer": AgentProfile("writer", "Sagan", "📝", "セーガン", "執筆 · LaTeX論文と実験プロトコル",
                           "Writer · LaTeX paper & protocol writing", "#2a78d6"),
    "reviewer": AgentProfile("reviewer", "Tycho", "🖍️", "チコ", "査読 · エージェント間ピアレビュー",
                             "Reviewer · inter-agent peer review", "#d03b3b"),
}
AGENT_KEYS: tuple[str, ...] = tuple(AGENT_PROFILES)


@dataclass(frozen=True)
class StageInfo:
    key: str
    en: str
    ja: str
    emoji: str


STAGES: tuple[StageInfo, ...] = (
    StageInfo("theme", "THEME", "テーマ受付", "📮"),
    StageInfo("scout", "SCOUT", "文献調査", "🔍"),
    StageInfo("analyst", "THEORY", "理論・仮説", "🧠"),
    StageInfo("coder", "SIMULATE", "計算実験", "💻"),
    StageInfo("writer", "WRITE", "論文・提案", "📝"),
    StageInfo("review", "REVIEW", "査読", "🖍️"),
    StageInfo("publish", "PUBLISH", "公開", "🚀"),
)
STAGE_KEYS: tuple[str, ...] = tuple(s.key for s in STAGES)
STAGE_STATUSES = ("pending", "active", "done", "skipped", "error")

DIRECTOR_STATES = {
    "away": ("AWAY", "不在", "🌙"),
    "waiting": ("THEME?", "テーマ待ち", "📮"),
    "received": ("THEME OK", "テーマ受付済み", "📜"),
    "reviewing": ("YOUR TURN", "成果の確認待ち", "👀"),
}


@dataclass
class AgentStatus(Record):
    agent: str
    state: AgentState = AgentState.SLEEPING
    message: str = ""
    progress: float = 0.0
    updated_at: str = ""

    @property
    def style(self) -> StateStyle:
        return STATE_STYLES[self.state]


@dataclass
class DirectorStatus(Record):
    state: str = "away"
    message: str = ""


@dataclass
class ActivityEvent(Record):
    at: str
    agent: str
    state: str
    message: str = ""


@dataclass
class LabSnapshot(Record):
    lab_name: str = "Medusa Lab"
    cycle_id: str = ""
    theme: str = ""
    mode: str = "hybrid"
    cycle_status: str = "idle"  # idle | waiting | running | done | error
    stage: str = ""
    stages: dict[str, str] = field(default_factory=lambda: {k: "pending" for k in STAGE_KEYS})
    agents: dict[str, AgentStatus] = field(
        default_factory=lambda: {k: AgentStatus(agent=k) for k in AGENT_KEYS})
    director: DirectorStatus = field(default_factory=DirectorStatus)
    counters: dict[str, Any] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    events: list[ActivityEvent] = field(default_factory=list)
    updated_at: str = ""

    def stage_index(self) -> int:
        return STAGE_KEYS.index(self.stage) if self.stage in STAGE_KEYS else -1

    def progress(self) -> float:
        """Fraction of the pipeline finished (done or skipped stages)."""
        finished = sum(1 for k in STAGE_KEYS if self.stages.get(k) in ("done", "skipped"))
        return finished / len(STAGE_KEYS)


Listener = Callable[[LabSnapshot, str], None]
MAX_EVENTS = 40


class StatusBoard:
    """Mutable, observable lab status persisted to ``status.json``."""

    def __init__(self, path: Path | None = None, *, lab_name: str = "Medusa Lab",
                 snapshot: LabSnapshot | None = None, autosave: bool = True) -> None:
        self.path = Path(path) if path else None
        self._snap = snapshot or LabSnapshot(lab_name=lab_name)
        self._snap.lab_name = lab_name or self._snap.lab_name
        self._listeners: list[Listener] = []
        self._lock = threading.RLock()
        self.autosave = autosave

    # ----------------------------------------------------------------- plumbing
    @classmethod
    def load(cls, path: Path, *, lab_name: str = "Medusa Lab", autosave: bool = True) -> StatusBoard:
        data = read_json(path)
        snap = None
        if isinstance(data, dict):
            try:
                snap = LabSnapshot.from_dict(data)
            except (TypeError, ValueError, KeyError):
                snap = None
        board = cls(path, lab_name=lab_name, snapshot=snap, autosave=autosave)
        board._ensure_agents()
        return board

    def _ensure_agents(self) -> None:
        for key in AGENT_KEYS:
            self._snap.agents.setdefault(key, AgentStatus(agent=key))
        for key in STAGE_KEYS:
            self._snap.stages.setdefault(key, "pending")

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    @property
    def snapshot(self) -> LabSnapshot:
        return self._snap

    def save(self) -> None:
        if self.path:
            write_json(self.path, self._snap.to_dict())

    def _changed(self, kind: str) -> None:
        self._snap.updated_at = iso_now()
        if self.autosave:
            self.save()
        for listener in list(self._listeners):
            listener(self._snap, kind)

    def _event(self, agent: str, state: str, message: str) -> None:
        self._snap.events.append(ActivityEvent(at=iso_now(), agent=agent, state=state, message=message))
        del self._snap.events[:-MAX_EVENTS]

    # ----------------------------------------------------------------- updates
    def agent(self, key: str, state: AgentState, message: str | None = None,
              progress: float | None = None) -> None:
        if key not in AGENT_PROFILES:
            raise KeyError(f"unknown agent {key!r}")
        with self._lock:
            status = self._snap.agents.setdefault(key, AgentStatus(agent=key))
            changed_state = status.state != state
            status.state = AgentState(state)
            if message is not None:
                status.message = message
            if progress is not None:
                status.progress = max(0.0, min(1.0, float(progress)))
            elif changed_state and state == AgentState.DONE:
                status.progress = 1.0
            status.updated_at = iso_now()
            if changed_state or message:
                self._event(key, status.state.value, status.message)
            self._changed("agent")

    def stage(self, key: str, status: str) -> None:
        if key not in STAGE_KEYS or status not in STAGE_STATUSES:
            raise ValueError(f"bad stage update {key!r}={status!r}")
        with self._lock:
            self._snap.stages[key] = status
            if status == "active":
                self._snap.stage = key
            self._changed("stage")

    def director(self, state: str, message: str = "") -> None:
        if state not in DIRECTOR_STATES:
            raise ValueError(f"unknown director state {state!r}")
        with self._lock:
            self._snap.director = DirectorStatus(state=state, message=message)
            self._event("director", state, message)
            self._changed("director")

    def cycle(self, **fields: Any) -> None:
        with self._lock:
            for name, value in fields.items():
                if not hasattr(self._snap, name):
                    raise AttributeError(name)
                setattr(self._snap, name, value)
            self._changed("cycle")

    def counter(self, key: str, value: Any) -> None:
        with self._lock:
            self._snap.counters[key] = value
            self._changed("counter")

    def link(self, key: str, url: str) -> None:
        with self._lock:
            self._snap.links[key] = url
            self._changed("link")

    def reset_for_cycle(self, *, cycle_id: str, theme: str, mode: str) -> None:
        """Start a fresh cycle: every stage pending, agents idle, Director has handed over."""
        with self._lock:
            self._snap.cycle_id = cycle_id
            self._snap.theme = theme
            self._snap.mode = mode
            self._snap.cycle_status = "running"
            self._snap.stage = "theme"
            self._snap.stages = {k: "pending" for k in STAGE_KEYS}
            self._snap.counters = {}
            self._snap.links = {}
            for key in AGENT_KEYS:
                self._snap.agents[key] = AgentStatus(agent=key, state=AgentState.IDLE,
                                                     message="出番待ち", updated_at=iso_now())
            self._snap.director = DirectorStatus(state="received", message=theme)
            self._event("director", "received", theme)
            self._changed("cycle")

    def sleep_all(self, message: str = "") -> None:
        """Between cycles: everyone sleeps until the Director picks a theme."""
        with self._lock:
            for key in AGENT_KEYS:
                self._snap.agents[key] = AgentStatus(agent=key, state=AgentState.SLEEPING,
                                                     message=message, updated_at=iso_now())
            self._changed("agent")
