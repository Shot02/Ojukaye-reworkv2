"""
Assigns a category to an article based on keywords in its title and content.

Deliberately simple: keyword matching, not machine learning.
Easy to extend, easy to debug, no training data needed.
"""
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Each category has a list of keywords.
# If a keyword appears in the title → strong signal (weight 3)
# If a keyword appears in the content → weaker signal (weight 1)
CATEGORY_KEYWORDS = {
    'Politics': [
        'politics', 'government', 'president', 'election', 'senate',
        'minister', 'governor', 'apc', 'pdp', 'labour party', 'atiku',
        'tinubu', 'obi', 'national assembly', 'lawmaker', 'bill',
        'constitution', 'primaries', 'candidate', 'vote', 'ballot',
    ],
    'Business': [
        'business', 'economy', 'naira', 'market', 'stock', 'finance',
        'bank', 'investment', 'trade', 'cbn', 'inflation', 'gdp',
        'budget', 'tax', 'revenue', 'import', 'export', 'dollar',
        'forex', 'interest rate', 'startup', 'entrepreneur', 'company',
    ],
    'Sports': [
        'sports', 'football', 'super eagles', 'super falcons', 'soccer',
        'basketball', 'match', 'league', 'player', 'goal', 'coach',
        'premier league', 'champions league', 'world cup', 'afcon',
        'athlete', 'olympic', 'tennis', 'boxing', 'cricket', 'rugby',
        'nba', 'fifa', 'uefa',
    ],
    'Technology': [
        'technology', 'tech', 'digital', 'ai', 'artificial intelligence',
        'internet', 'software', 'app', 'startup', 'cyber', 'computer',
        'smartphone', 'iphone', 'android', 'google', 'microsoft', 'apple',
        'meta', 'facebook', 'twitter', 'social media', 'crypto',
        'blockchain', 'data', 'cloud', 'programming', 'developer',
    ],
    'Entertainment': [
        'entertainment', 'music', 'movie', 'nollywood', 'hollywood',
        'actor', 'actress', 'celebrity', 'film', 'davido', 'wizkid',
        'burna boy', 'taylor swift', 'beyonce', 'grammy', 'oscar',
        'concert', 'album', 'song', 'singer', 'rapper', 'director',
        'series', 'netflix', 'tv show',
    ],
    'Health': [
        'health', 'medical', 'hospital', 'doctor', 'vaccine', 'disease',
        'covid', 'treatment', 'patient', 'medicine', 'nurse', 'surgery',
        'cancer', 'diabetes', 'malaria', 'mental health', 'who',
        'outbreak', 'virus', 'pandemic', 'drug',
    ],
    'Education': [
        'education', 'school', 'university', 'student', 'teacher',
        'college', 'exam', 'academic', 'jamb', 'waec', 'neco', 'asuu',
        'lecturer', 'professor', 'scholarship', 'admission', 'curriculum',
        'classroom', 'pupil', 'graduate', 'degree',
    ],
    'Crime': [
        'crime', 'police', 'arrest', 'court', 'judge', 'robbery',
        'murder', 'kidnap', 'bandit', 'terrorist', 'boko haram',
        'iswap', 'gunmen', 'theft', 'fraud', 'scam', 'prison',
        'sentence', 'trial', 'suspect', 'investigation', 'efcc',
    ],
    'World': [
        'world', 'international', 'global', 'united nations', 'un',
        'trump', 'biden', 'putin', 'china', 'russia', 'ukraine',
        'israel', 'gaza', 'europe', 'asia', 'america', 'africa',
        'foreign', 'diplomat', 'sanction', 'treaty', 'summit',
    ],
}


DEFAULT_CATEGORY = 'News'


class Categorizer:
    """Scores an article against every category and picks the winner."""

    def __init__(self, keywords: Optional[Dict[str, list]] = None):
        self.keywords = keywords or CATEGORY_KEYWORDS

    def categorize(self, title: str, content: str = '') -> str:
        """
        Returns the best category name, or 'News' if nothing matches.
        Uses word-boundary matching so 'ai' doesn't match 'asuu'.
        """
        title = (title or '').lower()
        content = (content or '').lower()

        scores = {}
        for category, keywords in self.keywords.items():
            score = 0
            for kw in keywords:
                kw = kw.lower().strip()
                if not kw:
                    continue

                # Use word boundaries. \b matches between \w and non-\w.
                # For multi-word keywords ("super eagles"), \b still works.
                pattern = r'\b' + re.escape(kw) + r'\b'

                if re.search(pattern, title):
                    score += 3
                if re.search(pattern, content):
                    score += 1

            if score > 0:
                scores[category] = score

        if not scores:
            return DEFAULT_CATEGORY

        winner = max(scores, key=scores.get)
        logger.debug(f"Categorizer: '{winner}' (score {scores[winner]}) for: {title[:60]}")
        return winner