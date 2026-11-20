"""Django settings, built from defaults, app/.env and MLC_* environment variables.

Order: defaults, then app/.env (not when testing), then the real environment (MLC_NAME,
JSON-parsed where possible), so the real environment wins over the file.
"""
import json
import os
import re
import secrets
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .envfile import read_env_file

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / "app" / ".env"
AUTH_MODES = ("oidc", "none")
OIDC_REQUIRED = ("SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")
MIN_SECRET_LENGTH = 32
PASSWORD_VALIDATORS = [   # the admin's password logins (createsuperuser, changepassword, the admin form)
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# University SSO (Microsoft Entra ID) through python-social-auth, as in academic-reading-eng.
# The allowlist check runs before any user or social-auth row is created; associate_by_email is
# deliberately absent (an address never links an identity to an existing account).
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "accounts.pipeline.enforce_allowlist",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "accounts.pipeline.finish_login",
)

DEFAULTS = {
    "CONTENT_DIR": str(REPO / "content"),
    "SHOW_UNREVIEWED": True,     # False at release: hide pages below `reviewed` (reviewers still see them)
    "REVIEWERS": [],
    "DEV_USER": "dev",
    "TRUST_PROXY": 0,
    "ACCESSIBILITY_CONTACT": "",
    "ASSISTANT_ENABLED": True,
    "ASSISTANT_MAX_CHARS": 600,
    "ASSISTANT_MODEL": "qwen3.5:9b",
    "ASSISTANT_TIMEOUT": 60,           # seconds for one model call
    "ASSISTANT_STEP_DEADLINE": 90,     # seconds for a whole step (the words step may make several calls)
    "ASSISTANT_MAX_CONCURRENT": 6,     # model calls at once, for everyone together
    "ASSISTANT_QUEUE_WAIT": 20,        # seconds a request waits for a free slot before "busy"
    "ASSISTANT_DAILY_LIMIT": 40,       # AI calls per user per day (one full analysis is 5, each question 1)
    "ASSISTANT_HOURLY_LIMIT": 150,     # AI calls per hour for everyone together
    "OLLAMA_HOST": "http://localhost:11434",   # the cloud service: https://ollama.com
    "OLLAMA_API_KEY": "",                      # cloud only; kept on the server
    "DB_PATH": str(REPO / "var" / "db.sqlite3"),
    "URL_PREFIX": "",                  # the path the site is served under, e.g. /chinese-literary-reading
    "RELOAD_CONTENT": None,            # None: reload content files when DEBUG is on
}


def logging_config(testing: bool) -> dict:
    """Everything at WARNING and above to stderr (journald / docker logs), with the app's own INFO.
    Django's default only prints django.request errors when DEBUG is on; here `django` has no
    handler of its own and propagates to the root one, so unhandled 500s are logged in production."""
    handler = {"class": "logging.StreamHandler", "stream": "ext://sys.stderr", "formatter": "plain"}
    if testing:
        handler["level"] = "CRITICAL"   # pristine test output; tests that need the output lower it
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"stderr": handler},
        "root": {"handlers": ["stderr"], "level": "WARNING"},
        "loggers": {
            "django": {"handlers": [], "level": "INFO", "propagate": True},
            "app": {"level": "INFO"},
            "accounts": {"level": "INFO"},
        },
    }


