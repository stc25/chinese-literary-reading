"""The reading assistant (docs/assistant-plan.md).

The page (A1) shows the deterministic layer: course glossary, grammar forms, dates.
The AI steps (A2) are JSON endpoints under /assistant/api/, called by the page's script.
Texts are sent by POST, so they never appear in URLs or server logs, and nothing the
learner pastes is stored.

The Django views are in views.py.
This module imports no web framework.
"""
from . import steps  # noqa: F401
from .client import ModelError, OllamaClient, client_from_config  # noqa: F401
from .limits import Limits  # noqa: F401
