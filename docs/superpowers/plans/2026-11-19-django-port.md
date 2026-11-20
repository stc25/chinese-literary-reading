# Django Port with University SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Flask backend with Django, keeping every page, URL, template and the reading assistant as they are, and replace the generic OIDC sign-in with University of Cambridge SSO (Microsoft Entra ID) restricted by an admin-editable allowlist.

**Architecture:** A straight port. The framework-free code (`app/content/`, `app/tools.py`, `app/assistant/{client,limits,lookup,prompts,steps,evaluate}.py`, `tools/`) is not touched. Django renders the **existing Jinja templates** through its built-in Jinja2 backend, with a small `url_for` shim, so templates change only where Flask-specific. Sign-in uses `social-auth-app-django` with the `AzureADTenantOAuth2` backend, as the `academic-reading-eng` repo (`auth` branch) does. A new `accounts` app holds the allowlist model, the pipeline step that enforces it, and the sign-in middleware.

**Tech Stack:** Django 5.x, `social-auth-app-django`, WhiteNoise, Gunicorn (one process, many threads, unchanged), SQLite, Jinja2 (already a dependency of Flask; add it explicitly), the existing `unittest` tests run through `manage.py test`.

**Spec:** none separate. The design is the conversation of 2026-11-19 and the "Decisions" below; the behaviour to preserve is the current Flask app (`app/`), whose tests (`tests/test_app.py`, `tests/test_assistant.py`, `tests/test_accessibility.py`) are the acceptance suite.

## Decisions (from the user)

- Straight port of the existing app: no new features, no visual change.
- SSO: the same provider as the `academic-reading` apps (Microsoft Entra ID), with a **new** app registration made by the user; tenant ID, client ID and secret are supplied later. Production redirect URI, added by the user on lcapps: `https://<host>/auth/sso/complete/azuread-tenant-oauth2/`.
- An allowlist is required: only people matching an entry may sign in. Entry forms, as in `academic-reading-eng` `docs/LOGIN.md`: a bare CRSid (`abc123`), an exact email (`abc123@cam.ac.uk`), or a whole domain (`@ling.cam.ac.uk`). Managed in the Django admin.
- The `ALLOWED_DOMAINS` setting is dropped: the allowlist replaces it.

## Global Constraints

- Python 3.10+ (README floor); Docker image stays `python:3.12-slim`.
- Environment variables keep the `MLC_` prefix and the same names (`MLC_AUTH_MODE`, `MLC_SECRET_KEY`, `MLC_REVIEWERS`, `MLC_DEV_USER`, `MLC_SHOW_UNREVIEWED`, `MLC_TRUST_PROXY`, `MLC_ASSISTANT_*`, `MLC_OLLAMA_HOST`, `MLC_CONTENT_DIR`, `MLC_BIND`). `app/.env` keeps working, including the `Ollama_API` alias. Real environment variables win over the file. New: `MLC_AZURE_CLIENT_ID`, `MLC_AZURE_CLIENT_SECRET`, `MLC_AZURE_TENANT_ID` (required in `oidc` mode, no default: the user registers a new Entra app for this site, so the tenant ID may differ from `academic-reading-eng`), `MLC_DB_PATH`. `MLC_OIDC_*` and `MLC_ALLOWED_DOMAINS` are removed.
- `AUTH_MODE` is `oidc` (sign-in required) or `none` (no sign-in); default `none` when `DEBUG` or testing, otherwise `oidc`. Any other value stops startup.
- URL paths are unchanged (`/`, `/welcome`, `/units/<uid>`, `/units/<uid>/<num>`, `/grammar`, `/grammar/<gid>`, `/summaries.json`, `/toolkit`, `/toolkit/<tid>`, `/glossary`, `/review`, `/accessibility`, `/assistant/`, `/assistant/help`, `/assistant/api/<step>`, `/login`, `/auth/callback` becomes the social-auth completion URL, `/logout` (POST), `/signed-out`, `/reviewer-mode` (POST), `/healthz`). Django URL names keep the Flask endpoint names (`pages.unit`, `assistant.page`, `auth.login`, …) so templates and tests keep working.
- Response headers unchanged: the Content-Security-Policy string, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS in `oidc` mode, `Cache-Control: private, no-cache` on pages and `public` on `/static/`.
- The assistant's limits stay in memory, so deployment stays one Gunicorn process with threads (`deploy/gunicorn.conf.py` unchanged in spirit).
- The app refuses to start if the content validator reports errors (the Docker build runs `tools/validate.py --quiet`); in debug the content reloads when a file in `content/` changes.
- Sign-in stores only username (CRSid), display name and the allowlist-derived active flag; no email is saved. Update the welcome-page sentence if that stops being true.
- Commit after every task. Commit messages end with the attribution line from the session.

