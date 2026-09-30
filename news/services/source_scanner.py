"""
Source Scanner — tests news sources and auto-discovers RSS feeds.
"""
import logging
import time
import re
from urllib.parse import urlparse, urljoin
from typing import Optional, Dict, List
from datetime import datetime

import requests
import feedparser
from bs4 import BeautifulSoup

from django.utils import timezone

logger = logging.getLogger(__name__)


USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


class SourceScanner:
    """Tests and discovers RSS feeds."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})

    # ==================== TEST ====================

    def test_source(self, url: str, timeout: int = 12) -> Dict:
        """
        Test an RSS feed URL.
        Returns: {'ok': bool, 'count': int, 'error': str, 'response_ms': int, 'sample': [...]}
        """
        result = {
            'ok': False,
            'count': 0,
            'error': '',
            'response_ms': 0,
            'sample': [],
        }

        start = time.time()

        try:
            r = self.session.get(url, timeout=timeout, allow_redirects=True)
            result['response_ms'] = int((time.time() - start) * 1000)

            if r.status_code != 200:
                result['error'] = f'HTTP {r.status_code}'
                return result

            feed = feedparser.parse(r.content)

            if getattr(feed, 'bozo', 0) and not feed.entries:
                result['error'] = 'Invalid RSS/Atom feed'
                return result

            if not feed.entries:
                result['error'] = 'No entries in feed'
                return result

            result['ok'] = True
            result['count'] = len(feed.entries)

            # Sample the first 3 titles
            for entry in feed.entries[:3]:
                result['sample'].append({
                    'title': entry.get('title', '')[:80],
                    'published': entry.get('published', entry.get('pubDate', '')),
                })

            return result

        except requests.exceptions.Timeout:
            result['error'] = 'Timeout'
            result['response_ms'] = int((time.time() - start) * 1000)
            return result
        except requests.exceptions.ConnectionError:
            result['error'] = 'Connection error'
            result['response_ms'] = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            result['error'] = str(e)[:200]
            result['response_ms'] = int((time.time() - start) * 1000)
            return result

    # ==================== DISCOVER ====================

    def discover_feeds(self, site_url: str, timeout: int = 12) -> List[Dict]:
        """
        Given a website URL (e.g. https://example.com), try to find its RSS feed.
        Returns list of {url, title, type} candidates.
        """
        candidates = []

        # Normalize the site URL
        if not site_url.startswith('http'):
            site_url = 'https://' + site_url

        parsed = urlparse(site_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Common RSS paths to try
        common_paths = [
            '/feed',
            '/feed/',
            '/rss',
            '/rss/',
            '/rss.xml',
            '/feed.xml',
            '/atom.xml',
            '/index.xml',
            '/feeds/posts/default',
            '/blog/feed',
            '/news/feed',
            '/feed/rss',
        ]

        tried = set()

        # 1) Try to find <link rel="alternate" type="application/rss+xml"> on the page
        try:
            r = self.session.get(site_url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'html.parser')

                for link in soup.find_all('link', rel='alternate'):
                    link_type = link.get('type', '').lower()
                    href = link.get('href', '')
                    if not href:
                        continue
                    if 'rss' in link_type or 'atom' in link_type or 'xml' in link_type:
                        full = self._absolute(href, site_url)
                        if full and full not in tried:
                            tried.add(full)
                            candidates.append({
                                'url': full,
                                'title': link.get('title', ''),
                                'type': 'discovered',
                            })
        except Exception as e:
            logger.debug(f"Discovery page fetch failed: {e}")

        # 2) Try common paths
        for path in common_paths:
            url = base + path
            if url in tried:
                continue
            tried.add(url)

            try:
                r = self.session.get(url, timeout=timeout, allow_redirects=True)
                if r.status_code != 200:
                    continue

                feed = feedparser.parse(r.content)
                if feed.entries:
                    candidates.append({
                        'url': url,
                        'title': feed.feed.get('title', '') if hasattr(feed, 'feed') else '',
                        'type': 'common_path',
                    })
            except Exception:
                continue

        return candidates

    @staticmethod
    def _absolute(url: str, base: str) -> Optional[str]:
        if not url:
            return None
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith(('http://', 'https://')):
            return url
        if url.startswith('/'):
            parsed = urlparse(base)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        return urljoin(base, url)