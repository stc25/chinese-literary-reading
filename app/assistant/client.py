"""A small client for the Ollama chat API, local or cloud.

Only the server talks to the model; the API key never reaches the browser.
Every call asks for JSON matching a schema (Ollama's `format` parameter).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests


log = logging.getLogger(__name__)

NOT_SET_UP = "The AI service is not set up correctly. Please tell the course team; the course glossary, grammar and date steps still work."
UNAVAILABLE = "The AI service is not available at the moment. Please try again in a few minutes."
TOO_SLOW = "The AI service took too long to answer. Please try again, or try a shorter text."


class ModelError(Exception):
    """The model could not be reached or did not give a usable answer.

    The message is shown to the learner. `service_fault` is True when the service did no
    work (it could not be reached, refused the request, or failed): the call is then not
    counted against the learner. An unusable answer or a timeout used the model, so it counts.
    """

    def __init__(self, message: str, service_fault: bool = True):
        super().__init__(message)
        self.service_fault = service_fault


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
    """Thread-safe: each thread has its own HTTP session and its own deadline."""

    def __init__(self, host: str, model: str, api_key: str = "", timeout: float = 60.0,
                 temperature: float = 0.2, session: requests.Session | None = None, retry_pause: float = 1.0):
        self.host = host.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.retry_pause = retry_pause
        self._session = session                   # tests pass a stub; otherwise one per thread
        self._local = threading.local()

    @property
    def session(self):
        if self._session is not None:
            return self._session
        s = getattr(self._local, "session", None)
        if s is None:
            s = self._local.session = requests.Session()
        return s

    @contextmanager
    def deadline(self, seconds: float):
        """Limit the total time of all calls made in this block (one step may make several)."""
        old = getattr(self._local, "deadline", None)
        self._local.deadline = time.monotonic() + seconds
        try:
            yield
        finally:
            self._local.deadline = old

    def _time_left(self) -> float:
        d = getattr(self._local, "deadline", None)
        if d is None:
            return self.timeout
        left = d - time.monotonic()
        if left <= 1:
            raise ModelError(TOO_SLOW, service_fault=False)
        return min(self.timeout, left)

    def chat_json(self, system: str, user: str, schema: dict, validate=None, retries: int = 1) -> Reply:
        """Send one exchange and return the parsed JSON.

        An unusable answer (invalid JSON, or `validate(data)` raising ValueError) and a
        temporary failure (connection error, 5xx) are each retried `retries` times.
        Errors are logged with the status and timing only, never the text.
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
        for attempt in range(retries + 1):
            if attempt and last_error is not None and isinstance(last_error, ModelError):
                time.sleep(self.retry_pause)      # a temporary failure: pause before trying again
            start = time.monotonic()
            try:
                r = self.session.post(f"{self.host}/api/chat", json=payload, headers=headers,
                                      timeout=self._time_left())
            except requests.Timeout as e:
                log.warning("model %s: timed out after %.0f s", self.model, time.monotonic() - start)
                raise ModelError(TOO_SLOW, service_fault=False) from e
            except requests.RequestException as e:
                log.warning("model %s: could not connect to %s (%s)", self.model, self.host, type(e).__name__)
                last_error = ModelError(UNAVAILABLE)
                continue
            if r.status_code == 429:
                log.warning("model %s: the service's usage limit was reached (429)", self.model)
                raise ModelError("The AI service's usage limit has been reached. Please try again later.")
            if r.status_code in (401, 402, 403, 404):
                # A wrong key, a model not in the plan, or a model name that does not exist: an admin must act.
                log.error("model %s: the service refused the request (%s): %s", self.model, r.status_code,
                          r.text[:300])
                raise ModelError(NOT_SET_UP)
            if r.status_code >= 500:
                log.warning("model %s: service error %s", self.model, r.status_code)
                last_error = ModelError(UNAVAILABLE)
                continue
            if r.status_code >= 400:
                log.error("model %s: request rejected (%s): %s", self.model, r.status_code, r.text[:300])
                raise ModelError(f"The AI service returned an error ({r.status_code}).")
            try:
                body = r.json()
            except ValueError:
                log.warning("model %s: the service's answer was not JSON", self.model)
                last_error = ValueError("answer not JSON")
                continue
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
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                last_error = e
        if isinstance(last_error, ModelError):
            raise last_error
        log.warning("model %s: no usable answer after %d attempts (%s)", self.model, retries + 1,
                    type(last_error).__name__)
        raise ModelError("The AI service did not give a usable answer. Please try again.",
                         service_fault=False) from last_error


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
