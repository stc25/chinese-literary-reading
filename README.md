# Reading Modern Literary Chinese

Course materials for Cambridge learners reading 19th–20th century literary Chinese.
See [PLAN.md](PLAN.md) for the project plan and
[docs/content-spec.md](docs/content-spec.md) for the content format.

## Layout

| Folder | Contents |
|---|---|
| `content/` | The course: units, grammar points, toolkit pages |
| `docs/` | Specifications |
| `templates/` | Blank templates and a worked example passage |
| `app/` | The Flask web app |
| `deploy/` | Server configuration: Gunicorn, nginx, systemd, settings template |
| `tools/` | Scripts: validator, glossary and font builders |
| `tests/` | Validator and app tests, and test fixtures |

## Running the web app

Requires Python 3.10+ and the packages in `requirements.txt` (`pip install -r requirements.txt`).

```bash
flask --app app run --debug --port 5050
```

Then open <http://localhost:5050/>. For production, see [docs/deployment.md](docs/deployment.md)
(Gunicorn behind nginx, or a container; configuration files in `deploy/`). In debug mode the app reloads the content when a file in
`content/` changes. The app will not start if the validator reports errors. See
[docs/app-plan.md](docs/app-plan.md) for the plan.

### Settings

Settings are read from environment variables starting with `MLC_` (lists are written as JSON):

| Setting | Meaning |
|---|---|
| `MLC_AUTH_MODE` | `oidc` (Cambridge sign-in required) or `none` (no sign-in, for development). Default: `none` with `--debug`, otherwise `oidc` |
| `MLC_OIDC_METADATA_URL` | The sign-in provider's discovery URL, e.g. `https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration` |
| `MLC_OIDC_CLIENT_ID`, `MLC_OIDC_CLIENT_SECRET` | From the app's registration with University Information Services |
| `MLC_SECRET_KEY` | A long random string that signs the session cookie (required with `oidc`) |
| `MLC_ALLOWED_DOMAINS` | Accounts allowed to sign in; default `["cam.ac.uk"]` |
| `MLC_REVIEWERS` | CRSids allowed to switch on reviewer notes, e.g. `["cz201"]` |
| `MLC_DEV_USER` | With `none`, the user to act as, e.g. `cz201` to try reviewer mode |
| `MLC_SHOW_UNREVIEWED` | `false` at release: hide pages not yet reviewed (reviewers still see them) |
| `MLC_TRUST_PROXY` | Number of reverse proxies in front of the app, e.g. `1` behind nginx |
| `MLC_ASSISTANT_ENABLED` | `false` to switch the reading assistant off |
| `MLC_OLLAMA_HOST` | The AI model server: `http://localhost:11434` (local Ollama, the default) or `https://ollama.com` |
| `MLC_OLLAMA_API_KEY` | API key for the Ollama cloud service (kept on the server) |
| `MLC_ASSISTANT_MODEL` | The model: default `qwen3.5:9b` (local); `gemma4:31b` on the Ollama cloud service |
| `MLC_ASSISTANT_DAILY_LIMIT`, `MLC_ASSISTANT_HOURLY_LIMIT` | AI calls per user per day (default 40) and for everyone per hour (default 150) |

The sign-in callback URL to register is `https://<host>/auth/callback`. Nothing about users is stored
on the server: the signed-in user's id and name are kept in the session cookie.

To try reviewer mode locally:

```bash
MLC_DEV_USER=cz201 MLC_REVIEWERS='["cz201"]' flask --app app run --debug --port 5050
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
