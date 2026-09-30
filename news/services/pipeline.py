"""
The orchestrator. Takes the output of every fetcher and:

    1. Fetches raw articles (NewsAPI + RSS)
    2. De-duplicates them
    3. Extracts full content + media from each URL
    4. Auto-categorizes each article
    5. Saves to the database as Post rows

Every step logs what it did. Nothing raises — errors are logged and skipped.
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional
import hashlib

from django.contrib.auth.models import User
from django.utils import timezone

from news.models import Post, Category, FetchLog
from news.services.newsapi_client import NewsAPIClient
from news.services.rss_fetcher import RSSFetcher
from news.services.article_extractor import ArticleExtractor
from news.services.deduplicator import Deduplicator
from news.services.categorizer import Categorizer

logger = logging.getLogger(__name__)


# The user that owns auto-fetched articles.
NEWS_BOT_USERNAME = 'newsai'


class NewsPipeline:
    """
    One class, one job: run the full fetch → save cycle.

    Usage:
        pipeline = NewsPipeline()
        stats = pipeline.run(days=1, limit=50, workers=5)
    """

    def __init__(self):
        self.api = NewsAPIClient()
        self.rss = RSSFetcher()
        self.extractor = ArticleExtractor()
        self.dedupe = Deduplicator()
        self.categorizer = Categorizer()

    # ---------- public ----------

    def run(
        self,
        days: int = 1,
        limit: int = 50,
        workers: int = 5,
        extract_full: bool = True,
    ) -> Dict:
        """
        Run the whole pipeline. Returns a stats dict.
        """
        started = timezone.now()
        logger.info("=" * 60)
        logger.info(f"PIPELINE START  days={days}  limit={limit}  workers={workers}")
        logger.info("=" * 60)

        stats = {
            'fetched_newsapi': 0,
            'fetched_rss': 0,
            'total_raw': 0,
            'unique': 0,
            'processed': 0,
            'saved': 0,
            'skipped_duplicates': 0,
            'skipped_errors': 0,
            'extract_success': 0,
            'extract_fail': 0,
            'with_video': 0,
            'with_audio': 0,
            'with_image': 0,
            'duration_seconds': 0,
        }

        # ----- 1. Fetch -----
        raw = self._fetch_all(days=days, limit=limit)
        stats['fetched_newsapi'] = sum(1 for a in raw if a.get('source_type') == 'newsapi')
        stats['fetched_rss'] = sum(1 for a in raw if a.get('source_type') == 'rss')
        stats['total_raw'] = len(raw)
        logger.info(f"[1/5] Fetched {len(raw)} raw articles "
                    f"(NewsAPI: {stats['fetched_newsapi']}, RSS: {stats['fetched_rss']})")

        if not raw:
            logger.warning("Pipeline: no articles fetched, stopping.")
            self._log_to_db('pipeline_empty', 'No articles fetched')
            return stats

        # ----- 2. Dedupe -----
        unique = self.dedupe.dedupe(raw)
        stats['unique'] = len(unique)
        stats['skipped_duplicates'] = len(raw) - len(unique)
        logger.info(f"[2/5] After dedup: {len(unique)} unique "
                    f"({stats['skipped_duplicates']} removed)")

        # ----- 3. Extract full content + media (parallel) -----
        if extract_full:
            processed = self._process_articles(unique, workers=workers)
        else:
            processed = unique
        stats['processed'] = len(processed)
        stats['extract_success'] = sum(1 for a in processed if a.get('extract_ok'))
        stats['extract_fail'] = len(processed) - stats['extract_success']
        logger.info(f"[3/5] Extracted: {stats['extract_success']} ok, "
                    f"{stats['extract_fail']} failed/skipped")

        # ----- 4. Save -----
        saved, save_stats = self._save_all(processed)
        stats.update(save_stats)
        stats['saved'] = saved
        logger.info(f"[4/5] Saved {saved} new articles to database")

        # ----- 5. Wrap up -----
        stats['duration_seconds'] = int((timezone.now() - started).total_seconds())
        logger.info(f"[5/5] PIPELINE DONE in {stats['duration_seconds']}s")
        logger.info(f"      Saved: {stats['saved']}  "
                    f"Videos: {stats['with_video']}  "
                    f"Audio: {stats['with_audio']}  "
                    f"Images: {stats['with_image']}")

        self._log_to_db(
            'pipeline_run',
            f"Saved {stats['saved']} articles in {stats['duration_seconds']}s"
        )
        return stats

    # ---------- step 1: fetch ----------

    def _fetch_all(self, days: int, limit: int) -> List[Dict]:
        """Fetch from NewsAPI + RSS, combine into one list."""
        all_articles = []

        # NewsAPI gets ~half the limit
        newsapi_limit = max(1, limit // 2)
        try:
            newsapi_articles = self.api.fetch_everything(
                query='Nigeria OR Africa OR world',
                days=days,
                limit=newsapi_limit,
            )
            all_articles.extend(newsapi_articles)
        except Exception as e:
            logger.error(f"NewsAPI fetch failed: {e}")

        # RSS gets the rest
        rss_limit = limit - len(all_articles)
        if rss_limit > 0:
            try:
                rss_articles = self.rss.fetch_all(limit=rss_limit)
                all_articles.extend(rss_articles)
            except Exception as e:
                logger.error(f"RSS fetch failed: {e}")

        return all_articles

    # ---------- step 2: extract ----------

    def _process_articles(self, articles: List[Dict], workers: int = 5) -> List[Dict]:
        """Run the extractor on each article in parallel threads."""
        processed = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._extract_one, a): a
                for a in articles
            }

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result(timeout=60)
                    processed.append(result)
                except Exception as e:
                    logger.warning(f"Extractor thread error: {e}")
                    article = futures[future]
                    article['extract_ok'] = False
                    article['extract_error'] = str(e)
                    processed.append(article)

                if i % 10 == 0:
                    logger.info(f"    ... extracted {i}/{len(articles)}")

        return processed

    def _extract_one(self, article: Dict) -> Dict:
        """Extract full content + media for a single article."""
        url = article.get('url', '')
        if not url:
            article['extract_ok'] = False
            article['extract_error'] = 'no url'
            return article

        try:
            result = self.extractor.extract(url)
            article['extract_ok'] = result.get('success', False)
            article['extract_error'] = result.get('error')

            # Prefer extracted content, fall back to what the feed gave us
            if result.get('content'):
                article['full_content'] = result['content']
            elif article.get('description'):
                article['full_content'] = article['description']
            else:
                article['full_content'] = article.get('title', '')

            # Merge media
            article['videos'] = result.get('videos', [])
            article['audios'] = result.get('audios', [])
            article['images'] = result.get('images', [])

            # Main image: extractor wins, else what the feed had
            if result.get('main_image'):
                article['image'] = result['main_image']

        except Exception as e:
            logger.warning(f"Extractor failed for {url[:70]}: {e}")
            article['extract_ok'] = False
            article['extract_error'] = str(e)
            article['full_content'] = article.get('description', article.get('title', ''))

        return article

    # ---------- step 3: save ----------

    def _save_all(self, articles: List[Dict]) -> tuple:
        """Save all processed articles to the DB. Returns (count, stats)."""
        bot = self._get_or_create_news_bot()

        save_stats = {
            'with_video': 0,
            'with_audio': 0,
            'with_image': 0,
        }
        saved = 0

        for article in articles:
            try:
                post = self._save_one(article, bot)
                if post:
                    saved += 1
                    if article.get('videos'):
                        save_stats['with_video'] += 1
                    if article.get('audios'):
                        save_stats['with_audio'] += 1
                    if article.get('image'):
                        save_stats['with_image'] += 1
            except Exception as e:
                logger.error(f"Save failed for '{article.get('title', '')[:60]}': {e}")

        return saved, save_stats

    def _save_one(self, article: Dict, bot: User) -> Optional[Post]:
        """Save one article and run AI verification immediately."""
        url = (article.get('url') or '').strip()
        title = (article.get('title') or '').strip()

        if not url or not title:
            return None

        # Skip duplicates
        external_id = hashlib.md5(url.encode()).hexdigest()
        if Post.objects.filter(external_id=external_id).exists():
            return None
        if Post.objects.filter(external_url=url).exists():
            return None

        # Category
        category_name = self.categorizer.categorize(
            title,
            article.get('full_content', '') or article.get('description', '')
        )
        category, _ = Category.objects.get_or_create(
            name=category_name,
            defaults={'slug': category_name.lower().replace(' ', '-')}
        )

        # Published date
        published_at = self._parse_date(article.get('published_at'))

        # Content
        content = article.get('full_content') or article.get('description') or title
        content = content[:20000]

        # Media
        videos = article.get('videos') or []
        audios = article.get('audios') or []
        image_url = article.get('image') or ''

        # Create post
        post = Post.objects.create(
            title=title[:200],
            content=content,
            post_type='news',
            status='published',
            author=bot,
            category=category,
            external_source=article.get('source', 'Unknown')[:200],
            external_url=url[:1000],
            external_id=external_id,
            image_url=image_url[:1000] if image_url else '',
            published_at=published_at,
            is_auto_fetched=True,
            is_approved=True,
            verification_status='unverified',
            has_media=bool(videos or audios),
            video_urls=videos if videos else [],
            audio_urls=audios if audios else [],
            meta_description=content[:160],
        )

        # ---- Run AI verification immediately ----
        try:
            self._verify_post(post)
        except Exception as e:
            logger.exception(f"AI verification failed for post {post.id}: {e}")

        return post


    def _verify_post(self, post: Post):
        """Run AI verification and apply thresholds."""
        from news.services.verifier import EnhancedNewsVerifier
        from core.models import SystemSettings

        settings = SystemSettings.get_settings()

        if not settings.auto_verify_news:
            post.verification_status = 'pending'
            post.save(update_fields=['verification_status'])
            return

        verifier = EnhancedNewsVerifier()
        article = {
            'title': post.title or '',
            'content': post.content or '',
            'url': post.external_url or post.source_url or '',
            'source': post.external_source or '',
        }
        result = verifier.verify_article(article)
        score = result.get('overall_score', 0.0)

        post.verification_score = score
        post.verification_details = result
        post.verification_method = 'ai_assisted'

        verify_at = settings.auto_approve_threshold      # default 0.7
        publish_at = settings.min_publish_threshold      # default 0.5

        if score >= verify_at:
            post.verification_status = 'verified'
            post.is_verified = True
        elif score >= publish_at:
            post.verification_status = 'likely_legit'
            post.is_verified = False
        elif score >= 0.4:
            post.verification_status = 'pending'
        else:
            post.verification_status = 'fake'

        post.save()

    # ---------- helpers ----------

    def _get_or_create_news_bot(self) -> User:
        """Get or create the Ojukaye NewsAi bot user."""
        from accounts.models import UserProfile

        bot, created = User.objects.get_or_create(
            username=NEWS_BOT_USERNAME,
            defaults={
                'email': 'newsai@ojukaye.local',
                'first_name': 'Ojukaye',
                'last_name': 'NewsAi',
                'is_active': False,
            }
        )

        if created:
            bot.set_unusable_password()
            bot.save()
            logger.info("Created Ojukaye NewsAi bot user")

        # Ensure profile has correct avatar + cover
        profile, _ = UserProfile.objects.get_or_create(user=bot)
        changed = False

        if not profile.bio:
            profile.bio = 'Ojukaye NewsAi — automated news curation powered by AI.'
            changed = True

        if changed:
            profile.save()

        return bot

    @staticmethod
    def _parse_date(date_str: str):
        """Best-effort date parsing. Falls back to now."""
        if not date_str:
            return timezone.now()
        try:
            from dateutil import parser
            parsed = parser.parse(str(date_str))
            if parsed.tzinfo is None:
                parsed = timezone.make_aware(parsed)
            return parsed
        except Exception:
            return timezone.now()

    @staticmethod
    def _log_to_db(action: str, details: str):
        try:
            FetchLog.objects.create(action=action, details=details)
        except Exception as e:
            logger.warning(f"Could not write FetchLog: {e}")