"""Configuração do Gunicorn para a aplicação Serra Rocketry.

Carregada automaticamente quando o servidor é iniciado com::

    gunicorn wsgi:app -c gunicorn.conf.py

Define o endereço de bind, logs de acesso/erro, número de workers e o
recarregamento automático em desenvolvimento (observando templates e estáticos).

Os caminhos de templates/estáticos são resolvidos relativamente a este arquivo,
de modo que a configuração funciona independentemente do diretório de trabalho
a partir do qual o gunicorn é invocado.
"""

import os

# Diretório deste arquivo de configuração (raiz do pacote app/)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Coleta de arquivos observados para reload automático
watched_files = []
for _rel_path in ["templates", "static/css", "static/js"]:
    _abs_path = os.path.join(_BASE_DIR, _rel_path)
    if os.path.isdir(_abs_path):
        for _file in os.listdir(_abs_path):
            watched_files.append(os.path.join(_abs_path, _file))

# --- Configurações do servidor ---
bind = "0.0.0.0:5000"
accesslog = "persistence/logs/access.log"
errorlog = "persistence/logs/error.log"
workers = 2
reload = True
reload_extra_files = watched_files
