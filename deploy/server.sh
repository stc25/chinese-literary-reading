#!/usr/bin/env bash
# One-command setup and update of the course app on the lcapps server (Docker + the existing Caddy).
#
#   cd /var/www/chinese-literary-reading
#   ./deploy/server.sh setup     # first time: writes mlc.env (asks for the Entra values), builds, starts, checks
#   ./deploy/server.sh update    # later: git pull, rebuild, restart, check
#   ./deploy/server.sh status    # is it running and healthy?
#   ./deploy/server.sh admin     # create an admin (asks for a user name, an email address and a password)
#
# Secrets are typed here (not echoed) and written to mlc.env (mode 600, ignored by git). Nothing is sent anywhere.
set -euo pipefail
umask 077     # files written here (mlc.env) are private

cd "$(dirname "$0")/.."
BASE="https://lcapps.langcen.cam.ac.uk/chinese-literary-reading"
ENV_FILE="${MLC_ENV_FILE:-./mlc.env}"
export MLC_ENV_FILE="$ENV_FILE"

say()  { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed (or not on PATH)."; }

check_tools() {
  need git; need docker
  docker compose version >/dev/null 2>&1 || die "'docker compose' is not available (install the Docker Compose plugin)."
  docker info >/dev/null 2>&1 || die "Cannot talk to Docker. Is this user in the docker group (or use sudo)?"
}

check_code() {
  [ -f manage.py ] && [ -f config/settings.py ] || die "This is not the Django version of the app (no manage.py). You are on the old Flask code: do NOT use Flask. Run: git checkout main && git pull"
  branch="$(git branch --show-current)"
  [ "$branch" = "main" ] || echo "Note: you are on branch '$branch', not 'main'."
}

# set_var KEY VALUE: replace the KEY= line in the env file (no sed, so special characters in secrets are safe)
set_var() {
  K="$1" V="$2" awk 'BEGIN{k=ENVIRON["K"]; v=ENVIRON["V"]; done=0}
    index($0, k "=")==1 {print k "=" v; done=1; next} {print}
    END{if(!done) print k "=" v}' "$ENV_FILE" > "$ENV_FILE.tmp" && chmod 600 "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
}

ask() { # ask PROMPT [secret]
  local reply
  if [ "${2:-}" = "secret" ]; then read -r -s -p "$1: " reply; echo >&2; else read -r -p "$1: " reply; fi
  printf '%s' "$reply"
}

make_env() {
  if [ -f "$ENV_FILE" ]; then
    echo "$ENV_FILE already exists: keeping it. Edit it by hand to change a setting."
    return
  fi
  say "Creating $ENV_FILE (the Microsoft Entra app registration for this site is needed)"
  cp deploy/mlc.env.example "$ENV_FILE"; chmod 600 "$ENV_FILE"
  local tenant client secret key
  while :; do
    tenant="$(ask 'Directory (tenant) ID, a GUID like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')"
    [[ "$tenant" =~ ^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$ ]] && break
    echo "That is not a GUID ('common' and names are refused). Try again."
  done
  client="$(ask 'Application (client) ID')"
  secret="$(ask 'Client secret (not shown)' secret)"
  [ -n "$client" ] && [ -n "$secret" ] || die "The client ID and secret are required."
  if command -v openssl >/dev/null 2>&1; then key="$(openssl rand -hex 32)"; else key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"; fi
  set_var MLC_AZURE_TENANT_ID "$tenant"
  set_var MLC_AZURE_CLIENT_ID "$client"
  set_var MLC_AZURE_CLIENT_SECRET "$secret"
  set_var MLC_SECRET_KEY "$key"
  local ollama; ollama="$(ask 'Ollama API key for the reading assistant (Enter to skip, not shown)' secret)"
  if [ -n "$ollama" ]; then set_var MLC_OLLAMA_API_KEY "$ollama"; else set_var MLC_ASSISTANT_ENABLED false; echo "Assistant switched off (no API key). Set MLC_ASSISTANT_ENABLED=true and MLC_OLLAMA_API_KEY in $ENV_FILE to enable it."; fi
  echo "Wrote $ENV_FILE (mode 600). A new MLC_SECRET_KEY was generated."
}

start() {
  say "Building and starting the container (the build fails if the content has validation errors)"
  docker compose up -d --build
}

wait_healthy() {
  say "Waiting for the app to answer"
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then echo "Healthy: $(curl -s http://127.0.0.1:8000/healthz)"; return 0; fi
    sleep 2
  done
  docker compose logs --tail 40 web || true
  die "The app did not become healthy. See the log above (usually a missing or invalid value in $ENV_FILE)."
}

next_steps() {
  cat <<TXT

==> The app is running on 127.0.0.1:8000. Remaining steps (once):
  1. Entra: register this redirect URI on the app registration:
       $BASE/auth/sso/complete/azuread-tenant-oauth2/
  2. Caddy: add the 'redir' and 'handle_path' blocks from deploy/Caddyfile.example inside the existing
     lcapps.langcen.cam.ac.uk block, set the admin 'remote_ip' range, then:
       sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
  3. Create an admin (email address + password):   ./deploy/server.sh admin
  4. Open $BASE/django-admin/ , sign in, and add the people who may sign in under "Allowed logins".
  5. Open $BASE/ and try a University sign-in.
TXT
}

case "${1:-}" in
  setup)  check_tools; check_code; make_env; start; wait_healthy; next_steps ;;
  update) check_tools; check_code; [ -f "$ENV_FILE" ] || die "No $ENV_FILE: run ./deploy/server.sh setup first."
          say "Pulling the latest code"; git pull --ff-only; start; wait_healthy ;;
  status) check_tools; docker compose ps; curl -fsS http://127.0.0.1:8000/healthz && echo ;;
  admin)  check_tools; docker compose exec web python manage.py createsuperuser ;;
  *) sed -n '2,11p' "$0"; exit 2 ;;
esac