## Review Focus

- An allowlist entry deleted or an account deactivated while the person is signed in: they must be refused on their next request, not at session expiry (middleware re-checks the allowlist per request).
- Allowlist matching: `ABC123`, `abc123@CAM.AC.UK` and `@Ling.Cam.Ac.Uk` match entries case-insensitively; `abc123@gmail.com` does not match a bare CRSid entry; an entry of `@cam.ac.uk` does not match `x@evilcam.ac.uk` or `x@cam.ac.uk.evil.com`.
- Anonymous call to `/assistant/api/<step>` or `/summaries.json` in `oidc` mode: a 401/403 JSON response (not an HTML redirect body the script would try to parse); an anonymous page request redirects to `/login?next=<path>` with `next` limited to same-site paths (`//evil.com` and `https://evil.com` fall back to `/`).
- Identity token with no `preferred_username`/`upn`/`email` (only `sub`): refused with the sign-in error page, no user created.
- Invalid content at startup or after an edit in debug: the existing content-error behaviour (page lists the errors) is kept, and `/healthz` still answers.
- POST to `/logout`, `/reviewer-mode` or the assistant API without the CSRF token: 403, session untouched.

---

## File Structure

| Path | Responsibility |
|---|---|
| `manage.py` | Django entry point |
| `config/settings.py` | All settings, read from `MLC_*` env and `app/.env` (port of `create_app` config + `read_env_file`) |
| `config/envfile.py` | `read_env_file(path) -> dict` moved unchanged from `app/__init__.py` |
| `config/urls.py`, `config/wsgi.py` | Root URLconf (includes `app.urls`, `accounts.urls`, admin at `/django-admin/`); WSGI app. `wsgi.py` at the repo root imports `config.wsgi.application` |
| `app/apps.py`, `app/urls.py` | The course app (existing `app/` package becomes a Django app); URL names `pages.*`, `assistant.*`, `health` |
| `app/store.py` | `CourseStore` moved from `app/__init__.py` |
| `app/jinja.py` | Jinja2 environment factory: globals `url_for`, `csrf_token`, filters `first_index`, `passage_progress_item`; replaces Flask's context processors |
| `app/context.py` | Per-request template context (`course`, `md`, `md_inline`, `current_year`, `current_user`, `reviewer_mode`, `auth_mode`, `config`, `request`) |
| `app/middleware.py` | `SecurityHeadersMiddleware`, `CourseMiddleware` (attaches `request.course`, `request.content_error`) |
| `app/views.py` | Ported page views (same helper functions) |
| `app/assistant/views.py` | Ported assistant views (the Flask blueprint code from `app/assistant/__init__.py`) |
| `accounts/models.py` | `AllowedLogin(entry, note, created)` and `matches(identifiers) -> bool` |
| `accounts/pipeline.py` | `enforce_allowlist`, `finish_login` social-auth pipeline steps |
| `accounts/middleware.py` | `RequireSignInMiddleware`: gate, allowlist re-check, dev-user in `none` mode |
| `accounts/views.py`, `accounts/urls.py` | `login`, `logout`, `signed_out`, `toggle_reviewer_mode`, `signin_error` |
| `accounts/admin.py` | Admin for `AllowedLogin` |
| `tests/` | Existing tests ported to Django's test client; new `tests/test_accounts.py` |

