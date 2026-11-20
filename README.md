# Reading Modern Literary Chinese

Course materials for Cambridge learners reading 19th–20th century literary Chinese.
See [PLAN.md](PLAN.md) for the project plan and
[docs/content-spec.md](docs/content-spec.md) for the content format.

## Django, not Flask

The web app is **Django**. An earlier version was Flask (the `main` branch before the Django port); that
version is retired. Do not install Flask, do not run `app.py` or `flask run`, and do not add Flask code
or a Flask test run. Start the app with `python manage.py runserver` (development), Gunicorn on
`config.wsgi:application` or the container (production), and run the tests with `python manage.py test`.
If something complains that Flask is missing, you are on the wrong branch or an old image.

In production the app is served at https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/ (see
`MLC_URL_PREFIX` and [docs/deployment.md](docs/deployment.md)).

## Layout

| Folder | Contents |
|---|---|
| `content/` | The course: units, grammar points, toolkit pages |
| `docs/` | Specifications |
| `templates/` | Blank templates and a worked example passage |
| `app/`, `accounts/`, `config/` | The Django web app: pages and assistant, University sign-in and allowlist, settings |
| `deploy/` | Server configuration: Gunicorn, Caddy, systemd, settings template |
| `tools/` | Scripts: validator, glossary and font builders |
| `tests/` | Validator and app tests, and test fixtures |

## Running the web app

Requires Python 3.10+ and the packages in `requirements.txt` (`pip install -r requirements.txt`).

```bash
MLC_DEBUG=1 python manage.py runserver 5050
```

or, in a container (the repository is mounted and the server reloads on changes; the database
lives in `./var`):

```bash
docker compose -f docker-compose.dev.yml up --build     # then open http://localhost:5051/
```

`MLC_DEBUG=1` means no sign-in. Then open <http://localhost:5050/> (or port 5051 with Docker). For production, `docker compose up -d --build` runs the production image (see [docs/deployment.md](docs/deployment.md))
(Gunicorn behind Caddy, or a container; configuration files in `deploy/`). With `MLC_DEBUG=1` the app reloads the content when a file in
`content/` changes. The app will not start if the validator reports errors. See
[docs/app-plan.md](docs/app-plan.md) for the plan.

### Settings

Settings are read from environment variables starting with `MLC_` (lists are written as JSON).
For local development they can also go in `app/.env`, one `MLC_NAME=value` per line; the API key may
be given there as `Ollama_API=…`. Real environment variables win over the file. `.env` files are
ignored by git: never commit one. On the server, use `mlc.env` (see `docs/deployment.md`).

To use the cloud model locally, copy `app/.env.example` to `app/.env` and put your key in it. It holds:

```
Ollama_API=<key>
MLC_OLLAMA_HOST=https://ollama.com
MLC_ASSISTANT_MODEL=gemma4:31b
```


