"""
RSS feed fetcher.
Same output shape as NewsAPIClient — returns normalized article dicts,
so the rest of the pipeline doesn't care where an article came from.
"""
import logging
import time
from typing import List, Dict, Optional

import feedparser
import requests

logger = logging.getLogger(__name__)


# ------------------------------------------------
# Nigerian feeds — primary pool
# ------------------------------------------------
NIGERIAN_FEEDS = [
    ('Premium Times',     'https://www.premiumtimesng.com/feed'),
    ('Punch',             'https://punchng.com/feed'),
    ('Vanguard',          'https://www.vanguardngr.com/feed'),
    ('The Guardian NG',   'https://guardian.ng/feed/'),
    ('The Cable',         'https://www.thecable.ng/feed'),
    ('ThisDay',           'https://www.thisdaylive.com/index.php/feed/'),
    ('The Nation NG',     'https://thenationonlineng.net/feed/'),
    ('Leadership',        'https://leadership.ng/feed/'),
    ('BusinessDay NG',    'https://businessday.ng/feed/'),
    ('Channels TV',       'https://www.channelstv.com/feed/'),
    ('Legit NG',          'https://legit.ng/rss/all.rss'),
    ('Daily Trust',       'https://dailytrust.com/feed/'),
    ('Tribune NG',        'https://tribuneonlineng.com/feed/'),
    ('Sahara Reporters',  'https://saharareporters.com/feed'),
    ('The Sun NG',        'https://www.sunnewsonline.com/feed/'),
    ('Independent NG',    'https://independent.ng/feed/'),
]


# ------------------------------------------------
# International feeds — fallback pool only
# ------------------------------------------------
INTERNATIONAL_FEEDS = [
    ('BBC Africa',        'https://feeds.bbci.co.uk/news/world/africa/rss.xml'),
    ('BBC World',         'https://feeds.bbci.co.uk/news/world/rss.xml'),
    ('Al Jazeera',        'https://www.aljazeera.com/xml/rss/all.xml'),
    ('Reuters Africa',    'https://feeds.reuters.com/reuters/AFRICATopNews'),
]


# Backwards compat — anything importing DEFAULT_FEEDS still works
DEFAULT_FEEDS = NIGERIAN_FEEDS + INTERNATIONAL_FEEDS


USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


class RSSFetcher:
    """Pulls articles from a list of RSS feeds."""

    def __init__(self, feeds=None, prefer_nigerian=True):
        """
        feeds: optional explicit list of (name, url) tuples.
        prefer_nigerian: if True, default DB-loaded sources are filtered
                         to Nigerian sources only (country_hint='Nigeria').
        """
        if feeds is None:
            feeds = self._load_from_db(nigerian_only=prefer_nigerian)
            if not feeds:
                # Nothing in DB yet — fall back to hardcoded pools
                feeds = NIGERIAN_FEEDS if prefer_nigerian else DEFAULT_FEEDS

        self.feeds = feeds
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})

    def _load_from_db(self, nigerian_only: bool = True):
        """
        Load active sources from the database.
        If nigerian_only is True, restrict to sources tagged with Nigeria.
        """
        try:
            from news.models import NewsSource
            qs = NewsSource.objects.filter(
                is_active=True,
                source_type='rss',
            ).exclude(last_status='broken')

            if nigerian_only:
                qs = qs.filter(country_hint__iexact='Nigeria')

            return list(qs.values_list('name', 'url'))
        except Exception as e:
            logger.warning(f"Could not load sources from DB: {e}")
            return []

    # ---------- public ----------

    def fetch_nigerian(self, limit: int = 50) -> List[Dict]:
        """Fetch only from Nigerian sources."""
        return self._fetch_feeds(NIGERIAN_FEEDS, limit=limit, label='NG')

    def fetch_international(self, limit: int = 50) -> List[Dict]:
        """Fetch only from international sources (used as fallback)."""
        return self._fetch_feeds(INTERNATIONAL_FEEDS, limit=limit, label='INTL')

    def fetch_all(self, limit: int = 50) -> List[Dict]:
        """
        Legacy method — kept for compatibility.
        Now delegates to the Nigeria-first version.
        """
        return self.fetch_nigerian(limit=limit)

    # ---------- internals ----------

    def _fetch_feeds(self, feeds: list, limit: int, label: str = '') -> List[Dict]:
        """Fetch from a specific feed list."""
        if not feeds:
            return []

        per_feed = max(3, limit // len(feeds))
        collected: List[Dict] = []

        for name, url in feeds:
            if len(collected) >= limit:
                break

            remaining = limit - len(collected)
            take = min(per_feed, remaining)

            try:
                articles = self._fetch_one(name, url, take)
                collected.extend(articles)
                logger.info(f"RSS[{label}] '{name}': {len(articles)} articles")
            except Exception as e:
                logger.warning(f"RSS[{label}] '{name}' failed: {e}")

            time.sleep(0.5)

        logger.info(f"RSS[{label}]: total {len(collected)} articles collected.")
        return collected[:limit]

    # ---------- internals ----------

    def _fetch_one(self, name: str, url: str, limit: int) -> List[Dict]:
        """Fetch + parse a single RSS feed."""
        feed = feedparser.parse(url, agent=USER_AGENT)

        # feedparser doesn't raise on bad feeds, it sets `bozo`
        if getattr(feed, 'bozo', 0):
            logger.debug(f"RSS '{name}': parse warning (bozo) — continuing.")

        entries = feed.entries[:limit]
        normalized = []

        for entry in entries:
            title = (entry.get('title') or '').strip()
            link = (entry.get('link') or '').strip()

            if not title or not link:
                continue

            description = (
                entry.get('description')
                or entry.get('summary')
                or ''
            )
            # Strip HTML tags from the summary
            description = self._strip_html(description)[:500]

            image = self._extract_image(entry)

            published = (
                entry.get('published')
                or entry.get('pubDate')
                or entry.get('updated')
                or ''
            )

            normalized.append({
                'title': title,
                'url': link,
                'description': description,
                'content': '',
                'image': image,
                'source': name,
                'author': entry.get('author', ''),
                'published_at': published,
                'source_type': 'rss',
            })

        return normalized

    @staticmethod
    def _strip_html(text: str) -> str:
        """Cheap HTML stripper (no BeautifulSoup needed for RSS)."""
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def _extract_image(entry) -> str:
        """Try several places RSS feeds stash images."""
        # 1. media:content
        media = entry.get('media_content') or []
        for m in media:
            if m.get('url'):
                return m['url']

        # 2. media:thumbnail
        thumb = entry.get('media_thumbnail') or []
        for t in thumb:
            if t.get('url'):
                return t['url']

        # 3. enclosure
        enclosures = entry.get('enclosures') or []
        for enc in enclosures:
            if enc.get('type', '').startswith('image') and enc.get('href'):
                return enc['href']

        # 4. inside the summary HTML
        summary = entry.get('summary') or entry.get('description') or ''
        if '<img' in summary:
            import re
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
            if match:
                return match.group(1)

        return ''