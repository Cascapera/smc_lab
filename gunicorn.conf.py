"""
Configuração do Gunicorn.

Carregada pelo CMD do Dockerfile (`-c gunicorn.conf.py`). Até o Deploy 4 o
docker-compose sobrescrevia o CMD sem o `-c`, então nada disto valia em
produção: rodava com 1 worker, timeout de 30s e sem access log.
"""

import os

# Bind
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
worker_class = "sync"
threads = int(os.environ.get("GUNICORN_THREADS", 1))

# Timeout do worker.
#
# A análise por IA ainda roda dentro do request e o cliente da OpenAI usa
# OPENAI_TIMEOUT=90 com retentativas (trades/llm_service.py). Com o timeout
# padrão de 30s o arbiter matava o worker no meio, devolvendo 502 ao usuário
# depois de a OpenAI já ter cobrado a chamada. 120s cobre o caso.
#
# Isto é um paliativo: enquanto a análise for síncrona, uma requisição segura
# metade da capacidade (são 2 workers). A correção real é mover a análise para
# uma task Celery — está na Fase 2 do projeto.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Recicla o worker periodicamente para conter vazamento de memória.
# O jitter evita que todos reiniciem ao mesmo tempo.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", 100))

# Log: inclui tempo de resposta em microsegundos no final (ex: 234000 = 234ms)
# %(D)s = tempo em microsegundos
accesslog = "-"  # stdout
errorlog = "-"
access_log_format = '%(h)s - - %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
