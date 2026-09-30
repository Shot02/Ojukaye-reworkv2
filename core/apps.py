from django.apps import AppConfig
import os


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Only run in the main process (avoid double-start with reloader)
        if os.environ.get('RUN_MAIN') == 'true':
            # Delay slightly so DB is ready
            import threading
            def delayed_start():
                import time
                time.sleep(3)
                try:
                    from news.services.scheduler import auto_fetcher
                    auto_fetcher.start()
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Could not start scheduler: {e}")

            threading.Thread(target=delayed_start, daemon=True).start()