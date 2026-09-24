"""LLM access for the agents.

* :class:`ClaudeLLM` calls Claude through the official Anthropic SDK: streaming
  (large ``max_tokens`` without HTTP timeouts), adaptive thinking, structured
  JSON outputs (``output_config.format``) and server-side refusal fallbacks.
* :class:`OfflineLLM` is used when no credentials/SDK are available. Agents
  check ``llm.offline`` and switch to their deterministic, template-driven path,
  so the whole weekly cycle still runs end to end (useful for CI and demos).
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ConfigError, LLMConfig

log = logging.getLogger("medusa.llm")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens (input, output) — used only for the cost estimate in reports.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-fable-5-1": (10.0, 50.0),
}


class LLMError(RuntimeError):
    """The model call failed (network, API error, invalid output...)."""


class LLMUnavailable(LLMError):
    """No usable model (offline mode, missing SDK or credentials)."""


class LLMRefusal(LLMError):
    """The model (and any fallback) declined the request."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    def cost_usd(self, model: str) -> float | None:
        price = PRICES.get(model)
        if not price:
            return None
        pin, pout = price
        return round((self.input_tokens * pin + self.cache_write_tokens * pin * 1.25
                      + self.cache_read_tokens * pin * 0.1 + self.output_tokens * pout) / 1e6, 4)


@dataclass
class LLMResult:
    text: str
    data: Any = None
    model: str = ""
    stop_reason: str = ""
    usage: Usage = field(default_factory=Usage)


class LLM:
    """Common interface. ``purpose`` labels calls for per-agent usage accounting."""

    offline: bool = True
    model: str = "offline"
    reason: str = ""

    def __init__(self) -> None:
        self.usage: dict[str, Usage] = {}

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any] | None = None,
                 effort: str | None = None, cache_prefix: str | None = None, purpose: str = "") -> LLMResult:
        raise NotImplementedError

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any], **kw: Any) -> dict[str, Any]:
        result = self.generate(system=system, prompt=prompt, schema=schema, **kw)
        if not isinstance(result.data, dict):
            raise LLMError("model did not return a JSON object")
        return result.data

    def total_usage(self) -> Usage:
        total = Usage()
        for u in self.usage.values():
            total.add(u)
        return total

    def usage_report(self) -> dict[str, Any]:
        total = self.total_usage()
        return {
            "model": self.model,
            "offline": self.offline,
            "by_agent": {k: vars(v) for k, v in self.usage.items()},
            "total": vars(total),
            "estimated_cost_usd": None if self.offline else total.cost_usd(self.model),
        }

    def describe(self) -> str:
        return f"offline ({self.reason})" if self.offline else self.model


class OfflineLLM(LLM):
    offline = True

    def __init__(self, reason: str = "offline mode") -> None:
        super().__init__()
        self.reason = reason
        self.model = "offline"

    def generate(self, **_: Any) -> LLMResult:  # type: ignore[override]
        raise LLMUnavailable(f"LLM unavailable: {self.reason}")


