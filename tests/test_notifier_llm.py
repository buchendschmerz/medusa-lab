from __future__ import annotations

import io
import json
import types
from typing import Any

import pytest

from medusa.config import LLMConfig
from medusa.llm import (
    FALLBACK_BETA,
    ClaudeLLM,
    LLMError,
    LLMRefusal,
    OfflineLLM,
    create_llm,
    obj,
    s,
)
from medusa.notifier import GitHubAPI, IssueLiveReporter, Notifier
from medusa.state import StatusBoard


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class FakeGitHub:
    """Records REST calls made through GitHubAPI's opener."""

    def __init__(self, branches: list[str] | None = None) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.open_issues: list[dict[str, Any]] = [{"number": 3, "body": "<!-- medusa:theme-request cycle=2026-W38 -->",
                                                   "html_url": "https://github.com/o/r/issues/3"}]
        self.branches = branches or []

    def __call__(self, req: Any, timeout: float = 0) -> FakeResponse:
        body = json.loads(req.data) if req.data else None
        path = req.full_url.replace("https://api.github.com", "")
        self.calls.append((req.get_method(), path, body))
        if req.get_method() == "GET" and "/git/matching-refs/heads/" in path:
            prefix = path.split("/git/matching-refs/heads/", 1)[1]
            refs = [{"ref": f"refs/heads/{b}"} for b in self.branches if b.startswith(prefix)]
            return FakeResponse(json.dumps(refs).encode())
        if req.get_method() == "GET" and "/issues?" in path:
            return FakeResponse(json.dumps(self.open_issues).encode())
        if req.get_method() == "POST" and path.endswith("/issues"):
            issue = {"number": 7, "html_url": "https://github.com/o/r/issues/7", "body": body["body"]}
            self.open_issues.append(issue)
            return FakeResponse(json.dumps(issue).encode())
        if path.endswith("/comments") and req.get_method() == "POST":
            return FakeResponse(json.dumps({"id": 99}).encode())
        return FakeResponse(b"{}")


def test_ask_director_creates_issue_and_closes_old(cfg) -> None:  # type: ignore[no-untyped-def]
    fake = FakeGitHub()
    posted: list[dict[str, Any]] = []
    notifier = Notifier(cfg, env={"SLACK_WEBHOOK_URL": "https://hooks.slack/x", "DISCORD_WEBHOOK_URL": "https://d/x"},
                        github=GitHubAPI("t", "o/r", opener=fake), http=lambda url, payload: posted.append(payload) or 200)
    result = notifier.ask_director("2026-W39", "title", "<!-- medusa:theme-request cycle=2026-W39 -->\nbody")
    assert result.issue_number == 7 and result.sent == ["slack", "discord"]
    methods = [(m, p) for m, p, _ in fake.calls]
    assert ("POST", "/repos/o/r/issues") in methods
    assert ("PATCH", "/repos/o/r/issues/3") in methods  # last week's request closed
    assert "blocks" in posted[0] and "embeds" in posted[1]
    again = notifier.ask_director("2026-W39", "title", "body")
    assert again.issue_number == 7 and "already open" in again.errors[0]


def test_ask_director_without_token_prints(cfg, capsys) -> None:  # type: ignore[no-untyped-def]
    result = Notifier(cfg, env={}).ask_director("2026-W39", "Title", "Body")
    assert result.printed and "Body" in capsys.readouterr().out


def test_live_reporter_throttles(cfg) -> None:  # type: ignore[no-untyped-def]
    fake = FakeGitHub()
    clock = iter([0.0, 1.0, 2.0, 50.0, 51.0]).__next__
    reporter = IssueLiveReporter(GitHubAPI("t", "o/r", opener=fake), 7, clock=clock, min_interval=20)
    board = StatusBoard(None)
    board.subscribe(reporter)
    board.reset_for_cycle(cycle_id="2026-W39", theme="t", mode="hybrid")  # cycle -> push (create)
    from medusa.state import AgentState

    board.agent("scout", AgentState.SEARCHING, "a")  # throttled
    board.agent("scout", AgentState.SEARCHING, "b")  # throttled
    board.agent("scout", AgentState.READING, "c")    # 50s later -> update
    creates = [c for c in fake.calls if c[0] == "POST" and c[1].endswith("/comments")]
    updates = [c for c in fake.calls if c[0] == "PATCH"]
    assert len(creates) == 1 and len(updates) == 1 and reporter.comment_id == 99


def test_live_reporter_body_reflects_terminal_states(cfg) -> None:  # type: ignore[no-untyped-def]
    from medusa.state import StatusBoard

    reporter = IssueLiveReporter(GitHubAPI("t", "o/r"), 7, lang="en")
    board = StatusBoard(None)
    board.reset_for_cycle(cycle_id="2026-W39", theme="t", mode="hybrid")
    board.cycle(cycle_status="error")
    assert "failed" in reporter.body(board.snapshot).lower()
    board.cycle(cycle_status="done")
    assert "finished" in reporter.body(board.snapshot).lower()


