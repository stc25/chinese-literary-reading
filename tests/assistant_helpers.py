"""Model stubs shared by the assistant tests (no Django, no network)."""
import json as _json

from app.assistant.client import OllamaClient


class FakeResponse:
    def __init__(self, content, status=200):
        self.status_code = status
        self._body = {"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5}

    def json(self):
        return self._body


class FakeSession:
    """Returns the queued replies in order and records the requests."""

    def __init__(self, *replies, status=200):
        self.replies = list(replies)
        self.status = status
        self.requests = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers})
        content = self.replies.pop(0) if self.replies else "{}"
        return FakeResponse(content if isinstance(content, str) else _json.dumps(content), self.status)


def stub(*replies, status=200, api_key=""):
    return OllamaClient("http://model.test", "test-model", api_key=api_key, session=FakeSession(*replies, status=status))


class ScriptedSession:
    """Each item is a status code, an exception to raise, or a reply (dict or str) with status 200."""

    def __init__(self, *script):
        self.script = list(script)
        self.timeouts = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.timeouts.append(timeout)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            r = FakeResponse("{}", item)
            r.text = "refused"
            return r
        return FakeResponse(item if isinstance(item, str) else _json.dumps(item))


def scripted(*script, timeout=60.0):
    return OllamaClient("http://model.test", "test-model", session=ScriptedSession(*script), timeout=timeout,
                        retry_pause=0)
