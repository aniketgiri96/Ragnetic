"""Celery application for async ingestion and background jobs."""
from celery import Celery

from .config import settings

celery_app = Celery(
    "ragnetic",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.tasks.ingestion"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)
