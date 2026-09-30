"""
Background auto-fetcher scheduler.
Runs in a daemon thread when the server starts.
Checks every 60 seconds and runs the fetcher when due.
Can be started/stopped from the admin UI.
"""
import logging
import threading
import time
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


INTERVALS = {
    '30min': timedelta(minutes=30),
    '1h':    timedelta(hours=1),
    '3h':    timedelta(hours=3),
    '6h':    timedelta(hours=6),
    '12h':   timedelta(hours=12),
    '24h':   timedelta(hours=24),
}


class AutoFetchScheduler:
    """Singleton scheduler running in a background thread."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._thread = None
            cls._instance._running = False
        return cls._instance

    # ==================== LIFECYCLE ====================

    def start(self):
        """Start the scheduler thread (idempotent)."""
        with self._lock:
            if self._running:
                logger.info("Scheduler already running")
                return False
            self._running = True

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Auto-fetch scheduler STARTED")
        return True

    def stop(self):
        """Stop the scheduler thread."""
        with self._lock:
            if not self._running:
                return False
            self._running = False
        logger.info("Auto-fetch scheduler STOPPED")
        return True

    @property
    def is_running(self):
        return self._running

    # ==================== MAIN LOOP ====================

    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"Scheduler tick failed: {e}")
            time.sleep(60)  # check every minute

    def _tick(self):
        from core.models import SystemSettings

        settings = SystemSettings.get_settings()

        if not settings.enable_auto_fetch:
            return

        now = timezone.now()

        # First run — schedule it
        if not settings.auto_fetch_next_run:
            interval = INTERVALS.get(settings.auto_fetch_interval, INTERVALS['6h'])
            settings.auto_fetch_next_run = now + interval
            settings.save(update_fields=['auto_fetch_next_run'])
            logger.info(f"Scheduler: next run set to {settings.auto_fetch_next_run}")
            return

        # Time to fetch?
        if now >= settings.auto_fetch_next_run:
            logger.info("Scheduler: running auto-fetch")
            self._run_fetch(settings)

    def _run_fetch(self, settings):
        """Run the pipeline and reschedule."""
        from news.services.pipeline import NewsPipeline

        try:
            pipeline = NewsPipeline()
            stats = pipeline.run(
                days=1,
                limit=settings.max_news_per_fetch,
                workers=5,
                extract_full=True,
            )
            logger.info(f"Auto-fetch complete: saved {stats.get('saved', 0)}")
        except Exception as e:
            logger.exception(f"Auto-fetch failed: {e}")

        now = timezone.now()
        interval = INTERVALS.get(settings.auto_fetch_interval, INTERVALS['6h'])
        settings.auto_fetch_last_run = now
        settings.auto_fetch_next_run = now + interval
        settings.save(update_fields=['auto_fetch_last_run', 'auto_fetch_next_run'])


auto_fetcher = AutoFetchScheduler()