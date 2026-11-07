"""WSGI entry point for production servers, e.g.:  gunicorn wsgi:application"""
from app import create_app

application = create_app()
