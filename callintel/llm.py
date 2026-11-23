#!/usr/bin/env python3
"""LLM client -- the one place the pipeline talks to a model.

Uses the OpenAI-compatible **Chat Completions** API, which means it works both
with OpenAI *and* with any local OpenAI-compatible server -- notably **Ollama**
(`http://localhost:11434/v1`). No OpenAI key required for local models; all the
pipeline actually needs from the model is a JSON response.

Behaviour:
  * `temperature=0` for repeatable extraction;
  * structured output requested as `response_format` with a strict JSON schema,
    degrading to a plain `json_object` and then to prompt-only JSON if a backend
    does not support it (Ollama versions vary; older ones only do `json_object`);
  * param-graceful degrade (drop `temperature`/`max_tokens` if a backend rejects
    them); retries/backoff are delegated to the official SDK.

The punchline this serves: black boxes can't be opened -- but strategic facts
and quotes buy you auditability, and a possible explanation. The model is kept
to a narrow JSON-returning job so everything it says can be checked.
"""
from __future__ import annotations

from typing import Any

from openai import BadRequestError, OpenAI

# Default model when targeting OpenAI. For local use, pass --model / set a model
# env var (see callintel.core.apply_model_default) -- e.g. llama3.1 on Ollama.
DEFAULT_MODEL = "gpt-4o-mini"


class LLMClient:
    """OpenAI-compatible Chat Completions client (OpenAI or local, e.g. Ollama)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str | None = None,
        timeout: int = 120,
        max_retries: int = 5,
        max_output_tokens: int = 1800,
    ) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": max_retries}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.base_url = base_url
        self.max_output_tokens = max_output_tokens

    def complete(self, prompt: str, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """One completion. With `schema`, request strict JSON; degrade gracefully."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "facts", "schema": schema, "strict": True},
            }

        resp = None
        for _ in range(6):
            try:
                resp = self.client.chat.completions.create(**payload)
                break
            except BadRequestError as exc:
                msg = str(getattr(exc, "message", exc)).lower()
                rf = payload.get("response_format")
                # 1) strict json_schema unsupported -> plain json_object
                if isinstance(rf, dict) and rf.get("type") == "json_schema":
                    payload["response_format"] = {"type": "json_object"}
                    continue
                # 2) json_object unsupported -> rely on prompt-enforced JSON
                if isinstance(rf, dict) and rf.get("type") == "json_object":
                    payload.pop("response_format", None)
                    continue
                # 3) a sampling/length param was rejected -> drop it and retry
                dropped = next(
                    (p for p in ("temperature", "max_tokens")
                     if p in payload and (p in msg or p.replace("_", " ") in msg)),
                    None,
                )
                if dropped is not None:
                    payload.pop(dropped, None)
                    continue
                raise
        if resp is None:  # pragma: no cover - last-ditch, minimal request
            resp = self.client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}]
            )

        choice = resp.choices[0] if resp.choices else None
        content = (getattr(getattr(choice, "message", None), "content", None) or "").strip()
        usage = getattr(resp, "usage", None)
        return {
            "text": content,
            "in": getattr(usage, "prompt_tokens", None),
            "out": getattr(usage, "completion_tokens", None),
        }
