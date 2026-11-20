# Container image for the course app.
#   docker build -t mlc .
#   docker run --env-file /etc/mlc/mlc.env -v mlc-var:/srv/mlc/var -p 127.0.0.1:8000:8000 mlc
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MLC_BIND=0.0.0.0:8000
WORKDIR /srv/mlc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development stage (docker-compose.dev.yml): the repo is bind-mounted over /srv/mlc, Django's
# development server reloads on changes. MLC_DEBUG=1 gives auth mode none (no sign-in).
FROM base AS dev
ENV MLC_DEBUG=1
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:5050"]

FROM base AS prod
COPY . .
# Refuse to build an image from content with validation errors.
RUN python3 tools/validate.py --quiet

# Collect the static files. The settings refuse to load in production without the sign-in
# settings, and production validation is deliberately not weakened for the build: this single
# command runs in auth mode none with a throwaway key, which exist only for this RUN.
RUN MLC_AUTH_MODE=none MLC_SECRET_KEY=build-only python manage.py collectstatic --noinput

# var/ holds the SQLite database and the collected static files. Mount a volume on it to keep the
# allowlist across container replacements. Only the mlc user may read it (the entrypoint also sets umask 077).
RUN useradd --system --no-create-home mlc \
    && mkdir -p /srv/mlc/var \
    && chown -R mlc:mlc /srv/mlc/var \
    && chmod 700 /srv/mlc/var
VOLUME /srv/mlc/var
USER mlc
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
ENTRYPOINT ["docker/entrypoint.sh"]
