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
| `tools/` | Scripts (validator) |
| `tests/` | Validator tests and test fixtures |

## Checking content

Requires Python 3.10+ and PyYAML (`pip install -r requirements.txt`).

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

The validator reads the allowed values for `level`, `status`, `genre`, `rights` and
`default_view` from section 2 of the spec, so a new genre only needs adding there.

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
