# Deploying the course app

Draft v0.1 · 2026-11-08

How to run "Reading Modern Literary Chinese" on a Language Centre server. The app is a small Django
application: it reads the Markdown in `content/` at start-up, keeps it in memory and serves pages. A
small SQLite database (`var/db.sqlite3`) holds the sign-in **allowlist** and admin accounts. It stores
only each signed-in person's CRSid, display name and active flag: no email address.

## What you need

- A Linux server (any current distribution) with Python 3.11 or later, nginx and a TLS certificate
  for the chosen host name, e.g. `course.langcen.cam.ac.uk`.
- About 200 MB of disk and 256 MB of memory.
- A new **Microsoft Entra ID** app registration for this site (University sign-in), as for the other
  Language Centre apps:
  - platform: **Web**;
  - redirect URI: `https://<host>/auth/sso/complete/azuread-tenant-oauth2/` (the operator adds it on
    lcapps in production; local development needs none, because it uses no sign-in);
  - accounts: University of Cambridge only (single tenant);
  - permissions: `openid`, `profile`, `email` (sign-in only);
  - a client secret.

  You receive a **tenant ID**, a **client ID** and a **client secret**. The tenant ID may differ from
  the other apps', because this is a new registration.

## Install

```bash
sudo useradd --system --home /srv/mlc --shell /usr/sbin/nologin mlc
sudo git clone <repository> /srv/mlc
cd /srv/mlc
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo .venv/bin/python tools/validate.py --quiet        # must report 0 errors
sudo chown -R root:mlc /srv/mlc
sudo install -d -o mlc -g mlc /srv/mlc/var             # SQLite database and collected static files
```

## Configure

```bash
sudo mkdir -p /etc/mlc
sudo install -m 600 -o mlc deploy/mlc.env.example /etc/mlc/mlc.env
sudo nano /etc/mlc/mlc.env
```