class ClaudeLLM(LLM):
    offline = False

    def __init__(self, cfg: LLMConfig) -> None:
        super().__init__()
        import anthropic  # optional dependency: pip install "medusa-lab[llm]"

        self._sdk = anthropic
        self.cfg = cfg
        self.model = cfg.model
        self.client = anthropic.Anthropic(timeout=cfg.timeout_sec, max_retries=3)

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any] | None = None,
                 effort: str | None = None, cache_prefix: str | None = None, purpose: str = "") -> LLMResult:
        sdk = self._sdk
        content: list[dict[str, Any]] = []
        if cache_prefix:
            # Shared context (e.g. the paper under review) first, so repeated calls hit the prompt cache.
            content.append({"type": "text", "text": cache_prefix, "cache_control": {"type": "ephemeral"}})
        content.append({"type": "text", "text": prompt})
        params: dict[str, Any] = {
            "model": self.cfg.model,
            "max_tokens": self.cfg.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
        }
        if self.cfg.thinking == "adaptive":
            params["thinking"] = {"type": "adaptive"}
        output_config: dict[str, Any] = {"effort": effort or self.cfg.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        params["output_config"] = output_config
        if self.cfg.fallbacks:
            params["fallbacks"] = self.cfg.fallbacks
            params["betas"] = [FALLBACK_BETA]

        try:
            with self.client.beta.messages.stream(**params) as stream:
                message = stream.get_final_message()
        except sdk.AuthenticationError as exc:
            raise LLMUnavailable(f"authentication failed: {exc.message}") from exc
        except sdk.PermissionDeniedError as exc:
            raise LLMUnavailable(f"permission denied: {exc.message}") from exc
        except sdk.NotFoundError as exc:
            raise LLMError(f"model or endpoint not found ({self.cfg.model}): {exc.message}") from exc
        except sdk.RateLimitError as exc:
            raise LLMError(f"rate limited after retries: {exc.message}") from exc
        except sdk.BadRequestError as exc:
            raise LLMError(f"bad request: {exc.message}") from exc
        except sdk.APIStatusError as exc:
            raise LLMError(f"API error {exc.status_code}: {exc.message}") from exc
        except sdk.APIConnectionError as exc:
            raise LLMError(f"connection error: {exc}") from exc
        except Exception as exc:  # a drop *mid-stream* surfaces as a raw transport error, not an SDK error
            raise LLMError(f"streaming failed: {type(exc).__name__}: {exc}") from exc

        usage = Usage(calls=1)
        u = getattr(message, "usage", None)
        if u is not None:
            usage.input_tokens = getattr(u, "input_tokens", 0) or 0
            usage.output_tokens = getattr(u, "output_tokens", 0) or 0
            usage.cache_read_tokens = getattr(u, "cache_read_input_tokens", 0) or 0
            usage.cache_write_tokens = getattr(u, "cache_creation_input_tokens", 0) or 0
        self.usage.setdefault(purpose or "misc", Usage()).add(usage)

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMRefusal(f"request declined (category: {category or 'unspecified'})")
        if message.stop_reason == "max_tokens":
            raise LLMError("response truncated at max_tokens")

        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        data = _parse_json(text) if schema is not None else None
        log.debug("llm[%s] %s in=%d out=%d", purpose, message.model, usage.input_tokens, usage.output_tokens)
        return LLMResult(text=text, data=data, model=getattr(message, "model", self.cfg.model),
                         stop_reason=message.stop_reason or "", usage=usage)


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)  # tolerate stray prose around the object
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError("model output was not valid JSON")


def has_anthropic_credentials(env: Mapping[str, str] | None = None) -> bool:
    """Best-effort check; an unset ANTHROPIC_API_KEY does not rule out a CLI login profile."""
    env = os.environ if env is None else env
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        if env.get(key, "").strip():
            return True
    if env.get("ANTHROPIC_FEDERATION_RULE_ID") and (env.get("ANTHROPIC_IDENTITY_TOKEN_FILE")
                                                     or env.get("ANTHROPIC_IDENTITY_TOKEN")):
        return True
    profile_dir = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "anthropic"
    return profile_dir.is_dir() and any(profile_dir.iterdir())


def create_llm(cfg: LLMConfig, env: Mapping[str, str] | None = None) -> LLM:
    if cfg.provider == "offline":
        return OfflineLLM("llm.provider = offline")
    try:
        import anthropic  # noqa: F401
    except ImportError as exc:
        if cfg.provider == "anthropic":
            raise ConfigError("llm.provider=anthropic but the SDK is missing: pip install 'medusa-lab[llm]'") from exc
        return OfflineLLM("anthropic SDK not installed")
    if cfg.provider == "auto" and not has_anthropic_credentials(env):
        return OfflineLLM("no Anthropic credentials found")
    return ClaudeLLM(cfg)


# ----------------------------------------------------------------------------- JSON schema helpers
def s(description: str = "") -> dict[str, Any]:
    return {"type": "string", **({"description": description} if description else {})}


def num(description: str = "") -> dict[str, Any]:
    return {"type": "number", **({"description": description} if description else {})}


def integer(description: str = "") -> dict[str, Any]:
    return {"type": "integer", **({"description": description} if description else {})}


def boolean(description: str = "") -> dict[str, Any]:
    return {"type": "boolean", **({"description": description} if description else {})}


def enum(values: list[str], description: str = "") -> dict[str, Any]:
    return {"type": "string", "enum": list(values), **({"description": description} if description else {})}


def arr(items: dict[str, Any], description: str = "") -> dict[str, Any]:
    return {"type": "array", "items": items, **({"description": description} if description else {})}


def obj(properties: dict[str, Any], description: str = "") -> dict[str, Any]:
    """Strict object: every property required, no extras (structured-output friendly)."""
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False, **({"description": description} if description else {})}