def test_live_reporter_never_raises_into_the_board(cfg) -> None:  # type: ignore[no-untyped-def]
    class Boom:
        def comment(self, *a: Any, **k: Any) -> Any:
            raise ValueError("empty 2xx body")  # not a GitHubError/OSError/KeyError

    reporter = IssueLiveReporter(Boom(), 7)  # type: ignore[arg-type]
    board = StatusBoard(None)
    board.reset_for_cycle(cycle_id="2026-W39", theme="t", mode="hybrid")
    board.subscribe(reporter)
    board.cycle(cycle_status="running")  # must not propagate the ValueError
    assert reporter.failed is True


def test_reserve_cycle_id_skips_open_pr_branch(cfg) -> None:  # type: ignore[no-untyped-def]
    from medusa.models import ResearchTheme
    from medusa.orchestrator import Orchestrator

    orch = Orchestrator(cfg, console=False)
    theme = ResearchTheme(title="new words", cycle_id="2026-W39")
    # no remote info -> the plain week is free
    assert orch.reserve_cycle_id(theme, github=None) == "2026-W39"
    # an open PR already owns medusa/2026-W39 -> a different theme must not collide on it
    gh = GitHubAPI("t", "o/r", opener=FakeGitHub(branches=["medusa/2026-W39"]))
    assert orch.reserve_cycle_id(theme, github=gh) == "2026-W39-2"


# ----------------------------------------------------------------------------- Claude client
class _Stream:
    def __init__(self, message: Any) -> None:
        self.message = message

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_final_message(self) -> Any:
        return self.message


def _message(stop: str = "end_turn", text: str = '{"answer": "ok"}') -> Any:
    usage = types.SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=50,
                                  cache_creation_input_tokens=0)
    return types.SimpleNamespace(stop_reason=stop, model="claude-opus-5", usage=usage,
                                 content=[types.SimpleNamespace(type="thinking", thinking=""),
                                          types.SimpleNamespace(type="text", text=text)],
                                 stop_details=types.SimpleNamespace(category="cyber"))


def _claude(message: Any, captured: dict[str, Any], **cfg: Any) -> ClaudeLLM:
    pytest.importorskip("anthropic")
    llm = ClaudeLLM(LLMConfig(**cfg))

    def stream(**params: Any) -> _Stream:
        captured.update(params)
        return _Stream(message)

    llm.client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=types.SimpleNamespace(stream=stream)))
    return llm


def test_claude_request_shape_and_parsing() -> None:
    captured: dict[str, Any] = {}
    llm = _claude(_message(), captured)
    data = llm.generate_json(system="sys", prompt="question", schema=obj({"answer": s()}), cache_prefix="PAPER",
                             purpose="reviewer", effort="medium")
    assert data == {"answer": "ok"}
    assert captured["model"] == "claude-opus-5"
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"]["effort"] == "medium"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert captured["fallbacks"] == "default" and captured["betas"] == [FALLBACK_BETA]
    content = captured["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "PAPER", "cache_control": {"type": "ephemeral"}}
    report = llm.usage_report()
    assert report["by_agent"]["reviewer"]["cache_read_tokens"] == 50 and report["estimated_cost_usd"] is not None


def test_claude_without_fallbacks_and_errors() -> None:
    captured: dict[str, Any] = {}
    llm = _claude(_message(), captured, fallbacks=None, thinking="none")
    llm.generate(system="s", prompt="p")
    assert "fallbacks" not in captured and "betas" not in captured and "thinking" not in captured
    with pytest.raises(LLMRefusal):
        _claude(_message(stop="refusal"), {}).generate(system="s", prompt="p")
    with pytest.raises(LLMError):
        _claude(_message(stop="max_tokens"), {}).generate(system="s", prompt="p")
    with pytest.raises(LLMError):
        _claude(_message(text="not json"), {}).generate(system="s", prompt="p", schema=obj({"a": s()}))


def test_claude_wraps_midstream_transport_error() -> None:
    pytest.importorskip("anthropic")
    llm = ClaudeLLM(LLMConfig())

    class Dropping:  # get_final_message() raising a raw (non-SDK) error mimics a connection drop mid-stream
        def __enter__(self) -> Dropping:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def get_final_message(self) -> Any:
            raise ConnectionResetError("peer closed the connection")

    llm.client = types.SimpleNamespace(
        beta=types.SimpleNamespace(messages=types.SimpleNamespace(stream=lambda **k: Dropping())))
    with pytest.raises(LLMError, match="streaming failed"):
        llm.generate(system="s", prompt="p")


def test_provider_selection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(create_llm(LLMConfig(provider="offline")), OfflineLLM)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    auto = create_llm(LLMConfig(provider="auto"), env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert auto.offline  # no key, no profile
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert not create_llm(LLMConfig(provider="auto"), env={"ANTHROPIC_API_KEY": "sk-test"}).offline
