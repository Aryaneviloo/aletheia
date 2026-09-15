"""
judge worker celery py

start with:
PYTHONPATH=. celery -A app.celery_worker worker -Q judge -c 2 --loglevel=info

"""


from aletheia_core.config import get_settings
from aletheia_core.logging import configure_logging
from aletheia_core.queue.celery_app import celery_app

configure_logging(get_settings())

from app import tasks  # noqa: F401, E402

__all__ = ["celery_app"]