---

### Task 1: Branch, baseline and Django scaffold

**Files:**
- Create: `manage.py`, `config/__init__.py`, `config/settings.py`, `config/envfile.py`, `config/urls.py`, `config/wsgi.py`, `app/apps.py`
- Modify: `requirements.txt`, `wsgi.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `config.envfile.read_env_file(path: Path) -> dict` (same behaviour as today's function in `app/__init__.py:54`); a settings module exposing `MLC` values as Django settings named without prefix (`AUTH_MODE`, `CONTENT_DIR`, `SHOW_UNREVIEWED`, `REVIEWERS`, `DEV_USER`, `ASSISTANT_*`, `OLLAMA_HOST`, `OLLAMA_API_KEY`, `ACCESSIBILITY_CONTACT`, `TRUST_PROXY`).

- [ ] **Step 1:** Done before execution: the UI work is stashed (`git stash list`, "ui-refresh WIP before django port") and the branch `django-port` exists, cut from `ui-refresh`. `Dockerfile` and `docker-compose.dev.yml` stay in the working tree and are committed with this task. Run `python -m unittest discover -s tests` and record the pass count in the PR description as the baseline.
- [ ] **Step 2: Write the failing tests** in `tests/test_settings.py`: `read_env_file` returns `{"OLLAMA_API_KEY": "k"}` for a file containing `Ollama_API=k`, parses `MLC_REVIEWERS=["cz201"]` to a list, ignores comments and a missing file; settings with `MLC_AUTH_MODE=banana` raise `ImproperlyConfigured`; with `DEBUG` and no `MLC_AUTH_MODE`, `AUTH_MODE == "none"`; `oidc` with an empty `SECRET_KEY`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` or `AZURE_TENANT_ID` raises `ImproperlyConfigured` naming the missing setting.
- [ ] **Step 3: Run** `python manage.py test tests.test_settings` and expect failures (module missing).
- [ ] **Step 4: Implement** the scaffold. Add `Django>=5.0,<6`, `social-auth-app-django>=5.4`, `whitenoise>=6.6`, `jinja2>=3.1` to `requirements.txt`; remove `flask` and `authlib` only in Task 9. Settings read order: defaults → `app/.env` (unless testing) → real environment (`MLC_*`, JSON-parsed where possible) → `MLC_` overrides from tests via `override_settings`. Move `read_env_file` and `ENV_ALIASES` verbatim. `DATABASES` is SQLite at `MLC_DB_PATH` (default `<repo>/var/db.sqlite3`). `SESSION_ENGINE` is `signed_cookies`, lifetime 12 h, `SameSite=Lax`, `HttpOnly`, `Secure` in `oidc` mode. `CSRF_HEADER_NAME = "HTTP_X_CSRF_TOKEN"` so the existing `assistant.js` header keeps working. `DATA_UPLOAD_MAX_MEMORY_SIZE = 256*1024`.
- [ ] **Step 5: Run** the same tests; expect PASS. Run `python manage.py check`.
- [ ] **Step 6: Commit** `git commit -m "Django scaffold: settings from MLC_ env and app/.env"`.

### Task 2: Jinja2 templates under Django

**Files:**
- Create: `app/jinja.py`, `app/context.py`
- Modify: `config/settings.py` (`TEMPLATES`), `app/templates/base.html`, `app/templates/assistant.html` (Flask-specific lines only)
- Test: `tests/test_templates.py`

