"""
robots.txt compliance checker.
"""
import urllib.robotparser
import urllib.request
from urllib.parse import urlparse
import threading

class RobotsChecker:
    def __init__(self, user_agent: str = 'OladizzResearchBot/1.0'):
        self.user_agent = user_agent
        self._cache = {}
        self._lock = threading.Lock()

    def _get_parser(self, domain: str) -> urllib.robotparser.RobotFileParser:
        with self._lock:
            if domain in self._cache:
                return self._cache[domain]
                
        parser = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(f"https://{domain}/robots.txt", headers={'User-Agent': self.user_agent})
            with urllib.request.urlopen(req, timeout=5) as response:
                content = response.read().decode('utf-8')
                parser.parse(content.splitlines())
        except Exception:
            pass
            
        with self._lock:
            self._cache[domain] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return True
        parser = self._get_parser(domain)
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def get_crawl_delay(self, domain: str) -> float:
        parser = self._get_parser(domain)
        try:
            delay = parser.crawl_delay(self.user_agent)
            if delay is not None:
                return float(delay)
        except Exception:
            pass
        return 2.0