def build_settings(env: dict, debug: bool, testing: bool) -> dict:
    """Django settings from `env` (unprefixed MLC names). Raises ImproperlyConfigured."""
    values = {**DEFAULTS, **env}
    mode = values.get("AUTH_MODE") or ("none" if (debug or testing) else "oidc")
    if mode not in AUTH_MODES:
        raise ImproperlyConfigured(f"MLC_AUTH_MODE must be one of {AUTH_MODES}, not {mode!r}")
    secret = values.get("SECRET_KEY") or ""
    tenant = str(values.get("AZURE_TENANT_ID") or "")
    if mode == "oidc":
        for name in OIDC_REQUIRED:
            if not values.get(name):
                raise ImproperlyConfigured(f"MLC_{name} is required when MLC_AUTH_MODE is oidc")
        secret = str(secret)
        if len(secret) < MIN_SECRET_LENGTH or secret == "dev" or secret.startswith("<"):
            raise ImproperlyConfigured(
                f"MLC_SECRET_KEY must be a long random string (at least {MIN_SECRET_LENGTH} characters, "
                "e.g. python3 -c 'import secrets; print(secrets.token_hex(32))'), not a placeholder")
        try:
            # A tenant GUID: "common" or "organizations" would turn off social-core's tenant (tid) check.
            tenant = str(uuid.UUID(tenant))
        except ValueError:
            raise ImproperlyConfigured(
                "MLC_AZURE_TENANT_ID must be the tenant's ID (a GUID such as "
                "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx), not a name or 'common'") from None
    elif not secret:
        secret = secrets.token_hex(32)   # development only: sessions end when the app restarts

    prefix = parse_url_prefix(values.get("URL_PREFIX"))

    reload_content = values.get("RELOAD_CONTENT")
    if reload_content is not None and reload_content != "":
        reload_content = parse_bool(reload_content, "RELOAD_CONTENT")
    else:
        reload_content = None    # reload content files when DEBUG is on

    s = {k: v for k, v in values.items() if k not in ("SECRET_KEY", "DB_PATH", "AUTH_MODE", "URL_PREFIX")}
    s.update(
        DEBUG=debug,
        SECRET_KEY=str(secret),
        AUTH_MODE=mode,
        AZURE_CLIENT_ID=str(values.get("AZURE_CLIENT_ID") or ""),
        AZURE_CLIENT_SECRET=str(values.get("AZURE_CLIENT_SECRET") or ""),
        AZURE_TENANT_ID=tenant,
        ALLOWED_HOSTS=["*"],   # the reverse proxy decides the host
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
            "social_django",
            "app.apps.MlcConfig",
            "accounts",
        ],
        MIDDLEWARE=[
            "app.middleware.SecurityHeadersMiddleware",   # outermost: also covers static responses
            "whitenoise.middleware.WhiteNoiseMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "accounts.middleware.RequireSignInMiddleware",
            "accounts.middleware.SignInErrorMiddleware",
            "app.middleware.CourseMiddleware",
        ],
        TEMPLATES=[{
            "BACKEND": "django.template.backends.jinja2.Jinja2",
            "DIRS": [str(REPO / "app" / "templates")],
            "OPTIONS": {
                "environment": "app.jinja.environment",
                "context_processors": ["app.context.template_context"],
            },
        }, {
            # Only for the Django admin's own templates; the site's pages are Jinja2.
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        }],
        AUTHENTICATION_BACKENDS=[
            "social_core.backends.azuread_tenant.AzureADTenantOAuth2",
            "django.contrib.auth.backends.ModelBackend",   # the admin's own password login (superusers)
        ],
        AUTH_PASSWORD_VALIDATORS=PASSWORD_VALIDATORS,
        RELOAD_CONTENT=reload_content,
        LOGIN_URL="auth.login",
        URL_PREFIX=prefix,
        FORCE_SCRIPT_NAME=prefix or None,     # reverse() and redirects include the prefix; the proxy strips it
        LOGIN_REDIRECT_URL=prefix + "/",
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY=str(values.get("AZURE_CLIENT_ID") or ""),
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET=str(values.get("AZURE_CLIENT_SECRET") or ""),
        SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID=tenant,
        SOCIAL_AUTH_PIPELINE=SOCIAL_AUTH_PIPELINE,
        SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL=False,
        SOCIAL_AUTH_USER_FIELDS=["username"],          # create_user never copies the address
        SOCIAL_AUTH_RAISE_EXCEPTIONS=False,
        SOCIAL_AUTH_LOGIN_ERROR_URL=prefix + "/signin-error",
        SOCIAL_AUTH_LOGIN_REDIRECT_URL=prefix + "/",
        SOCIAL_AUTH_REDIRECT_IS_HTTPS=(mode == "oidc"),   # the redirect URI registered in Entra is https
        TESTING=testing,
        STATIC_URL=prefix + "/static/",
        STATICFILES_DIRS=[str(REPO / "app" / "static")],
        WHITENOISE_USE_FINDERS=debug or testing,           # production serves the collected files
        ROOT_URLCONF="config.urls",
        WSGI_APPLICATION="config.wsgi.application",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": values["DB_PATH"]}},
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
        # Other apps share the host (lcapps): own cookie names, and cookies only under this site's path.
        SESSION_COOKIE_NAME="mlc_session",
        SESSION_COOKIE_PATH=prefix or "/",
        CSRF_COOKIE_NAME="mlc_csrf",
        CSRF_COOKIE_PATH=prefix or "/",
        SESSION_COOKIE_AGE=int(timedelta(hours=12).total_seconds()),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=(mode == "oidc"),
        CSRF_COOKIE_SECURE=(mode == "oidc"),
        CSRF_HEADER_NAME="HTTP_X_CSRF_TOKEN",   # the header the existing assistant.js sends
        DATA_UPLOAD_MAX_MEMORY_SIZE=256 * 1024,  # pasted texts are at most a few KB
        LOGGING=logging_config(testing),
    )
    if int(values.get("TRUST_PROXY") or 0):
        # Behind the reverse proxy (MLC_TRUST_PROXY): take the scheme and host it reports, so the
        # SSO redirect URI and the CSRF origin check see https://<public host>.
        s["SECURE_PROXY_SSL_HEADER"] = ("HTTP_X_FORWARDED_PROTO", "https")
        s["USE_X_FORWARDED_HOST"] = True
    if not (debug or testing):
        s["STATIC_ROOT"] = str(REPO / "var" / "static")   # `manage.py collectstatic` target
    return s