**Interfaces:**
- Consumes: settings from Task 1.
- Produces: `app.jinja.environment(**options) -> jinja2.Environment` with globals `url_for(name: str, **kwargs) -> str` (name `"static"` takes `filename=` and returns `STATIC_URL + filename`; other kwargs not in the URL pattern become a query string; name resolved with `django.urls.reverse`), `csrf_token() -> str`; filters `first_index`, `passage_progress_item`. `app.context.template_context(request) -> dict` with the keys `course, md, md_inline, current_year, current_user, reviewer_mode, auth_mode, config, request, content_error`. Templates read `request.endpoint`, so provide `request.endpoint` as the Django URL name (set by `CourseMiddleware` from `resolve(request.path_info).view_name`).

- [ ] **Step 1: Write the failing tests:** `url_for("pages.unit", uid="u01")` returns `/units/u01` after a stub URLconf registers it; `url_for("static", filename="css/site.css")` returns `/static/css/site.css`; an unused kwarg `next="/x"` is appended as `?next=%2Fx`; rendering `404.html` with a fake request and context does not raise.
- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** `app/jinja.py` and `app/context.py`; configure `TEMPLATES` with `django.template.backends.jinja2.Jinja2`, `DIRS=[app/templates]`, `OPTIONS={"environment": "app.jinja.environment", "context_processors": ["app.context.template_context"]}`. In `base.html` and `assistant.html` change only what needs it: `csrf_token()` stays as a callable; the logout, reviewer and next-link forms keep their `name="csrf"` hidden field replaced by Django's `csrfmiddlewaretoken` (field name changes in the matching view in Task 6); `config.ASSISTANT_ENABLED` resolves to `settings`.
- [ ] **Step 4: Run** and expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Render the existing Jinja templates through Django"`.

### Task 3: Course store, middleware, headers, health

**Files:**
- Create: `app/store.py`, `app/middleware.py`, `app/urls.py` (health only for now)
- Modify: `config/urls.py`, `config/settings.py` (`MIDDLEWARE`)
- Test: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `app.content.load`, `app.content.ContentError`, `app.content.content_signature` (unchanged).
- Produces: `app.store.CourseStore(root: Path, reload: bool)` with `.current()`, `.course`, `.error` (moved unchanged); `request.course`, `request.content_error` set by `CourseMiddleware`; the store lives on `app.apps.AppConfig.store` (built in `ready()`, fails startup on `ContentError` exactly as today).

- [ ] **Step 1: Write failing tests** (port from `tests/test_app.py` the headers, cache-control, healthz and reload tests, unchanged in assertions): `GET /healthz` is `{"status": "ok"}`; every response carries the six headers with the exact CSP string; `/static/…` is `public`, pages are `private, no-cache`; HSTS only when `AUTH_MODE == "oidc"`; with a temp content dir edited after start and `DEBUG`, the next request sees the change; broken content at start raises `ContentError`.
- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** by moving `CourseStore` verbatim and writing `SecurityHeadersMiddleware` and `CourseMiddleware`. WhiteNoise serves `/static/` from `app/static` (`WHITENOISE_USE_FINDERS` in debug).
- [ ] **Step 4: Run** and expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Course store, security headers and health check under Django"`.

### Task 4: Port the course pages

**Files:**
- Create: `app/views.py` (rewrite of the Flask module), extend `app/urls.py`
- Modify: `tests/test_app.py` (client setup only), `tests/test_accessibility.py` (client setup only)
- Test: the two existing files, with `make_app()` replaced by a helper returning Django's `Client` under `override_settings(CONTENT_DIR=..., AUTH_MODE="none", ...)`

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces: views named exactly as the Flask endpoints (`course_map, welcome, unit, passage, grammar_index, grammar, summaries, toolkit_index, toolkit, glossary, review_list, accessibility`) registered under URL names `pages.<name>`; a `handler404` rendering `404.html` with status 404. Keep the helpers (`visible`, `get_or_404`, `ref_url`, `ref_title`, `gloss_data`, `passages_before`, `date_converter`, `glossary_entries`, `strip_html`, `page_url`) with unchanged signatures; `get_or_404` raises `Http404`.

