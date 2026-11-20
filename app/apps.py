import threading
from pathlib import Path

from django.apps import AppConfig
from django.core.signals import setting_changed


class MlcConfig(AppConfig):
    name = "app"
    label = "app"
    default_auto_field = "django.db.models.BigAutoField"
    _store = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._assistant = {}                      # "limits", "gate", "client": shared by all requests
        self._assistant_lock = threading.Lock()

    def assistant_shared(self, name, make):
        """One limits object, gate or model client per process, created once even when the first
        requests arrive together."""
        obj = self._assistant.get(name)
        if obj is None:
            with self._assistant_lock:
                obj = self._assistant.get(name)
                if obj is None:
                    obj = self._assistant[name] = make()
        return obj

    def set_assistant(self, name, obj):
        """Tests swap in a stub model client (or a gate)."""
        with self._assistant_lock:
            self._assistant[name] = obj

    def reset_assistant(self):
        with self._assistant_lock:
            self._assistant.clear()

    @staticmethod
    def build_store(root, reload):
        """A CourseStore for `root`; raises ContentError if the content is invalid."""
        from .store import CourseStore
        return CourseStore(Path(root), bool(reload))

    def _build_from_settings(self):
        from django.conf import settings
        reload = settings.RELOAD_CONTENT
        return self.build_store(settings.CONTENT_DIR, settings.DEBUG if reload is None else reload)

    @property
    def course_store(self):
        """The shared store. Built at startup, except when testing (then on first use);
        tests may assign a store, and changing CONTENT_DIR, RELOAD_CONTENT or DEBUG resets it."""
        if self._store is None:
            self._store = self._build_from_settings()
        return self._store

    @course_store.setter
    def course_store(self, store):
        self._store = store

    def ready(self):
        from django.conf import settings
        setting_changed.connect(self._settings_changed)
        if not settings.TESTING:
            self._store = self._build_from_settings()   # fails startup on ContentError

    def _settings_changed(self, setting, **kwargs):
        if setting in ("CONTENT_DIR", "RELOAD_CONTENT", "DEBUG", "URL_PREFIX"):
            self._store = None
        if setting.startswith(("ASSISTANT_", "OLLAMA_")):
            self.reset_assistant()      # limits, gate and client are rebuilt from the new settings
