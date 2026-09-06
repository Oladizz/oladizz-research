"""
Multi-Engine Search & Discovery Module.
Supports:
1. Google Custom Search JSON API (with GOOGLE_SEARCH_API_KEY & GOOGLE_SEARCH_ENGINE_ID)
2. Free Fallback: DuckDuckGo HTML & Lite Search
3. Free Fallback: Wikipedia API (Canonical high-credibility articles)
4. Free Fallback: arXiv Open Access Scientific Research API
5. Free Fallback: PubMed / NCBI PMC Biomedical Research API
6. Brave Search API (if BRAVE_SEARCH_API_KEY provided)
"""
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup


def normalize_url(url: str) -> str:
    """Normalize URL: strip tracking parameters, www, trailing slashes, and anchors."""
    if not url or not url.startswith("http"):
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        
        # Strip tracking query parameters
        tracking_prefixes = ("utm_", "fbclid", "gclid", "ref", "source", "campaign")
        if parsed.query:
            qsl = urllib.parse.parse_qsl(parsed.query)
            filtered_qsl = [(k, v) for k, v in qsl if not any(k.startswith(p) for p in tracking_prefixes)]
            query_str = urllib.parse.urlencode(filtered_qsl)
        else:
            query_str = ""

        cleaned = urllib.parse.urlunparse((
            parsed.scheme,
            netloc,
            parsed.path.rstrip("/"),
            "",
            query_str,
            ""
        ))
        return cleaned
    except Exception:
        return url.strip()


