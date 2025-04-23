FROM python:3.12-slim

# Add build argument for version
ARG VERSION=development

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV APP_VERSION=${VERSION}

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

# Replace version in settings.py
RUN sed -i "s/VERSION = os.environ.get('APP_VERSION', 'development')/VERSION = '${VERSION}'/" Meshflow/settings/base.py

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port the app runs on
EXPOSE 8000

# Run the Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"] 