"""
Clean wrapper around the NewsAPI.org API.
Single responsibility: talk to NewsAPI and return structured articles.

Docs: https://newsapi.org/docs/endpoints
Free tier limits: 100 requests/day, 24-hour delay, dev only.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2"


class NewsAPIClient:
    """Thin client for NewsAPI. One method per endpoint we use."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'NEWS_API_KEY', '')
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Ojukaye/1.0'})

        if not self.api_key:
            logger.warning("NewsAPI key is missing — fetches will fail.")

    # ---------- public methods ----------

    def fetch_top_headlines(
        self,
        country: str = 'us',
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Top headlines for a country, optionally filtered by category.
        Returns a list of normalized article dicts.
        """
        params = {
            'apiKey': self.api_key,
            'country': country,
            'pageSize': min(limit, 100),
        }
        if category:
            params['category'] = category

        data = self._get(f"{NEWSAPI_BASE}/top-headlines", params)
        return self._normalize(data.get('articles', []))

    def fetch_nigeria_headlines(self, limit: int = 50) -> List[Dict]:
        """
        Nigeria-only top headlines. Uses NewsAPI's country filter,
        which is much more precise than a keyword search.
        """
        return self.fetch_top_headlines(country='ng', limit=limit)

    def fetch_everything(
        self,
        query: str,
        days: int = 1,
        language: str = 'en',
        limit: int = 50,
        domains: Optional[str] = None,
    ) -> List[Dict]:
        """
        Search all articles matching a query.
        Optionally restrict to specific domains (comma-separated string).
        """
        from_date = (timezone.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        params = {
            'apiKey': self.api_key,
            'q': query,
            'from': from_date,
            'language': language,
            'sortBy': 'publishedAt',
            'pageSize': min(limit, 100),
        }
        if domains:
            params['domains'] = domains

        data = self._get(f"{NEWSAPI_BASE}/everything", params)
        return self._normalize(data.get('articles', []))
    
    # ---------- internals ----------

    def _get(self, url: str, params: Dict, retries: int = 2) -> Dict:
        """GET with retry + clean error handling. Always returns a dict."""
        for attempt in range(retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=15)

                if r.status_code == 200:
                    return r.json()

                if r.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"NewsAPI rate limited. Waiting {wait}s.")
                    time.sleep(wait)
                    continue

                if r.status_code == 401:
                    logger.error("NewsAPI: invalid API key.")
                    return {}

                if r.status_code == 426:
                    logger.error("NewsAPI: upgrade required for this request.")
                    return {}

                logger.warning(f"NewsAPI returned {r.status_code}: {r.text[:200]}")
                return {}

            except requests.exceptions.Timeout:
                logger.warning(f"NewsAPI timeout (attempt {attempt + 1}).")
                time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as e:
                logger.warning(f"NewsAPI request error: {e}")
                time.sleep(2 ** attempt)

        logger.error("NewsAPI: all retries failed.")
        return {}

    def _normalize(self, raw_articles: List[Dict]) -> List[Dict]:
        """
        Convert NewsAPI's article shape into our internal shape.
        This is what every fetcher outputs, so downstream code doesn't care
        where the article came from.
        """
        normalized = []
        for item in raw_articles:
            title = (item.get('title') or '').strip()
            url = (item.get('url') or '').strip()

            # Skip garbage
            if not title or title == '[Removed]' or not url:
                continue

            normalized.append({
                'title': title,
                'url': url,
                'description': (item.get('description') or '').strip(),
                'content': (item.get('content') or '').strip(),
                'image': item.get('urlToImage') or '',
                'source': (item.get('source') or {}).get('name', 'Unknown'),
                'author': item.get('author') or '',
                'published_at': item.get('publishedAt') or '',
                'source_type': 'newsapi',
            })

        logger.info(f"NewsAPI: normalized {len(normalized)} articles.")
        return normalized