FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE=Meshflow.settings.monolith

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application (above the code copy so it stays cached)
RUN adduser --disabled-password --gecos "" appuser && chown appuser:appuser /app

# Install Python dependencies
COPY Meshflow/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Django project
COPY --chown=appuser:appuser ./Meshflow /app/

# Migration guard entrypoint (see docs/DEPLOY.md)
COPY --chown=appuser:appuser --chmod=755 docker-entrypoint.sh /app/docker-entrypoint.sh

# Collect static files (as root, then hand /app/Meshflow/staticfiles to appuser)
RUN python manage.py collectstatic --noinput && chown -R appuser:appuser /app/Meshflow/staticfiles

# Expose the port the app runs on
EXPOSE 8000

# Build version. Declared after the dependency and code layers so a new version does not invalidate apt/pip.
# Nothing at build time reads APP_VERSION (collectstatic falls back to "development" in settings/base.py).
ARG VERSION=development
ENV APP_VERSION=${VERSION}

USER appuser

# Refuse to start while migrations are unapplied; also applies to celery commands overriding CMD
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run Daphne ASGI server
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "Meshflow.asgi:application"]
