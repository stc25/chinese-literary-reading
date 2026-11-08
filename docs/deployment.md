# Deploying the course app

Draft v0.1 · 2026-11-08

How to run "Reading Modern Literary Chinese" on a Language Centre server. The app is a small Flask
application: it reads the Markdown in `content/` at start-up, keeps it in memory and serves pages. It
has **no database** and stores **nothing about users** on the server.

## What you need

- A Linux server (any current distribution) with Python 3.11 or later, nginx and a TLS certificate
  for the chosen host name, e.g. `course.langcen.cam.ac.uk`.
- About 200 MB of disk and 256 MB of memory.
- An application registration for **University sign-in** (Microsoft Entra ID), requested from
  University Information Services (UIS) by someone with authority in the Language Centre. Ask for:
  - platform: web application;
  - redirect (reply) URL: `https://<host>/auth/callback`;
  - accounts: University of Cambridge only (single tenant);
  - permissions: `openid`, `profile`, `email` (sign-in only, no access to other data);
  - a client secret.

  You receive a **tenant id**, a **client id** and a **client secret**.

## Install

```bash
sudo useradd --system --home /srv/mlc --shell /usr/sbin/nologin mlc
sudo git clone <repository> /srv/mlc
cd /srv/mlc
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo .venv/bin/python tools/validate.py --quiet        # must report 0 errors
sudo chown -R root:mlc /srv/mlc
```

## Configure

```bash
sudo mkdir -p /etc/mlc
sudo install -m 600 -o mlc deploy/mlc.env.example /etc/mlc/mlc.env
sudo nano /etc/mlc/mlc.env
```

Fill in the tenant id (in `MLC_OIDC_METADATA_URL`), client id, client secret, a new `MLC_SECRET_KEY`
and the reviewers' CRSids. All settings are listed in the [README](../README.md#settings).

## Run

The app runs under Gunicorn, managed by systemd, behind nginx:

```bash
sudo cp deploy/mlc.service /etc/systemd/system/mlc.service
sudo systemctl daemon-reload
sudo systemctl enable --now mlc
sudo systemctl status mlc

sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/mlc   # then edit host name and certificates
sudo ln -s /etc/nginx/sites-available/mlc /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Check:

```bash
curl -s https://<host>/healthz          # {"status": "ok"}
```

Then open `https://<host>/`: you should be sent to the University sign-in page and, after signing in,
see the course map.

nginx serves the static files (CSS, JavaScript, the font) and compresses responses; Gunicorn
serves the pages. If the content has validation errors, Gunicorn refuses to start and the journal
(`journalctl -u mlc`) lists them.

### Alternative: a container

If the server runs containers instead:

```bash
docker build -t mlc .                     # fails if the content has validation errors
docker run -d --name mlc --env-file /etc/mlc/mlc.env -p 127.0.0.1:8000:8000 --restart unless-stopped mlc
```

Put nginx (or the server's existing proxy) in front of it as above, so that TLS and compression are
handled there.

## Updating the content

The Markdown files are the source of truth. To publish changes:

```bash
cd /srv/mlc
sudo git pull
sudo .venv/bin/python tools/validate.py --quiet       # 0 errors
sudo .venv/bin/python tools/build_glossary.py --check # regenerate it first if out of date
sudo systemctl reload mlc                             # workers restart with the new content
```

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

## Logs and privacy

Gunicorn's access log records the client address, time, path and status, but not query strings
(which may contain glossary searches) or user names. Sign-in failures are logged as warnings.
Learners' progress and settings are kept only in their own browsers (`localStorage`); the session
cookie holds the signed-in user's CRSid, name and reviewer flag, is signed with `MLC_SECRET_KEY`
and expires after 12 hours.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Gunicorn does not start; the journal lists file names and messages | Validation errors in the content: fix them or roll back the last change |
| `RuntimeError: AUTH_MODE is 'oidc' but these settings are missing` | `/etc/mlc/mlc.env` incomplete or not loaded |
| Sign-in returns to an `http://` address or fails with a redirect mismatch | `MLC_TRUST_PROXY=1` missing, or nginx not sending `X-Forwarded-Proto` |
| "This course is open to members of the University of Cambridge only" | The account is not in `MLC_ALLOWED_DOMAINS` |
| Reviewer switch missing | The CRSid is not in `MLC_REVIEWERS` (lower case), or the user signed in before it was added: sign out and in again |