def parse_url_prefix(value) -> str:
    """MLC_URL_PREFIX: "" (served at the root) or a path such as /chinese-literary-reading."""
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    if not re.fullmatch(r"/[A-Za-z0-9._~-]+(/[A-Za-z0-9._~-]+)*", text):
        raise ImproperlyConfigured(
            f"MLC_URL_PREFIX must look like /chinese-literary-reading (a path, no spaces), not {value!r}")
    return text


def parse_bool(value, name: str) -> bool:
    """Strict boolean for MLC_DEBUG and MLC_TESTING: anything unrecognised is an error."""
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off", ""):
        return False
    raise ImproperlyConfigured(f"MLC_{name} must be true or false, not {value!r}")


def is_testing(argv: list, env: dict) -> bool:
    """Explicit and narrow: `manage.py test`, or MLC_TESTING set (tests/__init__.py does that)."""
    return argv[1:2] == ["test"] or parse_bool(env.get("MLC_TESTING", ""), "TESTING")


def _environment(environ) -> dict:
    out = {}
    for key, value in environ.items():
        if key.startswith("MLC_"):
            try:
                out[key[4:]] = json.loads(value)
            except ValueError:
                out[key[4:]] = value
    return out


def merge_env(file_env: dict, environ: dict, testing: bool) -> dict:
    """Settings from app/.env (ignored when testing) overlaid by the real MLC_* environment, which wins."""
    merged = {} if testing else dict(file_env)
    merged.update(_environment(environ))
    return merged


_TESTING = is_testing(sys.argv, os.environ)
_env = merge_env({} if _TESTING else read_env_file(ENV_FILE), os.environ, _TESTING)
_env.pop("TESTING", None)
_debug = parse_bool(_env.pop("DEBUG", False), "DEBUG")
globals().update(build_settings(_env, debug=_debug, testing=_TESTING))

# The SQLite file's folder (var/ by default) must exist before the first connection: `manage.py check`
# connects too, for the social-auth tables' JSON field.
try:
    Path(DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