Fill in `MLC_AZURE_TENANT_ID`, `MLC_AZURE_CLIENT_ID`, `MLC_AZURE_CLIENT_SECRET`, a new `MLC_SECRET_KEY`,
the reviewers' CRSids and the Ollama API key. Keep `MLC_TRUST_PROXY=1`: it is **required** behind
nginx with TLS, otherwise Django's CSRF origin check rejects the sign-out and reviewer-mode posts. All settings are listed in the
[README](../README.md#settings).

## Run

The app runs under Gunicorn (`config.wsgi:application`), managed by systemd, behind nginx. The unit
runs `manage.py migrate` and `manage.py collectstatic` before each start:

```bash
sudo cp deploy/mlc.service /etc/systemd/system/mlc.service
sudo systemctl daemon-reload
sudo systemctl enable --now mlc
sudo systemctl status mlc

sudo -u mlc bash -c 'set -a; . /etc/mlc/mlc.env; cd /srv/mlc && .venv/bin/python manage.py createsuperuser'   # first admin

sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/mlc   # then edit host name and certificates
sudo ln -s /etc/nginx/sites-available/mlc /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Check:

```bash
curl -s https://<host>/healthz          # {"status": "ok"}
```

Check the reading assistant's model settings with one short request:

```bash
sudo -u mlc bash -c 'set -a; . /etc/mlc/mlc.env; cd /srv/mlc && .venv/bin/python manage.py assistant_check'
# Model gemma4:31b at https://ollama.com; API key set.
# OK: answered in 0.6 s (334 tokens): To learn and then practise it from time to time.
```

If it fails, the log line above the error gives the service's answer: a wrong key (401), or a model
not covered by the plan (402).

### The allowlist and the first admin

Only people on the allowlist can sign in. Create the first admin as above, then open
`https://<host>/django-admin/` and add allowlist entries in one of three forms: a CRSid (`abc123`), an
exact address (`abc123@cam.ac.uk`) or a whole domain (`@ling.cam.ac.uk`). Matching ignores case.
Removing an entry, or deactivating an account, takes effect on that person's next request.

An account that signs in through SSO becomes SSO-only: its password is made unusable at its first SSO
sign-in. Sign in to `/django-admin/` with the password **before** using SSO with that account, or use
a separate admin account.

Then open `https://<host>/`: you should see the landing page and, after signing in with a University
account on the allowlist, the course map.

nginx serves the static files (CSS, JavaScript, the font) from `/srv/mlc/var/static/`, collected by
`python manage.py collectstatic` (the systemd unit and the container do it at start; Gunicorn's own
WhiteNoise would also serve them), and compresses responses; Gunicorn serves the pages. The nginx
site **overwrites** `X-Forwarded-Proto`, `X-Forwarded-Host` and `Host` with its own values (never
appends to what the client sent): Django trusts them for the sign-in redirect URI and the CSRF check. If the content has validation errors, Gunicorn refuses to start and the journal
(`journalctl -u mlc`) lists them.

### The reading assistant under load

The app runs as **one Gunicorn process with 16 threads**. The assistant's usage limits are counted
in memory, so they are exact only in a single process. Each extra process (`MLC_WORKERS`) would
multiply them. Threads suit the assistant, whose requests spend their time waiting for the model
service.

- At most `ASSISTANT_MAX_CONCURRENT` (6) model calls run at once. Further requests wait up to
  `ASSISTANT_QUEUE_WAIT` (20 s) for a free slot, then the page says the assistant is busy. This
  leaves threads free to serve the course pages.
- A step gives up after `ASSISTANT_STEP_DEADLINE` (90 s). Gunicorn's timeout (130 s) and nginx's
  `proxy_read_timeout` for `/assistant/api/` (130 s) are longer, so the learner sees the app's
  message rather than a gateway error. Keep them in this order if you change one; a test checks the
  shipped files.
- A temporary failure of the model service (no connection, an error 5xx) is retried once after a
  second. Calls that fail this way are not counted against the learner's daily limit. An unusable
  answer or a timeout is counted, because it used the model.
- If the words step glosses a long text in several parts and one part fails, the page shows the
  others and says that part of the text could not be glossed.

With `gemma4:31b` on the cloud service, a full analysis takes about 15 seconds
([evaluation](assistant-evaluation.md)). Six slots therefore serve about 20 learners comfortably.

### Alternative: a container

If the server runs containers instead:

```bash
docker build -t mlc .                     # fails if the content has validation errors
docker run -d --name mlc --env-file /etc/mlc/mlc.env -v mlc-var:/srv/mlc/var \
  -p 127.0.0.1:8000:8000 --restart unless-stopped mlc
docker exec -it mlc python manage.py createsuperuser                 # first admin
```

The volume `mlc-var` holds the SQLite database (the allowlist), so keep it when you replace the
container. The entrypoint runs `manage.py migrate` and `collectstatic`, then Gunicorn. Static files
are served by the app (WhiteNoise); nginx need not have them on disk.

Put nginx (or the server's existing proxy) in front of it as above, so that TLS and compression are
handled there.

## Updating the content

The Markdown files are the source of truth. To publish changes:

```bash
cd /srv/mlc
sudo git pull
sudo .venv/bin/python tools/validate.py --quiet       # 0 errors
sudo .venv/bin/python tools/build_glossary.py --check # regenerate it first if out of date
sudo systemctl restart mlc                            # migrations run first, then the new content loads
```

**Rolling back.** `git checkout <previous tag or commit>` and restart the service (or run the previous
image). Migrations only add tables, so an older version runs against a newer database; to undo a
change of the database itself, restore `var/db.sqlite3` from a copy taken before the update
(`sudo -u mlc cp /srv/mlc/var/db.sqlite3{,.bak}`).

If new passages add characters that the web font lacks, rebuild the font on a development machine
(`python3 tools/build_font.py --source NotoSerifCJKtc-Regular.otf`) and commit the new
`app/static/fonts/noto-serif-tc-subset.woff2`. The test suite reports missing characters.

## Release checklist

- [ ] Expert review complete; reviewed pages have `status: reviewed` or `expert-reviewed`.
- [ ] `MLC_SHOW_UNREVIEWED=false` if any unreviewed pages should be hidden from learners.
- [ ] `python3 -m unittest discover -s tests` passes.
- [ ] Sign-in tested with a learner account and a reviewer account.
- [ ] The accessibility statement (`/accessibility`) has the Language Centre's contact details and
      the date of the last accessibility check.
- [ ] TLS certificate renewal is automated.
- [ ] `python manage.py assistant_check` answers OK with the production settings.

## Logs and privacy

Gunicorn's access log records the client address, time, path and status, but not query strings
(which may contain glossary searches) or user names. Sign-in failures are logged as warnings.
Problems with the model service (no connection, a refused key, timeouts, unusable answers, all
slots busy) are logged with the model name, status and timing. Texts that learners paste, and the
model's answers, are never logged or stored: they are sent by POST to the model service and
discarded after the reply.
Learners' progress and settings are kept only in their own browsers (`localStorage`); the session
cookie holds the signed-in user's CRSid, name and reviewer flag, is signed with `MLC_SECRET_KEY`
and expires after 12 hours.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Gunicorn does not start; the journal lists file names and messages | Validation errors in the content: fix them or roll back the last change |
| `ImproperlyConfigured: MLC_… is required when MLC_AUTH_MODE is oidc` | `/etc/mlc/mlc.env` incomplete or not loaded (`MLC_SECRET_KEY`, `MLC_AZURE_*`) |
| Sign-in returns to an `http://` address or fails with a redirect mismatch | `MLC_TRUST_PROXY=1` missing, or nginx not overwriting `X-Forwarded-Proto`/`X-Forwarded-Host`; or the redirect URI is not registered in Entra |
| Sign-out or the reviewer switch answers 403 (CSRF) | `MLC_TRUST_PROXY=1` missing, or nginx passes a different `Host`/`X-Forwarded-Host` |
| The sign-in error page for a University account | The person is not on the allowlist: add an entry at `/django-admin/` |
| `sqlite3.OperationalError: unable to open database file` or a read-only database | `/srv/mlc/var` is missing or not writable by the `mlc` user |
| The assistant says "not set up correctly" | Run `python manage.py assistant_check` (see Run): a wrong or missing `MLC_OLLAMA_API_KEY` (401), or `MLC_ASSISTANT_MODEL` not covered by the plan or misspelt (402, 404) |
| The assistant often says "busy" | More learners than slots: raise `MLC_ASSISTANT_MAX_CONCURRENT` (and `MLC_THREADS` with it, keeping 4 or more threads spare) |
| The assistant says "usage limit has been reached" (the service's, not the learner's) | The Ollama plan's allowance is used up: lower `MLC_ASSISTANT_HOURLY_LIMIT`, or add credits |
| Reviewer switch missing | The CRSid is not in `MLC_REVIEWERS` (lower case), or the user signed in before it was added: sign out and in again |
