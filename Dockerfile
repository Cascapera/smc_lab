FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# deps do sistema (psql client, build essentials)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium já vêm no base image

COPY . .

# coletar estáticos para servir com Whitenoise
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "trader_portal.wsgi:application", "-c", "gunicorn.conf.py", "--bind", "0.0.0.0:8000"]