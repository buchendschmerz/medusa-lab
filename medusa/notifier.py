"""Talking to the Director: GitHub Issues (with live status comments), Slack and Discord.

Credentials come from the environment (``GITHUB_TOKEN``, ``GITHUB_REPOSITORY``,
``SLACK_WEBHOOK_URL``, ``DISCORD_WEBHOOK_URL``). Everything degrades gracefully:
without credentials, messages are printed instead of sent.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .state import LabSnapshot
from .visualizer import render_status_markdown

log = logging.getLogger("medusa.notifier")

LABEL_COLORS = {"medusa:theme-request": "1baf7a", "medusa:running": "2a78d6", "medusa:done": "0ca30c",
                "medusa:paper": "6a4fd6"}


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


class GitHubAPI:
    """Minimal GitHub REST client (stdlib only)."""

    def __init__(self, token: str, repo: str, *, api_url: str = "https://api.github.com", timeout: float = 20,
                 opener: Callable[..., Any] | None = None) -> None:
        if "/" not in repo:
            raise ValueError("repo must look like owner/name")
        self.token = token
        self.repo = repo
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        url = f"{self.api_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "medusa-lab",
            **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with self._open(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise GitHubError(exc.code, detail) from exc
        return json.loads(raw) if raw else None

    @property
    def base(self) -> str:
        return f"/repos/{self.repo}"

    def ensure_label(self, name: str, color: str = "6e6378", description: str = "") -> None:
        try:
            self.request("POST", f"{self.base}/labels", {"name": name, "color": color, "description": description})
        except GitHubError as exc:
            if exc.status != 422:  # 422 = already exists
                raise

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        return self.request("POST", f"{self.base}/issues", {"title": title, "body": body, "labels": labels})

    def list_issues(self, label: str, state: str = "open") -> list[dict[str, Any]]:
        from urllib.parse import quote

        issues = self.request("GET", f"{self.base}/issues?labels={quote(label)}&state={state}&per_page=50") or []
        return [i for i in issues if "pull_request" not in i]

    def matching_branches(self, prefix: str) -> list[str]:
        """Branch names (``heads/`` stripped) that start with ``prefix`` — includes branches of
        still-open PRs, which a fresh checkout of the default branch cannot see locally."""
        from urllib.parse import quote

        refs = self.request("GET", f"{self.base}/git/matching-refs/heads/{quote(prefix)}") or []
        return [r["ref"].split("refs/heads/", 1)[-1] for r in refs if isinstance(r, dict) and r.get("ref")]

    def comment(self, number: int, body: str) -> dict[str, Any]:
        return self.request("POST", f"{self.base}/issues/{number}/comments", {"body": body})

    def update_comment(self, comment_id: int, body: str) -> dict[str, Any]:
        return self.request("PATCH", f"{self.base}/issues/comments/{comment_id}", {"body": body})

    def react(self, comment_id: int, content: str) -> None:
        self.request("POST", f"{self.base}/issues/comments/{comment_id}/reactions", {"content": content})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.request("POST", f"{self.base}/issues/{number}/labels", {"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        from urllib.parse import quote

        try:
            self.request("DELETE", f"{self.base}/issues/{number}/labels/{quote(label)}")
        except GitHubError as exc:
            if exc.status != 404:
                raise

    def close_issue(self, number: int, reason: str = "completed") -> None:
        self.request("PATCH", f"{self.base}/issues/{number}", {"state": "closed", "state_reason": reason})


def post_json(url: str, payload: Mapping[str, Any], timeout: float = 15) -> int:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "medusa-lab"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-configured webhook
        return resp.status


@dataclass
class NotifyResult:
    issue_url: str = ""
    issue_number: int | None = None
    sent: list[str] = field(default_factory=list)
    printed: bool = False
    errors: list[str] = field(default_factory=list)


class Notifier:
    def __init__(self, cfg: Config, *, env: Mapping[str, str] | None = None,
                 github: GitHubAPI | None = None, http: Callable[..., int] = post_json) -> None:
        self.cfg = cfg
        self.env = dict(os.environ if env is None else env)
        self.http = http
        self.github = github or self._github_from_env()

    def _github_from_env(self) -> GitHubAPI | None:
        token, repo = self.env.get("GITHUB_TOKEN", ""), self.env.get("GITHUB_REPOSITORY", "")
        if token and repo and self.cfg.notify.github_issue:
            return GitHubAPI(token, repo, api_url=self.env.get("GITHUB_API_URL", "https://api.github.com"))
        return None

    @property
    def run_url(self) -> str:
        server, repo, run = (self.env.get("GITHUB_SERVER_URL", "https://github.com"),
                             self.env.get("GITHUB_REPOSITORY", ""), self.env.get("GITHUB_RUN_ID", ""))
        return f"{server}/{repo}/actions/runs/{run}" if repo and run else ""

    # ------------------------------------------------------------------ chat webhooks
    def chat(self, title: str, text: str, url: str = "", *, color: int = 0x1BAF7A) -> list[str]:
        sent = []
        slack = self.env.get(self.cfg.notify.slack_webhook_env, "")
        discord = self.env.get(self.cfg.notify.discord_webhook_env, "")
        link = f"\n{url}" if url else ""
        image = self.cfg.notify.dashboard_url
        image = image if image.lower().split("?")[0].endswith((".gif", ".png")) else ""  # chat apps cannot show SVG
        if slack:
            blocks: list[dict[str, Any]] = [
                {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
                {"type": "section", "text": {"type": "mrkdwn", "text": (text + (f"\n<{url}|→ GitHub>" if url else ""))[:2900]}}]
            if image:
                blocks.append({"type": "image", "image_url": image, "alt_text": f"{self.cfg.lab.name} dashboard"})
            payload = {"text": f"{title}\n{text}{link}", "blocks": blocks}
            try:
                self.http(slack, payload)
                sent.append("slack")
            except Exception as exc:  # noqa: BLE001 - notifications are best effort
                log.warning("Slack notification failed: %s", exc)
        if discord:
            embed: dict[str, Any] = {"title": title[:250], "description": text[:4000], "url": url or None, "color": color}
            if image:
                embed["image"] = {"url": image}
            payload = {"username": self.cfg.lab.name, "content": title[:1900], "embeds": [embed]}
            try:
                self.http(discord, payload)
                sent.append("discord")
            except Exception as exc:  # noqa: BLE001
                log.warning("Discord notification failed: %s", exc)
        return sent

    # ------------------------------------------------------------------ Monday prompt
    def ask_director(self, cycle_id: str, title: str, body: str, *, dry_run: bool = False) -> NotifyResult:
        result = NotifyResult()
        label = self.cfg.notify.issue_label
        if dry_run or self.github is None:
            print(f"# {title}\n\n{body}")
            result.printed = True
            if self.github is None and not dry_run:
                result.errors.append("GITHUB_TOKEN/GITHUB_REPOSITORY not set: printed the request instead")
            return result
        gh = self.github
        # never open two requests for the same week
        for issue in gh.list_issues(label):
            if f"cycle={cycle_id}" in (issue.get("body") or ""):
                result.issue_url, result.issue_number = issue["html_url"], issue["number"]
                result.errors.append(f"theme request for {cycle_id} already open: #{issue['number']}")
                return result
        gh.ensure_label(label, LABEL_COLORS.get(label, "1baf7a"), "Medusa Lab weekly theme request")
        issue = gh.create_issue(title, body, [label])
        result.issue_url, result.issue_number = issue["html_url"], issue["number"]
        # close older, unanswered requests
        for old in gh.list_issues(label):
            if old["number"] != issue["number"]:
                try:
                    gh.comment(old["number"], f"🗓️ 新しい週のテーマ募集 #{issue['number']} に引き継ぎました。"
                                              if self.cfg.lab.language == "ja" else
                               f"🗓️ Superseded by this week's request #{issue['number']}.")
                    gh.close_issue(old["number"], "not_planned")
                except GitHubError as exc:
                    result.errors.append(str(exc))
        ja = self.cfg.lab.language == "ja"
        result.sent = self.chat(title, ("Issueに `/theme <テーマ>` とコメントすると研究サイクルが始まります。" if ja else
                                        "Reply on the Issue with `/theme <topic>` to start the research cycle."),
                                result.issue_url)
        return result

    # ------------------------------------------------------------------ cycle lifecycle
    def acknowledge(self, issue_number: int | None, comment_id: int | None) -> None:
        if not self.github:
            return
        try:
            if comment_id:
                self.github.react(comment_id, "eyes")
            if issue_number:
                self.github.ensure_label("medusa:running", LABEL_COLORS["medusa:running"], "Research cycle running")
                self.github.add_labels(issue_number, ["medusa:running"])
        except GitHubError as exc:
            log.warning("could not acknowledge the theme comment: %s", exc)

    def finish(self, issue_number: int | None, summary_md: str, *, pr_url: str = "", comment_id: int | None = None,
               ok: bool = True) -> None:
        ja = self.cfg.lab.language == "ja"
        title = (f"🐍 {self.cfg.lab.name}: " + ("研究サイクル完了" if ok else "研究サイクルでエラーが発生") if ja else
                 f"🐍 {self.cfg.lab.name}: " + ("research cycle finished" if ok else "research cycle failed"))
        link = pr_url or self.run_url
        if self.github and issue_number:
            try:
                extra = (f"\n\n📬 **Pull Request:** {pr_url}" if pr_url else "") + (
                    f"\n\n⚙️ Run: {self.run_url}" if self.run_url else "")
                self.github.comment(issue_number, summary_md + extra)
                self.github.remove_label(issue_number, "medusa:running")
                if ok:
                    self.github.ensure_label("medusa:done", LABEL_COLORS["medusa:done"], "Research cycle finished")
                    self.github.add_labels(issue_number, ["medusa:done"])
                if comment_id:
                    self.github.react(comment_id, "rocket" if ok else "confused")
            except GitHubError as exc:
                log.warning("could not post the final comment: %s", exc)
        text = summary_md.split("\n\n", 2)[1] if summary_md.count("\n\n") >= 2 else summary_md[:500]
        self.chat(title, text[:1500], link, color=0x0CA30C if ok else 0xD03B3B)


class IssueLiveReporter:
    """StatusBoard subscriber that keeps one Issue comment updated with live status."""

    def __init__(self, api: GitHubAPI, issue_number: int, *, lang: str = "ja", run_url: str = "",
                 image_url: str = "", min_interval: float = 20.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.api = api
        self.issue_number = issue_number
        self.lang = lang
        self.run_url = run_url
        self.image_url = image_url
        self.min_interval = min_interval
        self.clock = clock
        self.comment_id: int | None = None
        self._last = -1e9
        self._last_stage = ""
        self.failed = False

    def body(self, snap: LabSnapshot) -> str:
        ja = self.lang == "ja"
        heads = {
            "done": "✅ **研究サイクル完了**" if ja else "✅ **Research cycle finished**",
            "error": "❌ **研究サイクルは失敗しました**" if ja else "❌ **Research cycle failed**",
            "waiting": "💤 **所長のテーマ待ち**" if ja else "💤 **Waiting for the Director's theme**",
        }
        head = heads.get(snap.cycle_status,
                         "🧪 **研究サイクル進行中** — このコメントは自動で更新されます。" if ja else
                         "🧪 **Research cycle in progress** — this comment updates automatically.")
        run = f"\n\n⚙️ {self.run_url}" if self.run_url else ""
        return f"{head}\n\n{render_status_markdown(snap, lang=self.lang, image_url=self.image_url or None)}{run}"

    def __call__(self, snap: LabSnapshot, kind: str) -> None:
        if self.failed:
            return
        now = self.clock()
        stage_changed = snap.stage != self._last_stage or kind in ("stage", "cycle")
        if not stage_changed and now - self._last < self.min_interval:
            return
        self._last, self._last_stage = now, snap.stage
        self.push(snap)

    def push(self, snap: LabSnapshot) -> None:
        try:
            if self.comment_id is None:
                self.comment_id = self.api.comment(self.issue_number, self.body(snap))["id"]
            else:
                self.api.update_comment(self.comment_id, self.body(snap))
        except Exception as exc:  # runs inside StatusBoard notifications — must never break the cycle
            log.warning("live status comment disabled: %s", exc)
            self.failed = True