| Setting | Meaning |
|---|---|
| `MLC_AUTH_MODE` | `oidc` (Cambridge sign-in required) or `none` (no sign-in, for development). Default: `none` with `MLC_DEBUG=1`, otherwise `oidc` |
| `MLC_AZURE_CLIENT_ID`, `MLC_AZURE_CLIENT_SECRET`, `MLC_AZURE_TENANT_ID` | The Microsoft Entra ID app registered for this site (required with `oidc`). The tenant ID may differ from other Cambridge apps, because this site has its own registration |
| `MLC_SECRET_KEY` | A long random string that signs the session cookie (required with `oidc`) |
| `MLC_REVIEWERS` | CRSids allowed to switch on reviewer notes, e.g. `["cz201"]` |
| `MLC_DEV_USER` | With `none`, the user to act as, e.g. `cz201` to try reviewer mode |
| `MLC_SHOW_UNREVIEWED` | `false` at release: hide pages not yet reviewed (reviewers still see them) |
| `MLC_URL_PREFIX` | The path the site is served under, e.g. `/chinese-literary-reading` (on lcapps: https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/). The proxy strips it; the app adds it to every link, redirect, static URL and cookie path. Empty (the default): served at the root |
| `MLC_TRUST_PROXY` | `1` behind Caddy (**required** there: without it Django's CSRF origin check rejects sign-out and reviewer-mode posts, and the sign-in redirect address is wrong). Default `0` |
| `MLC_DB_PATH` | The SQLite file that holds the allowlist and admin accounts. Default `var/db.sqlite3` |
| `MLC_DEBUG` | `1` for development: Django debug mode, no sign-in by default, content reloads |
| `MLC_TESTING` | Tests only (the test suite sets it): never set it in production |
| `MLC_ASSISTANT_ENABLED` | `false` to switch the reading assistant off |
| `MLC_OLLAMA_HOST` | The AI model server: `http://localhost:11434` (local Ollama, the default) or `https://ollama.com` |
| `MLC_OLLAMA_API_KEY` | API key for the Ollama cloud service (kept on the server) |
| `MLC_ASSISTANT_MODEL` | The model: default `qwen3.5:9b` (local); `gemma4:31b` on the Ollama cloud service |
| `MLC_ASSISTANT_DAILY_LIMIT`, `MLC_ASSISTANT_HOURLY_LIMIT` | AI calls per user per day (default 40) and for everyone per hour (default 150) |
| `MLC_ASSISTANT_TIMEOUT`, `MLC_ASSISTANT_STEP_DEADLINE` | Seconds allowed for one model call (default 60) and for a whole step (default 90) |
| `MLC_ASSISTANT_MAX_CONCURRENT`, `MLC_ASSISTANT_QUEUE_WAIT` | Model calls at once for everyone (default 6), and seconds a request waits for a free slot before the page says the assistant is busy (default 20) |

The sign-in redirect URI to register in Microsoft Entra ID (platform Web) is
`https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/auth/sso/complete/azuread-tenant-oauth2/`; in production the operator adds it on
lcapps. Local development needs none, because `MLC_DEBUG=1` uses no sign-in.

**Allowlist.** Only people on the allowlist can sign in. Add entries at `/django-admin/` under
"Allowed logins": a CRSid (`abc123`), an exact address (`abc123@cam.ac.uk`) or `@cam.ac.uk` for every
Cambridge CRSid. Only Cambridge sign-ins (a CRSid before `@cam.ac.uk`) can ever be admitted; any other
address is refused whatever the list says. Removing an entry takes effect on that person's next request.
The database stores only the user name (the CRSid), the display name and an active flag, no email address.

**Admin login.** The Django admin at `https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/django-admin/`
is for the people who manage the site. It has its own sign-in, **an email address and a password**, and it is
**not** part of the Cambridge SSO: an SSO sign-in has no email address stored and never opens the admin.
Visitors who are not signed in to the admin see a landing page with a button to the admin login.

1. Create an admin: `python manage.py createsuperuser` (in Docker:
   `docker compose exec web python manage.py createsuperuser`; the deployment guide has the non-Docker
   command). Give it a user name (any), **an email address (required for the login)** and a password.
2. Sign in at `/django-admin/` with that email address and password, and add the allowlist entries.
3. More admins: under Users in the admin, add a user with an email address and a password and tick *Staff*
   (and *Superuser* for full access). Each email address must belong to one account only.

A University sign-in always creates (or reuses) a separate account with no email address, never an admin
one. In production, restrict `/django-admin/` to the addresses you manage it from in the Caddy site block
(`deploy/Caddyfile.example`, `remote_ip`).

To try reviewer mode locally:

```bash
MLC_DEBUG=1 MLC_DEV_USER=cz201 MLC_REVIEWERS='["cz201"]' python manage.py runserver 5050
```

To try the assistant's AI steps on a text from the command line (local Ollama by default):

```bash
python3 tools/try_assistant.py "日本人之稱我中國也，一則曰老大帝國"
```

The glossary (`content/glossary.md`) is generated from the passage gloss tables. After changing
glosses, regenerate it (a test fails if it is out of date):

```bash
python3 tools/build_glossary.py
```

The Chinese web font (`app/static/fonts/`) is Noto Serif CJK TC cut down to the characters the course
uses. If new passages add characters, rebuild it (a test lists missing characters):

```bash
python3 tools/build_font.py --source path/to/NotoSerifCJKtc-Regular.otf
```

Run all tests (validator, app and accessibility checks) with:

```bash
python3 -m unittest discover -s tests
```

`tests/test_browser.py` also opens every main page in a real browser, in light and dark mode at phone,
tablet and desktop widths, and checks for sideways scrolling, small tap targets, JavaScript errors and
(with axe-core) WCAG violations. It takes about two minutes and is skipped unless Playwright and Chromium
are installed: `pip install -r requirements-dev.txt && playwright install chromium`. For the axe check,
point `AXE_CORE_JS` at `axe.min.js` (`npm install axe-core`). See the top of the file for details.

## Checking content

```bash
python3 tools/validate.py
```

The command above checks `content/`. To check another folder, pass its path:

```bash
python3 tools/validate.py tests/fixtures/valid
```

Options:

- `--reviews`: list all `<!-- REVIEW(…): … -->` comments
- `--strict`: fail on warnings as well as errors
- `--quiet`: show errors only

Messages look like `path:line: error: message`. **Errors** break the spec and must
be fixed. **Warnings** point to things that are probably wrong but may be intended.

The validator reads the allowed values for `level`, `status`, `genre`, `rights`,
`default_view`, `source.punctuation` and gloss labels from section 2 of the spec, so a
new genre or label only needs adding there.

To find the right `#n` for an occurrence-specific gloss, list a term's numbered occurrences:

```bash
python3 tools/occurrences.py content/units/u05-the-noun-phrase/u05-p02-old-and-young.md 之
```

Run the validator's own tests with:

```bash
python3 -m unittest discover tests
```

## Editing in Obsidian

Content files must use standard Markdown links with relative paths, so the app can follow them.
In **Settings → Files and links**:

- **Use [[Wikilinks]]**: off
- **New link format**: Relative path to file

The validator flags any `[[wikilink]]` it finds.
