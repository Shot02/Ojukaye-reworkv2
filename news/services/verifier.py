"""
AI verification engine for news articles.
Scores articles for credibility across 7 dimensions.
"""
import re
import logging
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse

from django.utils import timezone

logger = logging.getLogger(__name__)


class EnhancedNewsVerifier:
    """Multi-dimensional news credibility scorer."""

    def __init__(self):
        # Known reliable sources (Nigerian focus)
        self.reliable_sources = [
            'premiumtimesng.com', 'punchng.com', 'vanguardngr.com',
            'guardian.ng', 'thisdaylive.com', 'thenationonlineng.net',
            'sunnewsonline.com', 'tribuneonlineng.com', 'dailytrust.com',
            'leadership.ng', 'independent.ng', 'businessday.ng',
            'channelstv.com', 'arise.tv', 'tv360nigeria.com',
            'thecable.ng', 'saharareporters.com', 'pmnewsnigeria.com',
            # International
            'reuters.com', 'bbc.com', 'cnn.com', 'aljazeera.com',
            'apnews.com', 'afp.com', 'nytimes.com', 'wsj.com',
            'bloomberg.com', 'ft.com', 'economist.com',
        ]

        # Known unreliable / gossip sites
        self.unreliable_sources = [
            'naijanews.com', 'gistmania.com', 'nairaland.com',
            'trendingnaija.com', 'infonigeria.com', 'naijagists.com',
            'lindaikejisblog.com', 'naijaloaded.com.ng', 'gistlover.com',
            'naijagossip.com', 'trendybeatz.com',
        ]

        # Sensationalist words → penalty
        self.sensationalist = [
            ('shocking', 0.2), ('unbelievable', 0.2), ("you won't believe", 0.3),
            ('mind-blowing', 0.2), ('jaw-dropping', 0.2), ('incredible', 0.1),
            ('amazing', 0.1), ('epic', 0.1), ('massive', 0.1), ('huge', 0.1),
            ('explosive', 0.2), ('revealed', 0.1), ('exposed', 0.2),
            ('conspiracy', 0.3), ('cover-up', 0.3),
            ('they don\'t want you to know', 0.4),
            ('what happens next', 0.3), ('will shock you', 0.3),
            ('goes viral', 0.2), ('must read', 0.1), ('share this', 0.1),
            ('forward this', 0.1), ('prophet reveals', 0.3), ('miracle', 0.2),
        ]

        # URL shorteners
        self.url_shorteners = ['bit.ly', 'tinyurl.com', 'goo.gl', 'ow.ly', 'is.gd']

        # Suspicious TLDs
        self.suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.loan']

        # Official domains
        self.official_domains = ['.gov', '.edu', '.org', '.int', '.mil']

        # Emotional words
        self.emotional_positive = ['great', 'amazing', 'wonderful', 'excellent',
                                   'perfect', 'brilliant', 'fantastic', 'outstanding']
        self.emotional_negative = ['terrible', 'awful', 'horrible', 'disgusting',
                                   'hate', 'worst', 'evil', 'corrupt', 'disaster']

    # ==================== MAIN ====================

    def verify_article(self, article: Dict) -> Dict:
        title = article.get('title', '')
        content = article.get('content', '')
        url = article.get('url', '')
        source = article.get('source', '')

        if not title or not url:
            return self._result(0.0, 'fake', {}, ['Missing title or URL'])

        checks = {
            'source': self._check_source(source, url),
            'url': self._check_url(url),
            'content': self._check_content(title, content),
            'sensationalism': self._check_sensationalism(title, content),
            'language': self._check_language(title + ' ' + content),
        }

        weights = {
            'source': 0.35,
            'url': 0.10,
            'content': 0.20,
            'sensationalism': 0.20,
            'language': 0.15,
        }

        total = 0
        total_weight = 0
        for name, check in checks.items():
            w = weights.get(name, 0.1)
            total += check['score'] * w
            total_weight += w

        final = total / total_weight if total_weight else 0.5

        # Determine status
        if final >= 0.7:
            status = 'verified'
        elif final >= 0.5:
            status = 'likely_legit'   # published, but no "Verified" badge
        elif final >= 0.4:
            status = 'pending'        # holds for manual review
        else:
            status = 'fake'

        warnings = []
        strengths = []
        for name, check in checks.items():
            for r in check.get('reasons', []):
                if check['score'] < 0.5:
                    warnings.append(f"{name}: {r}")
                elif check['score'] > 0.7:
                    strengths.append(f"{name}: {r}")

        return self._result(final, status, checks, warnings, strengths)

    def _result(self, score, status, checks, warnings=None, strengths=None):
        return {
            'overall_score': round(score, 2),
            'score_percentage': round(score * 100, 1),
            'status': status,
            'checks': checks,
            'warnings': (warnings or [])[:5],
            'strengths': (strengths or [])[:5],
            'verified_at': timezone.now().isoformat(),
            'method': 'ai_assisted',
        }

    # ==================== CHECKS ====================

    def _check_source(self, source: str, url: str) -> Dict:
        score = 0.5
        reasons = []
        domain = self._domain(url)

        for reliable in self.reliable_sources:
            if reliable in source.lower() or reliable in domain:
                score = 0.95
                reasons.append(f"Known reliable source: {reliable}")
                break
        else:
            for unreliable in self.unreliable_sources:
                if unreliable in source.lower() or unreliable in domain:
                    score = 0.15
                    reasons.append(f"Known unreliable source: {unreliable}")
                    break
            else:
                for official in self.official_domains:
                    if official in domain:
                        score = max(score, 0.85)
                        reasons.append(f"Official domain: {official}")
                        break

        # HTTPS bonus
        if url.startswith('https://'):
            score += 0.05
            reasons.append("Secure HTTPS")
        else:
            score -= 0.05
            reasons.append("No HTTPS")

        return {'score': max(0, min(1, score)), 'reasons': reasons, 'domain': domain}

    def _check_url(self, url: str) -> Dict:
        score = 0.8
        reasons = []
        domain = self._domain(url)

        for s in self.url_shorteners:
            if s in url:
                score -= 0.3
                reasons.append(f"URL shortener: {s}")
                break

        if re.match(r'https?://\d+\.\d+\.\d+\.\d+', url):
            score -= 0.4
            reasons.append("IP address used instead of domain")

        for tld in self.suspicious_tlds:
            if domain.endswith(tld):
                score -= 0.25
                reasons.append(f"Suspicious TLD: {tld}")
                break

        return {'score': max(0, min(1, score)), 'reasons': reasons}

    def _check_content(self, title: str, content: str) -> Dict:
        score = 0.6
        reasons = []
        length = len(content)
        words = len(content.split())

        if length < 100:
            score -= 0.3
            reasons.append(f"Very short content ({length} chars)")
        elif length < 300:
            score -= 0.1
            reasons.append(f"Short content ({length} chars)")
        elif length > 1000:
            score += 0.15
            reasons.append(f"Substantial content ({length} chars)")

        if words > 200:
            score += 0.1
            reasons.append(f"{words} words")

        quotes = re.findall(r'"([^"]*)"', content)
        if len(quotes) >= 2:
            score += 0.1
            reasons.append(f"{len(quotes)} quotes")

        attribution = ['according to', 'said', 'stated', 'reported',
                       'confirmed', 'announced', 'revealed']
        for kw in attribution:
            if kw in content.lower():
                score += 0.1
                reasons.append(f"Attribution: '{kw}'")
                break

        stats = re.findall(r'\d+%|\d+\s*(?:million|billion|thousand)', content.lower())
        if stats:
            score += 0.05
            reasons.append(f"{len(stats)} statistics")

        return {'score': max(0, min(1, score)), 'reasons': reasons}

    def _check_sensationalism(self, title: str, content: str) -> Dict:
        text = (title + ' ' + content).lower()
        score = 0.8
        reasons = []
        detected = []

        for kw, penalty in self.sensationalist:
            if kw in text:
                score -= penalty
                detected.append(kw)
                reasons.append(f"Sensationalist: '{kw}'")

        if title.count('!') > 1:
            score -= 0.1
            reasons.append("Excessive exclamation marks")
        if title.count('?') > 2:
            score -= 0.1
            reasons.append("Excessive question marks")

        caps = [w for w in title.split() if w.isupper() and len(w) > 3]
        if caps:
            score -= 0.1
            reasons.append(f"ALL CAPS: {', '.join(caps[:3])}")

        return {'score': max(0, min(1, score)), 'reasons': reasons, 'detected': detected[:5]}

    def _check_language(self, text: str) -> Dict:
        score = 0.6
        reasons = []
        text_lower = text.lower()

        pos = sum(1 for w in self.emotional_positive if w in text_lower)
        neg = sum(1 for w in self.emotional_negative if w in text_lower)

        if pos > 5 or neg > 5:
            score -= 0.15
            reasons.append("Highly emotional language")
        elif pos > 2 or neg > 2:
            score -= 0.05
            reasons.append("Some emotional language")
        else:
            score += 0.1
            reasons.append("Language appears objective")

        # Sentence complexity
        sentences = [s for s in text.split('.') if len(s.strip()) > 10]
        if sentences:
            avg = sum(len(s.split()) for s in sentences) / len(sentences)
            if 12 <= avg <= 25:
                score += 0.1
                reasons.append("Good sentence complexity")
            elif avg > 30:
                score -= 0.05
                reasons.append("Very complex sentences")

        return {'score': max(0, min(1, score)), 'reasons': reasons,
                'stats': {'positive': pos, 'negative': neg}}

    @staticmethod
    def _domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            return (parsed.netloc or parsed.path).replace('www.', '').lower()
        except Exception:
            return url.lower()