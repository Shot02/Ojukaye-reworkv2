"""
Removes duplicate articles before they hit the database.

Two layers of dedup:
1. Exact URL match — same link from RSS + NewsAPI
2. Title similarity — same story from BBC and Al Jazeera
"""
import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)


# Words that don't help distinguish articles
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'were', 'has', 'have',
    'had', 'be', 'been', 'are', 'this', 'that', 'these', 'those', 'it',
    'its', 'will', 'would', 'can', 'could', 'should', 'says', 'said',
    'after', 'before', 'over', 'under', 'new', 'says',
}


class Deduplicator:
    """
    Takes a list of article dicts, returns a list with dupes removed.
    """

    def __init__(self, title_threshold: float = 0.7):
        # 0.7 = 70% word overlap → duplicate
        self.title_threshold = title_threshold

    def dedupe(self, articles: List[Dict]) -> List[Dict]:
        if not articles:
            return []

        seen_urls = set()
        seen_titles: List[set] = []
        unique: List[Dict] = []

        for article in articles:
            url = (article.get('url') or '').strip()
            title = (article.get('title') or '').strip()

            if not url or not title:
                continue

            # Layer 1 — exact URL
            if url in seen_urls:
                logger.debug(f"Dedup: URL match skipped -> {url[:70]}")
                continue
            seen_urls.add(url)

            # Layer 2 — title similarity
            title_words = self._tokenize(title)
            if not title_words:
                unique.append(article)
                continue

            is_dupe = False
            for existing in seen_titles:
                if self._jaccard(title_words, existing) >= self.title_threshold:
                    is_dupe = True
                    break

            if is_dupe:
                logger.debug(f"Dedup: title match skipped -> {title[:70]}")
                continue

            seen_titles.append(title_words)
            unique.append(article)

        logger.info(
            f"Dedup: {len(articles)} in -> {len(unique)} out "
            f"({len(articles) - len(unique)} removed)"
        )
        return unique

    # ---------- helpers ----------

    @staticmethod
    def _tokenize(title: str) -> set:
        """Lowercase, strip punctuation, drop stopwords."""
        title = title.lower()
        title = re.sub(r'[^a-z0-9\s]', ' ', title)
        words = {w for w in title.split() if w and w not in STOPWORDS and len(w) > 2}
        return words

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        """Jaccard similarity between two word sets."""
        if not a or not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union) if union else 0.0