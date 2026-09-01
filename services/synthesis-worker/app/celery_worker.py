"""
synthesis_worker.app.celery_worker
-------------------------------------

Celery worker entry point for syntehsis queue

Start with: 
          PYTHONPATH=. celery -A app.celery_worker worker -Q synthesis -c 1 --loglevel=info
"""



from aletheia_core.config import get_settings
from aletheia_core.logging import configure_logging
from aletheia_core.queue.celery_app import celery_app

configure_logging(get_settings())

from app import tasks  

__all__ = ["celery_app"]