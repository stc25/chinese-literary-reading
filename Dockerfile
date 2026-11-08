# Container image for the course app.
#   docker build -t mlc .
#   docker run --env-file /etc/mlc/mlc.env -p 8000:8000 mlc
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MLC_BIND=0.0.0.0:8000
WORKDIR /srv/mlc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Refuse to build an image from content with validation errors.
RUN python3 tools/validate.py --quiet

RUN useradd --system --no-create-home mlc
USER mlc
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "wsgi:application"]
