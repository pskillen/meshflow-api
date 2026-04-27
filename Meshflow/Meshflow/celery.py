"""Celery app configuration."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Meshflow.settings")

app = Celery("Meshflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["traceroute", "stats", "mesh_monitoring", "rf_propagation", "nodes", "dx_monitoring"])
