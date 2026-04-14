"""
Traceroute trigger rate limits: manual HTTP API and future Mesh Monitoring Celery.

Mesh Monitoring (phase 03b) should import MONITORING_TRIGGER_MIN_INTERVAL_SEC for
per-source spacing when scheduling verification traceroutes (see parent epic).
"""

# Manual trigger API: reject requests within this window (see traceroute views).
MANUAL_TRIGGER_MIN_INTERVAL_SEC = 60

# Intended default for monitoring/Celery-initiated traceroutes per source (~30s firmware-aligned).
MONITORING_TRIGGER_MIN_INTERVAL_SEC = 30
