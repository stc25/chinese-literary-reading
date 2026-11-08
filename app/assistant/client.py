"""A small client for the Ollama chat API, local or cloud.

Only the server talks to the model; the API key never reaches the browser.
Every call asks for JSON matching a schema (Ollama's `format` parameter).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import requests


class ModelError(Exception):
    """The model could not be reached or did not give a usable answer."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds
        self.calls += other.calls


@dataclass
class Reply:
    data: dict
    usage: Usage = field(default_factory=Usage)


class OllamaClient:
    def __init__(self, host: str, model: str, api_key: str = "", timeout: float = 60.0,
                 temperature: float = 0.2, session: requests.Session | None = None):
        self.host = host.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.session = session or requests.Session()

    def chat_json(self, system: str, user: str, schema: dict, validate=None, retries: int = 1) -> Reply:
        """Send one exchange and return the parsed JSON.

        `validate(data)` may raise ValueError; the call is then retried once with the
        same request before giving up.
        """
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": self.temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        total = Usage()
        last_error: Exception | None = None
        for _ in range(retries + 1):
            start = time.monotonic()
            try:
                r = self.session.post(f"{self.host}/api/chat", json=payload, headers=headers, timeout=self.timeout)
            except requests.Timeout as e:
                raise ModelError("The AI service took too long to answer.") from e
            except requests.RequestException as e:
                raise ModelError("The AI service could not be reached.") from e
            if r.status_code == 429:
                raise ModelError("The AI service's usage limit has been reached. Please try again later.")
            if r.status_code >= 400:
                raise ModelError(f"The AI service returned an error ({r.status_code}).")
            body = r.json()
            total.add(Usage(body.get("prompt_eval_count", 0), body.get("eval_count", 0),
                            time.monotonic() - start, 1))
            content = (body.get("message") or {}).get("content", "")
            try:
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("not a JSON object")
                if validate:
                    validate(data)
                return Reply(data, total)
            except (ValueError, KeyError, TypeError) as e:
                last_error = e
        raise ModelError("The AI service did not give a usable answer.") from last_error


def client_from_config(config) -> OllamaClient:
    return OllamaClient(
        host=config.get("OLLAMA_HOST", "http://localhost:11434"),
        model=config.get("ASSISTANT_MODEL", "qwen3.5:9b"),
        api_key=config.get("OLLAMA_API_KEY", ""),
        timeout=float(config.get("ASSISTANT_TIMEOUT", 60)),
    )
