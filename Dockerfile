# Production image: gunicorn serves the app, WhiteNoise serves static files.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Install dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Hashed static files are built into the image. The key is only for this step.
RUN DEBUG=False SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

# Don't run as root.
RUN useradd --create-home app && mkdir -p media && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
# gunicorn binds to $PORT and uses $WEB_CONCURRENCY workers when they are set.
CMD ["gunicorn", "config.wsgi", "--access-logfile", "-"]
