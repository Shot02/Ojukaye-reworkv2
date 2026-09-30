"""
Run the news pipeline from the terminal.

Examples:
    python manage.py fetch_news
    python manage.py fetch_news --limit=30
    python manage.py fetch_news --days=3 --limit=50 --workers=5
    python manage.py fetch_news --no-extract      (skip full content extraction)
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from news.services.pipeline import NewsPipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fetch news from NewsAPI + RSS, extract content, and save to the database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='How many days back to fetch (default: 1)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of articles to save (default: 50)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Parallel extractor threads (default: 5)',
        )
        parser.add_argument(
            '--no-extract',
            action='store_true',
            help='Skip full-content extraction (faster, less data)',
        )

    def handle(self, *args, **options):
        days = options['days']
        limit = options['limit']
        workers = options['workers']
        extract_full = not options['no_extract']

        if days < 1:
            raise CommandError("--days must be at least 1")
        if limit < 1:
            raise CommandError("--limit must be at least 1")
        if workers < 1:
            raise CommandError("--workers must be at least 1")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nStarting news fetch — days={days}, limit={limit}, "
            f"workers={workers}, extract_full={extract_full}\n"
        ))

        pipeline = NewsPipeline()
        stats = pipeline.run(
            days=days,
            limit=limit,
            workers=workers,
            extract_full=extract_full,
        )

        # ----- Pretty report -----
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("FETCH COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        rows = [
            ("Fetched from NewsAPI",   stats.get('fetched_newsapi', 0)),
            ("Fetched from RSS",       stats.get('fetched_rss', 0)),
            ("Total raw",              stats.get('total_raw', 0)),
            ("Duplicates removed",     stats.get('skipped_duplicates', 0)),
            ("Unique",                 stats.get('unique', 0)),
            ("Extract success",        stats.get('extract_success', 0)),
            ("Extract failed",         stats.get('extract_fail', 0)),
            ("", ""),
            ("Saved to DB",            stats.get('saved', 0)),
            ("With video",             stats.get('with_video', 0)),
            ("With audio",             stats.get('with_audio', 0)),
            ("With image",             stats.get('with_image', 0)),
            ("", ""),
            ("Duration (seconds)",     stats.get('duration_seconds', 0)),
        ]

        for label, value in rows:
            if not label:
                self.stdout.write("")
                continue
            self.stdout.write(f"  {label:<25} {value}")

        self.stdout.write(self.style.SUCCESS("=" * 60))

        if stats.get('saved', 0) == 0:
            self.stdout.write(self.style.WARNING(
                "\nNo new articles saved. Possible reasons:\n"
                "  - All fetched articles already in the database\n"
                "  - NewsAPI rate limit reached\n"
                "  - RSS feeds returned nothing\n"
            ))