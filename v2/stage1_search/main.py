import os
import sys
import json
import hashlib
import time
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import requests
from bs4 import BeautifulSoup

from google.cloud import firestore
import google.generativeai as genai

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import DiscoveredURL

def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking params, trailing slashes, and fragments."""
    parsed = urlparse(url)
    
    # Strip fragment
    parsed = parsed._replace(fragment='')
    
    # Strip tracking params (e.g., utm_)
    if parsed.query:
        qsl = parse_qsl(parsed.query)
        filtered_qsl = [(k, v) for k, v in qsl if not k.startswith('utm_')]
        parsed = parsed._replace(query=urlencode(filtered_qsl))
        
    # Rebuild URL
    clean_url = urlunparse(parsed)
    
    # Strip trailing slash
    if clean_url.endswith('/'):
        clean_url = clean_url[:-1]
        
    return clean_url

def expand_topic_queries(topic: str) -> list[str]:
    """Expand topic into 10 diverse search queries using Gemini."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_EXTRACT)
    
    prompt = f"""
    You are an expert researcher. Expand the following research topic into exactly {SEARCH_QUERIES_PER_TOPIC} diverse search queries.
    Include rephrasings, different angles, and relevant geographical variants if applicable.
    Return ONLY a JSON array of strings. Do not include markdown code blocks or any other text.
    
    Topic: {topic}
    """
    
    print("Calling Gemini to expand topic...")
    response = model.generate_content(prompt)
    time.sleep(GEMINI_FREE_TIER_DELAY) # Respect rate limits
    
    try:
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        
        queries = json.loads(text)
        if not isinstance(queries, list):
            queries = [str(q) for q in queries]
        return queries[:SEARCH_QUERIES_PER_TOPIC]
    except Exception as e:
        print(f"Error parsing Gemini response: {e}. Falling back to topic.")
        return [topic]

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
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            urls.append(item.get("link"))
    except Exception as e:
        print(f"Google API search failed for '{query}': {e}")
    return urls

def search_ddg_html(query: str) -> list[str]:
    """Fallback: Scrape DuckDuckGo HTML."""
    urls = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        data = {'q': query}
        resp = requests.post(DDG_URL, data=data, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for a in soup.select('.result__url'):
            href = a.get('href')
            if href:
                if href.startswith('//'):
                    urls.append('https:' + href)
                else:
                    urls.append(href)
    except Exception as e:
        print(f"DDG search failed for '{query}': {e}")
    
    return urls[:DDG_RESULTS_PER_QUERY]

def main():
    topic = os.environ.get("RESEARCH_TOPIC")
    run_id = os.environ.get("RUN_ID")
    
    if not topic or not run_id:
        print("Error: RESEARCH_TOPIC and RUN_ID must be set.")
        sys.exit(1)
        
    print(f"Starting Stage 1 for run '{run_id}', topic: '{topic}'")
    
    queries = expand_topic_queries(topic)
    print(f"Generated {len(queries)} queries:")
    for i, q in enumerate(queries):
        print(f"  {i+1}. {q}")
        
    db = firestore.Client(project=GCP_PROJECT, database="(default)")
    
    unique_urls = {}
    
    for query in queries:
        print(f"Searching for: {query}")
        
        if SEARCH_API_KEY and SEARCH_ENGINE_ID:
            urls = search_google_api(query)
        else:
            urls = search_ddg_html(query)
            
        print(f"  Found {len(urls)} URLs")
        
        for u in urls:
            norm_url = normalize_url(u)
            if norm_url not in unique_urls:
                unique_urls[norm_url] = query
                
        time.sleep(SEARCH_DELAY)
        
    print(f"Total unique URLs discovered: {len(unique_urls)}")
    
    # Save to Firestore
    batch = db.batch()
    batch_count = 0
    
    for url, query in unique_urls.items():
        domain = urlparse(url).netloc
        
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
        
    print("Stage 1 complete. Saved to Firestore.")

if __name__ == "__main__":
    main()
