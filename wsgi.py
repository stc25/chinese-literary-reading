"""WSGI entry point for production servers, e.g.:  gunicorn wsgi:application

The same application as config.wsgi:application (which the Docker image uses).
"""
from config.wsgi import application  # noqa: F401
