"""Ponto de entrada WSGI para servidores de produção (gunicorn/uWSGI).

Importa a instância ``app`` criada pela *app factory* em :mod:`app`. Use com::

    gunicorn wsgi:app --bind 0.0.0.0:5000
"""

from app import app

__all__ = ["app"]
