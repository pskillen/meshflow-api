from celery import shared_task

from m2m_api.usage import flush_m2m_usage


@shared_task
def flush_m2m_usage_task():
    flush_m2m_usage()
