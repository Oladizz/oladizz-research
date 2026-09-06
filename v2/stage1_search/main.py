"""
Stage 1 — Search & Discovery (Production, Zero-AI default)

Uses template-based query expansion by default.
Falls back to Gemini only if USE_AI_QUERY_EXPANSION=true is set.
"""
import os
import sys
import json
import hashlib
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import requests
from bs4 import BeautifulSoup

from google.cloud import firestore

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import DiscoveredURL

# Import zero-AI query expander
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))
try:
    from query_expander import expand_topic
except ImportError:
    expand_topic = None

try:
    from search_engine import MultiSearchEngine
except ImportError:
    MultiSearchEngine = None

# Optional AI imports
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking params, www, trailing slashes, and fragments."""
    parsed = urlparse(url)

    # Lowercase the domain
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]

    # Strip fragment
    parsed = parsed._replace(fragment='', netloc=netloc)

    # Strip tracking params (utm_*, fbclid, gclid, etc.)
    if parsed.query:
        tracking_prefixes = ('utm_', 'fbclid', 'gclid', 'ref', 'source', 'campaign')
        qsl = parse_qsl(parsed.query)
        filtered_qsl = [(k, v) for k, v in qsl if not any(k.startswith(p) for p in tracking_prefixes)]
        parsed = parsed._replace(query=urlencode(filtered_qsl))

    clean_url = urlunparse(parsed)

    # Strip trailing slash
    if clean_url.endswith('/'):
        clean_url = clean_url[:-1]

    return clean_url


def expand_topic_code(topic: str, count: int = 15) -> list[str]:
    """Expand topic using code-only synonym templates. Zero AI cost."""
    if expand_topic is not None:
        return expand_topic(topic, count)

    # Inline fallback if utils not available yet
    modifiers = ["best", "top", "essential", "critical", "guide", "checklist",
                 "examples", "2026", "for business", "for startups"]
    queries = [topic]
    for mod in modifiers:
        queries.append(f"{topic} {mod}")
        if len(queries) >= count:
            break
    return queries[:count]


def expand_topic_ai(topic: str) -> list[str]:
    """Expand topic using Gemini. Costs AI tokens."""
    if not HAS_GENAI or not GEMINI_API_KEY:
        print("  AI expansion unavailable, falling back to code expansion.")
        return expand_topic_code(topic)

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_EXTRACT)

    prompt = f"""Generate exactly {SEARCH_QUERIES_PER_TOPIC} diverse search queries to research: '{topic}'.
Include rephrasings, different angles, and geographical variants.
Return ONLY a JSON array of strings."""

    try:
        response = model.generate_content(prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json"))
        time.sleep(GEMINI_FREE_TIER_DELAY)
        queries = json.loads(response.text)
        return queries[:SEARCH_QUERIES_PER_TOPIC]
    except Exception as e:
        print(f"  AI expansion failed: {e}. Falling back to code.")
        return expand_topic_code(topic)


def search_google_api(query: str) -> list[str]:
    """Search using Google Custom Search API."""
    urls = []
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": SEARCH_API_KEY,
            "cx": SEARCH_ENGINE_ID,
            "q": query,
            "num": min(10, SEARCH_RESULTS_PER_QUERY)
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            link = item.get("link")
            if link:
                urls.append(link)
    except Exception as e:
        print(f"  Google API search failed for '{query}': {e}")
    return urls


def search_ddg_html(query: str) -> list[str]:
    """Fallback: Scrape DuckDuckGo HTML."""
    urls = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        data = {'q': query}
        resp = requests.post(DDG_URL, data=data, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        for a in soup.select('.result__url'):
            href = a.get('href')
            if href:
                if href.startswith('//'):
                    urls.append('https:' + href)
                elif href.startswith('http'):
                    urls.append(href)
    except Exception as e:
        print(f"  DDG search failed for '{query}': {e}")

    return urls[:DDG_RESULTS_PER_QUERY]


def main():
    topic = os.environ.get("RESEARCH_TOPIC")
    run_id = os.environ.get("RUN_ID")

    if not topic or not run_id:
        print("Error: RESEARCH_TOPIC and RUN_ID must be set.")
        sys.exit(1)

    print("=== STAGE 1: Search & Discovery ===")
    print(f"Run: {run_id} | Topic: '{topic}'")

    # Decide: code-only or AI-assisted query expansion
    use_ai = os.environ.get("USE_AI_QUERY_EXPANSION", "false").lower() == "true"
    if use_ai:
        print("Mode: AI-assisted query expansion (costs tokens)")
        queries = expand_topic_ai(topic)
    else:
        print("Mode: Code-only query expansion (zero cost)")
        queries = expand_topic_code(topic)

    print(f"Generated {len(queries)} queries:")
    for i, q in enumerate(queries):
        print(f"  {i+1}. {q}")

    # Initialize Firestore & MultiSearchEngine
    db = firestore.Client(project=GCP_PROJECT, database="(default)")
    search_engine = MultiSearchEngine(
        google_api_key=SEARCH_API_KEY,
        google_engine_id=SEARCH_ENGINE_ID
    ) if MultiSearchEngine else None

    unique_urls = {}

    for query in queries:
        print(f"\nSearching: '{query}'...")

        if search_engine:
            urls = search_engine.discover(query, target_count=SEARCH_RESULTS_PER_QUERY)
        elif SEARCH_API_KEY and SEARCH_ENGINE_ID:
            urls = search_google_api(query)
        else:
            urls = search_ddg_html(query)

        print(f"  Found {len(urls)} URLs")

        for u in urls:
            norm_url = normalize_url(u)
            if norm_url not in unique_urls:
                unique_urls[norm_url] = query

        time.sleep(SEARCH_DELAY)

    print(f"\nTotal unique URLs discovered: {len(unique_urls)}")

    # Enforce Free Tier hard limit
    url_items = list(unique_urls.items())
    if len(url_items) > MAX_URLS_PER_RUN:
        print(f"Capping at {MAX_URLS_PER_RUN} URLs to protect GCP Free Tier.")
        url_items = url_items[:MAX_URLS_PER_RUN]

    # Save to Firestore in batches of 500
    batch = db.batch()
    batch_count = 0

    for url, query in url_items:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        doc_ref = db.collection(FS_DISCOVERED_URLS).document(url_hash)

        discovered = DiscoveredURL(
            url=url,
            domain=domain,
            query_used=query,
            run_id=run_id
        )

        batch.set(doc_ref, discovered.to_dict())
        batch_count += 1

        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        batch.commit()

    print(f"Stage 1 complete. {len(unique_urls)} URLs saved to Firestore.")


if __name__ == "__main__":
    main()