class MultiSearchEngine:
    """Universal multi-engine search provider with automatic free fallbacks."""

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        google_engine_id: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ):
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_SEARCH_API_KEY") or os.environ.get("SEARCH_API_KEY", "")
        self.google_engine_id = google_engine_id or os.environ.get("GOOGLE_SEARCH_ENGINE_ID") or os.environ.get("SEARCH_ENGINE_ID", "")
        self.brave_api_key = brave_api_key or os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self.headers = {"User-Agent": user_agent}

    # ─── 1. Google Custom Search JSON API ─────────────────────────────

    def search_google(self, query: str, max_results: int = 10) -> List[str]:
        """Queries Google Custom Search JSON API."""
        if not self.google_api_key or not self.google_engine_id:
            return []
        urls = []
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.google_api_key,
                "cx": self.google_engine_id,
                "q": query,
                "num": min(10, max_results)
            }
            resp = requests.get(url, params=params, headers=self.headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    link = item.get("link")
                    if link:
                        clean = normalize_url(link)
                        if clean:
                            urls.append(clean)
        except Exception as e:
            print(f"Google API search warning: {e}")
        return urls

    # ─── 2. Free Fallback: DuckDuckGo HTML / Lite ──────────────────────

    def search_duckduckgo(self, query: str, max_results: int = 10) -> List[str]:
        """Scrapes DuckDuckGo HTML without requiring an API key."""
        urls = []
        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query, "b": ""}
            resp = requests.post(url, data=data, headers=self.headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.select(".result__url"):
                    href = a.get("href")
                    if href:
                        if href.startswith("//"):
                            href = "https:" + href
                        clean = normalize_url(href)
                        if clean and clean not in urls:
                            urls.append(clean)
                            if len(urls) >= max_results:
                                break
        except Exception as e:
            print(f"DuckDuckGo search warning: {e}")
        return urls

    # ─── 3. Free Fallback: Wikipedia API ──────────────────────────────

    def search_wikipedia(self, query: str, max_results: int = 5) -> List[str]:
        """Free Wikipedia Open API search for canonical encyclopedia articles."""
        urls = []
        try:
            endpoint = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results
            }
            resp = requests.get(endpoint, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                search_results = data.get("query", {}).get("search", [])
                for item in search_results:
                    title = item.get("title", "")
                    if title:
                        slug = urllib.parse.quote(title.replace(" ", "_"))
                        urls.append(f"https://en.wikipedia.org/wiki/{slug}")
        except Exception as e:
            print(f"Wikipedia search warning: {e}")
        return urls

    # ─── 4. Free Fallback: arXiv API ──────────────────────────────────

    def search_arxiv(self, query: str, max_results: int = 5) -> List[str]:
        """Free arXiv API query for peer-reviewed preprints and research papers."""
        urls = []
        try:
            clean_q = re.sub(r"[^\w\s]", "", query)
            endpoint = "https://export.arxiv.org/api/query"
            params = {
                "search_query": f"all:{clean_q}",
                "start": 0,
                "max_results": max_results
            }
            resp = requests.get(endpoint, params=params, headers=self.headers, timeout=12)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns):
                    link = entry.find("atom:id", ns)
                    if link is not None and link.text:
                        urls.append(link.text.strip())
        except Exception as e:
            print(f"arXiv search warning: {e}")
        return urls

    # ─── 5. Free Fallback: PubMed (PMC) Open API ──────────────────────

    def search_pubmed(self, query: str, max_results: int = 5) -> List[str]:
        """Free NCBI E-utilities search for medical & life science research papers."""
        urls = []
        try:
            clean_q = re.sub(r"[^\w\s]", "", query)
            endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pmc",
                "term": clean_q,
                "retmode": "json",
                "retmax": max_results
            }
            resp = requests.get(endpoint, params=params, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                id_list = resp.json().get("esearchresult", {}).get("idlist", [])
                for pmcid in id_list:
                    urls.append(f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/")
        except Exception as e:
            print(f"PubMed search warning: {e}")
        return urls

    # ─── 6. Brave Search API (Optional) ──────────────────────────────

    def search_brave(self, query: str, max_results: int = 10) -> List[str]:
        """Queries Brave Search API if API key is configured."""
        if not self.brave_api_key:
            return []
        urls = []
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {**self.headers, "X-Subscription-Token": self.brave_api_key}
            params = {"q": query, "count": min(20, max_results)}
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get("web", {}).get("results", []):
                    link = item.get("url")
                    if link:
                        clean = normalize_url(link)
                        if clean:
                            urls.append(clean)
        except Exception as e:
            print(f"Brave Search warning: {e}")
        return urls

    # ─── Unified Multi-Engine Discovery ───────────────────────────────

    def discover(self, query: str, target_count: int = 10) -> List[str]:
        """
        Discovers URLs for a given query across available search providers.
        Hierarchy:
        1. Google Custom Search (if API keys set)
        2. DuckDuckGo HTML
        3. Wikipedia API (for domain authority facts)
        4. arXiv & PubMed (for academic/scientific queries)
        """
        discovered = []
        seen = set()

        def add_urls(urls: List[str]):
            for u in urls:
                norm = normalize_url(u)
                if norm and norm not in seen and norm.startswith("http"):
                    seen.add(norm)
                    discovered.append(norm)

        # 1. Primary: Google API
        if self.google_api_key and self.google_engine_id:
            google_urls = self.search_google(query, max_results=target_count)
            add_urls(google_urls)

        # 2. Brave API (if present)
        if len(discovered) < target_count and self.brave_api_key:
            brave_urls = self.search_brave(query, max_results=target_count)
            add_urls(brave_urls)

        # 3. DuckDuckGo fallback
        if len(discovered) < target_count:
            ddg_urls = self.search_duckduckgo(query, max_results=target_count)
            add_urls(ddg_urls)

        # 4. Wikipedia fallback
        if len(discovered) < target_count:
            wiki_urls = self.search_wikipedia(query, max_results=3)
            add_urls(wiki_urls)

        # 5. Academic/Research fallback (arXiv / PubMed)
        if len(discovered) < target_count:
            arxiv_urls = self.search_arxiv(query, max_results=3)
            add_urls(arxiv_urls)

        return discovered[:target_count]
