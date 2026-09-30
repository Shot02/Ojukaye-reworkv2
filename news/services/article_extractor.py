"""
Fetches a single article URL and pulls out:
- full text content
- main image
- all images
- video embeds (YouTube, Vimeo, direct MP4, etc.)
- audio embeds (Spotify, SoundCloud, direct MP3, etc.)

Never raises. Returns a consistent dict, always.
"""
import logging
import re
import time
import random
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# Sites that are always a dead end
SKIP_DOMAINS = [
    'consent.yahoo.com',
    'consent.google.com',
    'cookieconsent',
    'facebook.com',
    'twitter.com',
    'x.com',
    'instagram.com',
    'tiktok.com',
]

# Consent-wall phrases — if we see several, give up
CONSENT_PHRASES = [
    'accept cookies',
    'cookie policy',
    'we use cookies',
    'cookie settings',
    'your privacy choices',
]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


class ArticleExtractor:
    """Extracts full content + media from a single article URL."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- public ----------

    def extract(self, url: str) -> Dict:
        """
        Main entry point. Always returns:
        {
            'success': bool,
            'title': str | None,
            'content': str | None,
            'main_image': str | None,
            'images': [{'url': ..., 'alt': ...}],
            'videos': [{'url': ..., 'type': ..., 'source': ...}],
            'audios': [{'url': ..., 'type': ..., 'source': ...}],
            'error': str | None,
        }
        """
        result = {
            'success': False,
            'title': None,
            'content': None,
            'main_image': None,
            'images': [],
            'videos': [],
            'audios': [],
            'error': None,
        }

        if not url:
            result['error'] = 'empty url'
            return result

        # Skip known dead ends
        domain = urlparse(url).netloc.lower()
        if any(skip in domain for skip in SKIP_DOMAINS):
            result['error'] = 'skipped domain'
            return result

        html = self._fetch(url)
        if not html:
            result['error'] = 'fetch failed'
            return result

        if self._is_consent_page(html):
            result['error'] = 'consent wall'
            return result

        try:
            soup = BeautifulSoup(html, 'lxml')
        except Exception:
            soup = BeautifulSoup(html, 'html.parser')

        # ---- title ----
        result['title'] = self._extract_title(soup)

        # ---- full text ----
        result['content'] = self._extract_content(soup)

        # ---- media ----
        media = self._extract_media(soup, url)
        result['main_image'] = media['main_image']
        result['images'] = media['images']
        result['videos'] = media['videos']
        result['audios'] = media['audios']

        # Success = we got text AND it's long enough to be a real article
        if result['content'] and len(result['content']) > 200:
            result['success'] = True
        elif result['content']:
            result['error'] = f"content too short ({len(result['content'])} chars)"
        else:
            result['error'] = 'no content extracted'

        return result

    # ---------- fetch ----------

    def _fetch(self, url: str) -> Optional[str]:
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'DNT': '1',
        }

        try:
            time.sleep(random.uniform(0.3, 1.0))  # be polite
            r = self.session.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)

            if r.status_code == 200:
                return r.text

            logger.debug(f"Extractor: HTTP {r.status_code} for {url}")
            return None

        except requests.exceptions.Timeout:
            logger.debug(f"Extractor: timeout for {url}")
        except requests.exceptions.SSLError:
            logger.debug(f"Extractor: SSL error for {url}")
        except requests.exceptions.ConnectionError:
            logger.debug(f"Extractor: connection error for {url}")
        except Exception as e:
            logger.debug(f"Extractor: unexpected error for {url}: {e}")

        return None

    # ---------- detection ----------

    @staticmethod
    def _is_consent_page(html: str) -> bool:
        if not html:
            return False
        low = html.lower()
        hits = sum(1 for p in CONSENT_PHRASES if p in low)
        return hits >= 3

    # ---------- title ----------

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        # og:title first (usually cleanest)
        meta = soup.find('meta', property='og:title')
        if meta and meta.get('content'):
            return meta['content'].strip()

        # then twitter:title
        meta = soup.find('meta', attrs={'name': 'twitter:title'})
        if meta and meta.get('content'):
            return meta['content'].strip()

        # then <title>
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # then h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)

        return None

    # ---------- content ----------

    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        # Kill non-content elements
        for tag in soup(['script', 'style', 'nav', 'footer', 'header',
                         'aside', 'form', 'noscript', 'iframe']):
            tag.decompose()

        # Try article containers in priority order
        containers = [
            soup.find('article'),
            soup.find('div', class_=re.compile(r'article[-_]?body|article[-_]?content|post[-_]?content|entry[-_]?content|story[-_]?body', re.I)),
            soup.find('div', {'itemprop': 'articleBody'}),
            soup.find('main'),
            soup.find('div', id=re.compile(r'content|article|story', re.I)),
        ]

        for container in containers:
            if not container:
                continue

            paragraphs = container.find_all('p')
            text = '\n\n'.join(
                p.get_text(strip=True) for p in paragraphs
                if len(p.get_text(strip=True)) > 40
            )

            if len(text) > 200:
                return text

        # Fallback: every <p> on the page
        paragraphs = soup.find_all('p')
        text = '\n\n'.join(
            p.get_text(strip=True) for p in paragraphs
            if len(p.get_text(strip=True)) > 40
        )
        return text if text else None

    # ---------- media ----------

    def _extract_media(self, soup: BeautifulSoup, base_url: str) -> Dict:
        result = {
            'main_image': None,
            'images': [],
            'videos': [],
            'audios': [],
        }

        # ----- main image: og:image > twitter:image -----
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            result['main_image'] = self._abs(og['content'], base_url)
        else:
            tw = soup.find('meta', attrs={'name': 'twitter:image'})
            if tw and tw.get('content'):
                result['main_image'] = self._abs(tw['content'], base_url)

        # ----- images -----
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if not src:
                continue
            width = img.get('width')
            if width and str(width).isdigit() and int(width) < 100:
                continue
            result['images'].append({
                'url': self._abs(src, base_url),
                'alt': img.get('alt', ''),
            })

        # ----- videos -----
        # iframes (YouTube, Vimeo, Dailymotion)
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if not src:
                continue
            full = self._abs(src, base_url)
            if 'youtube.com' in full or 'youtu.be' in full:
                result['videos'].append({'url': full, 'type': 'youtube', 'source': 'iframe'})
            elif 'vimeo.com' in full:
                result['videos'].append({'url': full, 'type': 'vimeo', 'source': 'iframe'})
            elif 'dailymotion.com' in full:
                result['videos'].append({'url': full, 'type': 'dailymotion', 'source': 'iframe'})

        # <video> tags
        for video in soup.find_all('video'):
            src = video.get('src')
            if not src:
                source = video.find('source')
                if source:
                    src = source.get('src')
            if src:
                result['videos'].append({
                    'url': self._abs(src, base_url),
                    'type': 'direct',
                    'source': 'video_tag',
                })

        # links to video files
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(href.endswith(ext) for ext in ('.mp4', '.webm', '.mov')):
                result['videos'].append({
                    'url': self._abs(a['href'], base_url),
                    'type': 'direct',
                    'source': 'link',
                })

        # ----- audios -----
        # Spotify / SoundCloud iframes
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if 'spotify.com' in src:
                result['audios'].append({'url': src, 'type': 'spotify', 'source': 'iframe'})
            elif 'soundcloud.com' in src:
                result['audios'].append({'url': src, 'type': 'soundcloud', 'source': 'iframe'})

        # <audio> tags
        for audio in soup.find_all('audio'):
            src = audio.get('src')
            if not src:
                source = audio.find('source')
                if source:
                    src = source.get('src')
            if src:
                result['audios'].append({
                    'url': self._abs(src, base_url),
                    'type': 'direct',
                    'source': 'audio_tag',
                })

        # links to audio files
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(href.endswith(ext) for ext in ('.mp3', '.m4a', '.wav', '.ogg')):
                result['audios'].append({
                    'url': self._abs(a['href'], base_url),
                    'type': 'direct',
                    'source': 'link',
                })

        # de-dup by url
        for key in ('images', 'videos', 'audios'):
            seen = set()
            unique = []
            for item in result[key]:
                u = item.get('url')
                if u and u not in seen:
                    seen.add(u)
                    unique.append(item)
            result[key] = unique

        return result

    @staticmethod
    def _abs(url: str, base: str) -> str:
        if not url:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            return urljoin(base, url)
        if not url.startswith(('http://', 'https://')):
            return urljoin(base, url)
        return url