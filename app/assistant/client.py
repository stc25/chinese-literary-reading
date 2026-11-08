"""A small client for the Ollama chat API, local or cloud.

Only the server talks to the model; the API key never reaches the browser.
Every call asks for JSON matching a schema (Ollama's `format` parameter).
"""
from __future__ import annotations

import json
import re
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
            # Some cloud models ignore "format", so the expected form is also stated in the message.
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": f"{user}\n\nReply with one JSON object that follows this "
                                                     f"JSON schema: {json.dumps(schema, ensure_ascii=False)}"}],
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
                data = parse_json_object(content)
                if not isinstance(data, dict):
                    raise ValueError("not a JSON object")
                if validate:
                    validate(data)
                return Reply(data, total)
            except (ValueError, KeyError, TypeError) as e:
                last_error = e
        raise ModelError("The AI service did not give a usable answer.") from last_error


def parse_json_object(content: str):
    """Parse the model's JSON, allowing a Markdown code fence or text around one object.

    Some cloud models ignore the requested format and wrap the JSON in ```json … ```.
    """
    try:
        return json.loads(content)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if m:
        return json.loads(m.group(1))
    a, b = content.find("{"), content.rfind("}")
    if a != -1 and b > a:
        return json.loads(content[a : b + 1])
    raise ValueError("no JSON object in the answer")


def client_from_config(config) -> OllamaClient:
    return OllamaClient(
        host=config.get("OLLAMA_HOST", "http://localhost:11434"),
        model=config.get("ASSISTANT_MODEL", "qwen3.5:9b"),
        api_key=config.get("OLLAMA_API_KEY", ""),
        timeout=float(config.get("ASSISTANT_TIMEOUT", 60)),
    )
