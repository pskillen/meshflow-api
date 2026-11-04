FROM python:3.14-slim

# Add build argument for version
ARG VERSION=development

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV APP_VERSION=${VERSION}
ENV DJANGO_SETTINGS_MODULE=Meshflow.settings.monolith

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY Meshflow/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Django project
COPY ./Meshflow /app/

# Migration guard entrypoint (see docs/DEPLOY.md)
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port the app runs on
EXPOSE 8000

# Create a non-root user to run the application
RUN adduser --disabled-password --gecos "" appuser
RUN chown -R appuser:appuser /app
USER appuser

# Refuse to start while migrations are unapplied; also applies to celery commands overriding CMD
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Run Daphne ASGI server
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "Meshflow.asgi:application"]
