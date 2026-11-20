# Deploying the course app

Draft v0.1 · 2026-11-08

How to run "Reading Modern Literary Chinese" on a Language Centre server. The app is a small Django
application: it reads the Markdown in `content/` at start-up, keeps it in memory and serves pages. A
small SQLite database (`var/db.sqlite3`) holds the sign-in **allowlist** and admin accounts. It stores
only each signed-in person's CRSid, display name and active flag: no email address.

**Do not use Flask.** This app is Django. The earlier Flask version (the `main` branch before the Django
port) is retired: do not install Flask, do not run `app.py` or `flask run`, and do not add Flask code or a
Flask test run. Run the app with Gunicorn on `config.wsgi:application` (or the container) and run the tests
with `python manage.py test`. If a build or test run complains that Flask is missing, you are on the wrong
branch or an old image, not missing a dependency.

In production it is served at **https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/**, under a path
of the shared lcapps host (`MLC_URL_PREFIX=/chinese-literary-reading`; Caddy strips the prefix, the app adds it back).

## What you need

- A Linux server (any current distribution) with Python 3.10 or later (the container uses 3.12) and a Caddy reverse proxy (on lcapps it is already there; Caddy gets the TLS certificate)
  for the host `lcapps.langcen.cam.ac.uk`.
- About 200 MB of disk and 256 MB of memory.
- A new **Microsoft Entra ID** app registration for this site (University sign-in), as for the other
  Language Centre apps:
  - platform: **Web**;
  - redirect URI: `https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/auth/sso/complete/azuread-tenant-oauth2/` (the operator adds it on
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
sudo install -d -m 700 -o mlc -g mlc /srv/mlc/var      # SQLite database and static files, mlc only
```

## Configure

```bash
sudo mkdir -p /etc/mlc
sudo install -m 600 -o mlc deploy/mlc.env.example /etc/mlc/mlc.env
sudo nano /etc/mlc/mlc.env
```

Fill in `MLC_AZURE_TENANT_ID` (the tenant's GUID; names such as `common` are refused),
`MLC_AZURE_CLIENT_ID`, `MLC_AZURE_CLIENT_SECRET`, a new `MLC_SECRET_KEY` (at least 32 random
characters; the example's placeholder is refused), the reviewers' CRSids and the Ollama API key. Keep `MLC_TRUST_PROXY=1`: it is **required** behind
the Caddy proxy with TLS, otherwise Django's CSRF origin check rejects the sign-out and reviewer-mode posts. All settings are listed in the
[README](../README.md#settings).

## Run

The app runs under Gunicorn (`config.wsgi:application`), managed by systemd, behind Caddy. The unit
runs `manage.py migrate` and `manage.py collectstatic` before each start:

```bash
sudo cp deploy/mlc.service /etc/systemd/system/mlc.service
sudo systemctl daemon-reload
sudo systemctl enable --now mlc
sudo systemctl status mlc

sudo systemd-run --pty --wait --collect --quiet --uid=mlc --property=EnvironmentFile=/etc/mlc/mlc.env \
  --property=WorkingDirectory=/srv/mlc /srv/mlc/.venv/bin/python manage.py createsuperuser   # first admin

# Add the site block from deploy/Caddyfile.example (edit the host name) to the server's Caddyfile, then:
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

Check:

```bash
curl -s https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/healthz         # {"status": "ok"}
```

Check the reading assistant's model settings with one short request:

```bash
sudo systemd-run --pty --wait --collect --quiet --uid=mlc --property=EnvironmentFile=/etc/mlc/mlc.env \
  --property=WorkingDirectory=/srv/mlc /srv/mlc/.venv/bin/python manage.py assistant_check
# systemd-run reads /etc/mlc/mlc.env exactly as the service does. Do not source the file in a shell:
# the shell strips the quotes from JSON values such as MLC_REVIEWERS=["cz201"].
# Model gemma4:31b at https://ollama.com; API key set.
# OK: answered in 0.6 s (334 tokens): To learn and then practise it from time to time.
```

If it fails, the log line above the error gives the service's answer: a wrong key (401), or a model
not covered by the plan (402).

### The allowlist and the first admin

Only people on the allowlist can sign in. Create the first admin as above, then open
`https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/django-admin/` and add allowlist entries in one of three forms: a CRSid (`abc123`), an
exact address (`abc123@cam.ac.uk`) or `@cam.ac.uk` for every Cambridge CRSid. Only Cambridge sign-ins (a CRSid before `@cam.ac.uk`) can ever be admitted; any other address is refused whatever the list says. Matching ignores case.
Removing an entry, or deactivating an account, takes effect on that person's next request.

**Admins.** Admins sign in at `/django-admin/` with an **email address and a password**, separate from the
Cambridge SSO. Make the first one with `createsuperuser`: give it a user name, **an email address (the login
uses it)** and a password. For more admins, add a user with an email address and a password under Users in the
admin, and tick *Staff* (and *Superuser* for full access). A University sign-in never opens the admin: it
creates a separate account with no email address. A visitor who is not signed in to the admin sees a landing
page with a button to the admin login. Restrict `/django-admin/` to the addresses you manage it from (the
`remote_ip` block is in `deploy/Caddyfile.example`).

Then open `https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/`: you should see the landing page and, after signing in with a University
account on the allowlist, the course map.

The app serves its own static files (CSS, JavaScript, the font) through WhiteNoise, from
`/srv/mlc/var/static/`, collected by `python manage.py collectstatic` (the systemd unit and the container
do it at start); Caddy needs no static rule. Caddy terminates TLS, compresses responses and forwards
everything else to Gunicorn. It sets `X-Forwarded-Proto`, `X-Forwarded-Host` and `Host` from the real
request (never appending to what the client sent): Django trusts them for the sign-in redirect URI and the CSRF check. If the content has validation errors, Gunicorn refuses to start and the journal
(`journalctl -u mlc`) lists them.

### The Caddy reverse proxy

nginx is not needed. On lcapps, Caddy sits in front of the app and handles TLS (it obtains and renews
the certificate itself), compression and the public host name. The app serves its own static files
(WhiteNoise), so Caddy needs no `/static/` rule and nothing in `/srv/mlc/var/` has to be readable by it.

The site is served under a path of the shared `lcapps.langcen.cam.ac.uk` host, so add the `redir` and
`handle_path` blocks below **inside the existing site block**, next to the other apps (a copy is in
`deploy/Caddyfile.example`). `handle_path` strips `/chinese-literary-reading` before the request reaches
Gunicorn, and `MLC_URL_PREFIX=/chinese-literary-reading` in `mlc.env` makes the app write the prefix back
into every link, redirect, static URL and cookie path (the session and CSRF cookies are limited to that path
and named `mlc_session` and `mlc_csrf`, so they cannot clash with the other apps on the host).

```
lcapps.langcen.cam.ac.uk {
    # ... the existing blocks for the other apps ...

    redir /chinese-literary-reading /chinese-literary-reading/

    handle_path /chinese-literary-reading/* {
        encode zstd gzip

        # The Django admin (the allowlist) has its own password login. Recommended: allow it only from
        # the addresses you manage it from (replace 131.111.0.0/16).
        @admin path /django-admin/*
        handle @admin {
            @outside not remote_ip 131.111.0.0/16
            respond @outside 403
            reverse_proxy 127.0.0.1:8000
        }

        # Requests larger than the assistant needs are refused here as well as in the app.
        @api path /assistant/api/*
        handle @api {
            request_body {
                max_size 256KB
            }
            reverse_proxy 127.0.0.1:8000
        }

        handle {
            reverse_proxy 127.0.0.1:8000
        }
    }
}
```

Then `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`.

- **The prefix must match.** `MLC_URL_PREFIX` and the `handle_path` path must be the same. If you change one,
  change the other, and the Entra redirect URI. Without `MLC_URL_PREFIX` the pages would link to the root of the
  host and miss the app.
- **Upstream.** `127.0.0.1:8000` is Gunicorn's default bind (`MLC_BIND`) and the port the container publishes
  (`-p 127.0.0.1:8000:8000`). If Caddy runs in Docker too, point `reverse_proxy` at the container's name and
  port on the shared network instead.
- **`MLC_TRUST_PROXY=1` is required.** Caddy sets `Host`, `X-Forwarded-Proto` and `X-Forwarded-Host` from the
  real request, and Django trusts them for the sign-in redirect address and the CSRF check. Without it,
  sign-in returns to an `http://` address and sign-out answers 403. Keep `MLC_FORWARDED_ALLOW_IPS` at
  `127.0.0.1` when Caddy is on the same machine; if Caddy connects from another address, set it to that address.
- **Timeouts.** Caddy has no proxy read timeout by default, so the assistant's AI steps (up to 90 s plus a
  queue wait) are not cut off; Gunicorn's 130 s timeout is the limit. Do not add a shorter `read_timeout`.
- **Entra redirect URI.** Register `https://lcapps.langcen.cam.ac.uk/chinese-literary-reading/auth/sso/complete/azuread-tenant-oauth2/` on the new app
  registration (the prefix is part of it).
- **Admin.** The `remote_ip` block keeps `/django-admin/` (the allowlist) to your own network. Remove it only
  if the admin accounts are protected some other way.

### The reading assistant under load

The app runs as **one Gunicorn process with 16 threads**. The assistant's usage limits are counted
in memory, so they are exact only in a single process. Each extra process (`MLC_WORKERS`) would
multiply them. Threads suit the assistant, whose requests spend their time waiting for the model
service.

- At most `ASSISTANT_MAX_CONCURRENT` (6) model calls run at once. Further requests wait up to
  `ASSISTANT_QUEUE_WAIT` (20 s) for a free slot, then the page says the assistant is busy. This
  leaves threads free to serve the course pages.
- A step gives up after `ASSISTANT_STEP_DEADLINE` (90 s). Gunicorn's timeout (130 s) is longer, and Caddy has no proxy read timeout by default, so the learner sees the app's
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

If the server runs containers instead, `docker-compose.yml` does it in one step (Gunicorn on
`127.0.0.1:8000`, the volume `mlc-var`, restart on failure; set `MLC_ENV_FILE` to `/etc/mlc/mlc.env`
or keep a `mlc.env` beside it):

```bash
docker compose up -d --build
docker compose exec web python manage.py createsuperuser      # first admin
```

The same without Compose:

```bash
docker build -t mlc .                     # fails if the content has validation errors
docker run -d --name mlc --env-file /etc/mlc/mlc.env -v mlc-var:/srv/mlc/var \
  -p 127.0.0.1:8000:8000 --restart unless-stopped mlc
# If you bind-mount a host folder instead of a named volume, `chown` it to the container's `mlc` user first
# (`docker run --rm --entrypoint id mlc -u mlc` shows the uid).
docker exec -it mlc python manage.py createsuperuser                 # first admin
```

The volume `mlc-var` holds the SQLite database (the allowlist), so keep it when you replace the
container. The entrypoint runs `manage.py migrate` and `collectstatic`, then Gunicorn. Static files
are served by the app (WhiteNoise); Caddy need not have them on disk.

Put Caddy in front of it as above, so that TLS and compression are
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
change of the database itself, restore `var/db.sqlite3` from a copy taken before the update.
Take the copy with SQLite's online backup, which is safe while the service runs (a plain `cp` can catch
a half-written file): `sudo -u mlc sqlite3 /srv/mlc/var/db.sqlite3 ".backup '/srv/mlc/var/db.sqlite3.bak'"`.

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
(which may contain glossary searches) or user names. The app logs to standard error (the journal, or
`docker logs`): warnings and errors, with a traceback for any unexpected error (500). Sign-in failures
are logged as warnings, naming only the kind of failure.
Problems with the model service (no connection, a refused key, timeouts, unusable answers, all
slots busy) are logged with the model name, status and timing. Texts that learners paste, and the
model's answers, are never logged or stored: they are sent by POST to the model service and
discarded after the reply.
Learners' progress and settings are kept only in their own browsers (`localStorage`). The session
cookie holds the user's account id, Django's session hash and the sign-in identifier (the University
address, e.g. `abc123@cam.ac.uk`, used to re-check the allowlist on every request). It is signed with
`MLC_SECRET_KEY`, so it cannot be altered, but **not encrypted**: its owner can read it. It expires
after 12 hours.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Gunicorn does not start; the journal lists file names and messages | Validation errors in the content: fix them or roll back the last change |
| `ImproperlyConfigured: MLC_… is required when MLC_AUTH_MODE is oidc` | `/etc/mlc/mlc.env` incomplete or not loaded (`MLC_SECRET_KEY`, `MLC_AZURE_*`) |
| `ImproperlyConfigured: MLC_SECRET_KEY must be a long random string` or `MLC_AZURE_TENANT_ID must be the tenant's ID` | The placeholder or a short key is still in `/etc/mlc/mlc.env`; or the tenant is given by name instead of its GUID |
| Sign-in returns to an `http://` address or fails with a redirect mismatch | `MLC_TRUST_PROXY=1` missing, or the proxy not overwriting `X-Forwarded-Proto`/`X-Forwarded-Host`; or the redirect URI is not registered in Entra |
| Sign-out or the reviewer switch answers 403 (CSRF) | `MLC_TRUST_PROXY=1` missing, or the proxy passes a different `Host`/`X-Forwarded-Host` |
| The sign-in error page for a University account | The person is not on the allowlist: add an entry at `/django-admin/` |
| `sqlite3.OperationalError: unable to open database file` or a read-only database | `/srv/mlc/var` is missing or not writable by the `mlc` user |
| The assistant says "not set up correctly" | Run `python manage.py assistant_check` (see Run): a wrong or missing `MLC_OLLAMA_API_KEY` (401), or `MLC_ASSISTANT_MODEL` not covered by the plan or misspelt (402, 404) |
| The assistant often says "busy" | More learners than slots: raise `MLC_ASSISTANT_MAX_CONCURRENT` (and `MLC_THREADS` with it, keeping 4 or more threads spare) |
| The assistant says "usage limit has been reached" (the service's, not the learner's) | The Ollama plan's allowance is used up: lower `MLC_ASSISTANT_HOURLY_LIMIT`, or add credits |
| Reviewer switch missing | The CRSid is not in `MLC_REVIEWERS`, or the service has not been restarted since it was added: `sudo systemctl restart mlc` (reviewer status is worked out on every request; nobody needs to sign out) |
