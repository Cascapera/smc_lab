"""
Configuração do Gunicorn com log de acesso incluindo tempo de resposta.

O formato de log inclui o tempo em segundos no final (ex: 0.234).
Para usar: gunicorn trader_portal.wsgi:application -c gunicorn.conf.py
"""

import os

# Bind
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
worker_class = "sync"
threads = int(os.environ.get("GUNICORN_THREADS", 1))

# Log: inclui tempo de resposta em microsegundos no final (ex: 234000 = 234ms)
# %(D)s = tempo em microsegundos
accesslog = "-"  # stdout
errorlog = "-"
access_log_format = '%(h)s - - %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

capture_output = True