- [ ] **Step 1:** Change only the test harness in `tests/test_app.py` and `tests/test_accessibility.py` (the `make_app` helper and `app.test_client()` calls) so they target the Django client; assertions stay as they are. Add `override_settings` for `SHOW_UNREVIEWED`, `REVIEWERS`, `DEV_USER`.
- [ ] **Step 2: Run** `python manage.py test tests.test_app tests.test_accessibility` and expect FAIL (no views).
- [ ] **Step 3: Implement** the views by translating each Flask function: `render_template(...)` becomes `django.shortcuts.render(request, template, ctx)`; `g.course` becomes `request.course`; `abort(404)` becomes `raise Http404`; `jsonify` becomes `JsonResponse`. `review_list` is guarded by `reviewer_required`, ported in Task 6 (stub it with a pass-through until then and mark the dependent tests expected-failing only in this task's commit).
- [ ] **Step 4: Run** the same tests; expect PASS except the sign-in-dependent ones, which Task 6 turns green.
- [ ] **Step 5: Commit** `git commit -m "Port the course pages to Django views"`.

### Task 5: Accounts: allowlist model and matching

**Files:**
- Create: `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py`, `accounts/migrations/0001_initial.py`
- Test: `tests/test_accounts.py`

**Interfaces:**
- Produces: `AllowedLogin(entry: CharField(unique, stored lower-cased and stripped), note: CharField(blank), created: DateTimeField(auto_now_add))` with validation of the three entry forms (`^[a-z0-9]+$` CRSid, `^[^@\s]+@[^@\s]+$` email, `^@[^@\s]+$` domain); `AllowedLogin.objects.allows(email: str, crsid: str) -> bool` (case-insensitive; domain entries match the exact domain after the last `@`, no suffix matching; a CRSid entry matches only when `email` ends in `@cam.ac.uk`).

- [ ] **Step 1: Write the failing tests** covering every line of the allowlist-matching Review Focus bullet, plus: saving `" ABC123 "` stores `abc123`; saving `a b` or `` raises `ValidationError`.
- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement** the model, a custom manager `allows`, `clean()`, and an admin with search on `entry`.
- [ ] **Step 4: Run** and expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Allowlist model for sign-in"`.

### Task 6: SSO sign-in, gate, logout, reviewer mode, landing page

**Files:**
- Create: `accounts/pipeline.py`, `accounts/middleware.py`, `accounts/views.py`, `accounts/urls.py`
- Modify: `config/settings.py` (`INSTALLED_APPS`, `AUTHENTICATION_BACKENDS`, `SOCIAL_AUTH_*`, `MIDDLEWARE`, `LOGIN_URL`), `config/urls.py`, `app/templates/welcome.html`, `app/templates/signin_error.html`, `app/templates/signed_out.html`, `app/templates/base.html`
- Test: `tests/test_accounts.py` (extend)

**Interfaces:**
- Consumes: `AllowedLogin.objects.allows`, `app.context.template_context` (Task 2).
- Produces: `accounts.pipeline.enforce_allowlist(backend, details, response, *a, **kw)` raising `social_core.exceptions.AuthForbidden` unless `allows(email, crsid)`; `crsid` is the part before `@` of `preferred_username`, falling back to `upn`, `email`, never `sub` (no identifier → `AuthForbidden`). `finish_login(backend, user, *a, **kw)` stores display name only and sets the unusable password. URL names `auth.login` (GET `/login`, begins `social:begin` with `azuread-tenant-oauth2`, keeps `next` via `safe_next`), `auth.logout` (POST), `auth.signed_out`, `auth.toggle_reviewer_mode` (POST, 404 unless reviewer), `auth.callback` aliasing the social completion URL. `request.user_info -> {"id": str, "name": str, "reviewer": bool}` set by `RequireSignInMiddleware`, which in `none` mode yields `DEV_USER` as reviewer iff in `REVIEWERS`. `safe_next(url: str | None) -> str` ported verbatim. `reviewer_required` decorator ported.

- [ ] **Step 1: Write the failing tests:** port the sign-in tests in `tests/test_app.py` (anonymous redirect to `/login?next=…`, open endpoints, `next` sanitising, reviewer toggle 404 for non-reviewers, logout needs CSRF) and add one test per remaining Review Focus bullet: allowlist entry deleted mid-session → next request redirected to the sign-in page; deactivated user likewise; anonymous API calls under `/assistant/api/` and `/summaries.json` get a 401 JSON `{"error": "sign-in required"}`; token without identifier → error page, `User.objects.count() == 0`; non-allowlisted SSO result → 403 error page, no user; mock the Microsoft exchange by calling the pipeline functions directly with a fake `response` dict (do not call the network).
- [ ] **Step 2: Run** and expect FAIL.
- [ ] **Step 3: Implement.** Settings: `AUTHENTICATION_BACKENDS = ["social_core.backends.azuread_tenant.AzureADTenantOAuth2", "django.contrib.auth.backends.ModelBackend"]`; the pipeline is the one in `academic-reading-eng` `settings.py` (`social_details, social_uid, auth_allowed, accounts.pipeline.enforce_allowlist, social_user, get_username, create_user, associate_user, load_extra_data, user_details, accounts.pipeline.finish_login`), without `associate_by_email`; `SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL = False`; client id/secret/tenant from `MLC_AZURE_*`; `SOCIAL_AUTH_LOGIN_ERROR_URL = "/signin-error"` rendering `signin_error.html`. Middleware order: after `SessionMiddleware`/`AuthenticationMiddleware`, before views. Open paths: `/login`, `/auth/`, `/signed-out`, `/signin-error`, `/static/`, `/healthz`, `/accessibility`, `/`, `/welcome`, `/django-admin/` (the admin has its own login for superusers). In `welcome.html` the sign-in button uses `url_for('auth.login')` as now; the privacy sentence says the site stores only the user name and display name. `base.html`: forms use `csrfmiddlewaretoken`.
- [ ] **Step 4: Run** `python manage.py test tests.test_accounts tests.test_app tests.test_accessibility`; expect PASS, including the tests deferred from Task 4.
- [ ] **Step 5: Commit** `git commit -m "University SSO with an allowlist; sign-in gate and landing page"`.

### Task 7: Port the reading assistant

**Files:**
- Create: `app/assistant/views.py`
- Modify: `app/assistant/__init__.py` (remove Flask; keep only package docstring and re-exports of the framework-free helpers `Limits`, etc. that tests import), `app/urls.py`, `tests/test_assistant.py` (harness only)
- Test: `tests/test_assistant.py`

**Interfaces:**
- Consumes: `request.course`, `request.user_info["id"]` as the limit key, `get_limits() / get_gate() / get_client()` (same shared-singleton pattern, stored on the AppConfig instead of `current_app.extensions`).
- Produces: URL names `assistant.page` (`/assistant/`, GET and POST), `assistant.help` (`/assistant/help`), `assistant.api` (`/assistant/api/<step>`, POST, JSON). The API checks Django's CSRF through the `X-CSRF-Token` header (already configured), so `session["csrf"]` and `auth.csrf_token` disappear; `check_command` (`flask assistant-check`) becomes `python manage.py assistant_check`.

- [ ] **Step 1:** Change only the harness in `tests/test_assistant.py`; keep every assertion (limits, refunds, busy gate, deadline, step outputs, CSRF failure 403, disabled assistant 404).
- [ ] **Step 2: Run** `python manage.py test tests.test_assistant` and expect FAIL.
- [ ] **Step 3: Implement** by translating the blueprint code: `request.form.get` stays similar (`request.POST.get`), `request.get_json` becomes `json.loads(request.body)` in a try block, `jsonify` becomes `JsonResponse`, `current_app.config` becomes `django.conf.settings`, `current_app.logger` becomes `logging.getLogger("app.assistant")`. Add `app/management/commands/assistant_check.py` from the existing `check_command`.
- [ ] **Step 4: Run** and expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Port the reading assistant to Django"`.

### Task 8: Docker, deployment and docs

**Files:**
- Modify: `Dockerfile`, `docker-compose.dev.yml`, `deploy/gunicorn.conf.py`, `deploy/mlc.env.example`, `deploy/mlc.service`, `app/.env.example`, `README.md`, `docs/deployment.md`, `requirements.txt`, `wsgi.py`, `tests/test_browser.py` (server start-up only)
- Create: `docker/entrypoint.sh`
- Test: build and run

**Interfaces:**
- Produces: image entrypoint running `python manage.py migrate --noinput` then Gunicorn (`wsgi:application`, `workers=1`, `gthread`, 16 threads; comment in `gunicorn.conf.py` unchanged); dev stage runs `python manage.py runserver 0.0.0.0:5050`; the SQLite file on a volume (`/srv/mlc/var`) so the allowlist survives restarts.

- [ ] **Step 1:** Update the Dockerfile (keep the `tools/validate.py --quiet` build gate, add `python manage.py collectstatic --noinput` in the `prod` stage), the compose file (volume `./var:/srv/mlc/var`, port mapping unchanged) and the env examples with `MLC_AZURE_*`, `MLC_DB_PATH`; remove the `MLC_OIDC_*` and `MLC_ALLOWED_DOMAINS` rows from the README table and add "Allowlist: create the first admin with `python manage.py createsuperuser`, then add entries at `/django-admin/`". In `docs/deployment.md` add the Entra registration step (Web platform, redirect URI above) and the rollback note.
- [ ] **Step 2: Verify:** `docker compose -f docker-compose.dev.yml up --build -d`, then `curl -s -o /dev/null -w "%{http_code}" http://localhost:5051/healthz` returns `200` and `/` returns the course map in dev mode. `docker build -t mlc .` succeeds, and `docker run --rm -e MLC_AUTH_MODE=oidc mlc` exits with a message naming the missing `MLC_SECRET_KEY`.
- [ ] **Step 3: Commit** `git commit -m "Deploy the Django app: Docker, entrypoint, env and docs"`.

### Task 9: Remove Flask and final check

**Files:**
- Modify: `requirements.txt` (drop `flask`, `authlib`), delete `app/auth.py`, the old `create_app`/`CourseStore` code in `app/__init__.py`, `deploy/mlc.service` if it mentions Flask
- Test: whole suite

- [ ] **Step 1:** `grep -rn "flask\|Flask\|authlib" --include=*.py --include=*.txt --include=*.md --include=*.html . | grep -v ".venv"` returns only historical mentions in `docs/` (update or delete them).
- [ ] **Step 2: Verify:** `python manage.py test` all pass, count at least the baseline from Task 1 plus the new tests; `python manage.py check --deploy` with oidc settings reports no errors; `python tools/validate.py --quiet` passes; `playwright install chromium && python manage.py test tests.test_browser` passes against the dev server.
- [ ] **Step 3: Manual SSO check** with the real Entra registration once the user has one: allowlisted CRSid signs in and sees the course; a non-allowlisted Cambridge account gets the refusal page; removing the entry in `/django-admin/` blocks the already signed-in session on its next click.
- [ ] **Step 4: Commit** `git commit -m "Remove Flask; Django is the only backend"`.

---

## Self-review notes

- Spec coverage: every decision in "Decisions" maps to a task (port: 1–4, 7; SSO: 6; allowlist: 5–6; same provider: 6 and 8).
- Names used across tasks match their Interfaces blocks (`allows`, `request.user_info`, `request.course`, `url_for`, URL names `pages.*`, `assistant.*`, `auth.*`).
- Open risk: Django's Jinja2 backend and Jinja `{% call %}`/`{% from … import %}` with context. The templates use `{% from %}` and `{% macro %}` only, so there is no `call`. If a macro needs `request`, pass it explicitly.
