"""Reading the local app/.env file (development)."""
import json
from pathlib import Path

ENV_ALIASES = {"Ollama_API": "OLLAMA_API_KEY", "OLLAMA_API_KEY": "OLLAMA_API_KEY"}


def read_env_file(path: Path) -> dict:
    """Settings from a local .env file (development): MLC_NAME=value lines, as in the environment.

    `Ollama_API` and `OLLAMA_API_KEY` are also accepted for the API key. Values are parsed as
    JSON where possible (true, 40, ["a"]), like Flask's from_prefixed_env. A missing file is
    no error. The file is ignored by git and must never be committed.
    """
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if key.startswith("export "):
            key = key[7:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in ENV_ALIASES:
            out[ENV_ALIASES[key]] = value
        elif key.startswith("MLC_"):
            try:
                out[key[4:]] = json.loads(value)
            except ValueError:
                out[key[4:]] = value
    return out
