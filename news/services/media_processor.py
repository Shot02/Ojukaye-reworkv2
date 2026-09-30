"""
Converts stored video/audio URLs into embeddable forms the template can use.

Input:  a Post with video_urls = [{'url': ..., 'type': ...}, ...]
Output: {'videos': [{'embed_url': ..., 'platform': ..., ...}], 'audios': [...]}

Never raises. Always returns a valid dict.
"""
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
#  URL parsers — return an embed URL or None
# ------------------------------------------------------------------

def youtube_embed(url: str) -> Optional[str]:
    """Turn a YouTube URL into an embed URL, or return None."""
    patterns = [
        r'youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})',
        r'youtu\.be/([A-Za-z0-9_-]{6,})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{6,})',
        r'youtube\.com/shorts/([A-Za-z0-9_-]{6,})',
        r'youtube\.com/v/([A-Za-z0-9_-]{6,})',
    ]
    for pat in patterns:
        m = re.search(pat, url or '')
        if m:
            return f"https://www.youtube.com/embed/{m.group(1)}"
    return None


def vimeo_embed(url: str) -> Optional[str]:
    m = re.search(r'vimeo\.com/(?:video/)?(\d+)', url or '')
    return f"https://player.vimeo.com/video/{m.group(1)}" if m else None


def dailymotion_embed(url: str) -> Optional[str]:
    m = re.search(r'dailymotion\.com/video/([A-Za-z0-9]+)', url or '')
    return f"https://www.dailymotion.com/embed/video/{m.group(1)}" if m else None


def spotify_embed(url: str) -> Optional[str]:
    m = re.search(r'spotify\.com/(?:embed/)?(track|episode|album|playlist)/([A-Za-z0-9]+)', url or '')
    if m:
        return f"https://open.spotify.com/embed/{m.group(1)}/{m.group(2)}"
    return None


def soundcloud_embed(url: str) -> Optional[str]:
    if 'soundcloud.com' in (url or ''):
        return (
            "https://w.soundcloud.com/player/?url="
            + url
            + "&color=%23ff5500&auto_play=false&hide_related=true"
              "&show_comments=false&show_user=true&show_reposts=false"
        )
    return None


# ------------------------------------------------------------------
#  Media processor
# ------------------------------------------------------------------

class MediaProcessor:
    """Process a Post's stored media into template-ready data."""

    def __init__(self, post):
        self.post = post
        self.videos: List[Dict] = []
        self.audios: List[Dict] = []

    def process(self) -> Dict:
        try:
            self._process_videos()
        except Exception as e:
            logger.exception(f"Video processing failed: {e}")
        try:
            self._process_audios()
        except Exception as e:
            logger.exception(f"Audio processing failed: {e}")

        return {
            'videos': self.videos,
            'audios': self.audios,
            'video_count': len(self.videos),
            'audio_count': len(self.audios),
            'has_video': len(self.videos) > 0,
            'has_audio': len(self.audios) > 0,
        }

    # ---------- videos ----------

    def _process_videos(self):
        raw = self._normalize_list(self.post.video_urls)
        for item in raw:
            url = item.get('url') if isinstance(item, dict) else str(item)
            if not url:
                continue

            embed = youtube_embed(url)
            if embed:
                self.videos.append({
                    'platform': 'YouTube',
                    'embed_url': embed,
                    'watch_url': url,
                    'type': 'iframe',
                })
                continue

            embed = vimeo_embed(url)
            if embed:
                self.videos.append({
                    'platform': 'Vimeo',
                    'embed_url': embed,
                    'watch_url': url,
                    'type': 'iframe',
                })
                continue

            embed = dailymotion_embed(url)
            if embed:
                self.videos.append({
                    'platform': 'Dailymotion',
                    'embed_url': embed,
                    'watch_url': url,
                    'type': 'iframe',
                })
                continue

            # direct file
            if any(url.lower().endswith(ext) for ext in ('.mp4', '.webm', '.mov', '.ogg')):
                self.videos.append({
                    'platform': 'Direct',
                    'url': url,
                    'type': 'video',
                })
                continue

            # unknown — still show a link
            self.videos.append({
                'platform': 'Video',
                'watch_url': url,
                'type': 'link',
            })

    # ---------- audios ----------

    def _process_audios(self):
        raw = self._normalize_list(self.post.audio_urls)
        for item in raw:
            url = item.get('url') if isinstance(item, dict) else str(item)
            if not url:
                continue

            embed = spotify_embed(url)
            if embed:
                self.audios.append({
                    'platform': 'Spotify',
                    'embed_url': embed,
                    'type': 'iframe',
                })
                continue

            embed = soundcloud_embed(url)
            if embed:
                self.audios.append({
                    'platform': 'SoundCloud',
                    'embed_url': embed,
                    'type': 'iframe',
                })
                continue

            if any(url.lower().endswith(ext) for ext in ('.mp3', '.m4a', '.wav', '.ogg', '.aac')):
                self.audios.append({
                    'platform': 'Direct',
                    'url': url,
                    'type': 'audio',
                })
                continue

            self.audios.append({
                'platform': 'Audio',
                'watch_url': url,
                'type': 'link',
            })

    # ---------- helpers ----------

    @staticmethod
    def _normalize_list(value) -> List:
        """Stored JSON could be list, dict, string, or None. Make it a list."""
        if not value:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            # in case someone stored a single URL as a string
            return [{'url': value}]
        return []