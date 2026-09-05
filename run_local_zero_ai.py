import os
import sys
import time
import sqlite3
import hashlib
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import trafilatura

# Add v2 utilities to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'v2')))
from utils.query_expander import expand_topic
from utils.spacy_extractor import extract_claims_from_text
try:
    from utils.hdbscan_cluster import cluster_claims, pick_representative
except ImportError:
    HAS_HDBSCAN = False

def init_db():
    conn = sqlite3.connect('local_zero_ai.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS claims
                 (id TEXT PRIMARY KEY, claim TEXT, subject TEXT, numbers TEXT, url TEXT, domain TEXT)''')
    conn.commit()
    return conn

def search_ddg(query, max_results=3):
    urls = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.post("https://html.duckduckgo.com/html/", data={'q': query}, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.select('.result__url')[:max_results]:
            href = a.get('href')
            if href:
                urls.append('https:' + href if href.startswith('//') else href)
    except Exception as e:
        print(f"Search failed: {e}")
    return urls

def main(topic):
    print(f"=== ZERO-AI LOCAL PIPELINE ===")
    print(f"Topic: {topic}\n")
    
    conn = init_db()
    c = conn.cursor()
    
    # 1. Expand Queries (Code-only)
    print("[1/5] Expanding queries using local synonym templates...")
    queries = expand_topic(topic, count=3)
    print(f"  Generated: {queries}")
    
    # 2. Search (DuckDuckGo HTML Scraping)
    print("\n[2/5] Searching DuckDuckGo...")
    unique_urls = set()
    for q in queries:
        urls = search_ddg(q, max_results=3)
        unique_urls.update(urls)
        time.sleep(1) # Be nice to DDG
    print(f"  Found {len(unique_urls)} unique URLs.")
    
    # 3. Scrape & Extract (spaCy + Regex)
    print("\n[3/5] Scraping pages and extracting facts (spaCy NER)...")
    all_claims = []
    
    for url in list(unique_urls)[:5]: # Limit to 5 for speed test
        print(f"  -> Scraping: {url}")
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            continue
        text = trafilatura.extract(downloaded)
        if not text:
            continue
            
        domain = urlparse(url).netloc.replace('www.', '')
        
        # Zero-AI Extraction
        claims = extract_claims_from_text(text[:20000], url, domain)
        print(f"     Extracted {len(claims)} factual claims.")
        
        for claim in claims:
            claim_id = hashlib.md5(claim['claim'].encode()).hexdigest()
            try:
                c.execute("INSERT OR IGNORE INTO claims VALUES (?, ?, ?, ?, ?, ?)",
                          (claim_id, claim['claim'], claim['subject'], str(claim['numbers']), url, domain))
                conn.commit()
                all_claims.append(claim)
            except Exception as e:
                pass
                
    print(f"\n  Total factual claims extracted: {len(all_claims)}")
    
    # 4. Clustering (HDBSCAN / TF-IDF)
    print("\n[4/5] Clustering claims (TF-IDF + HDBSCAN)...")
    texts = [c['claim'] for c in all_claims]
    if len(texts) > 2:
        try:
            clusters_indices = cluster_claims(texts, min_cluster_size=2)
            print(f"  Formed {len(clusters_indices)} verified clusters.")
        except Exception as e:
            print(f"  Clustering skipped/failed: {e}")
            clusters_indices = [[i] for i in range(len(texts))] # Fallback: each is its own cluster
    else:
        clusters_indices = [[i] for i in range(len(texts))]
        
    # 5. Output Report
    print("\n[5/5] Generating Report...")
    report_path = "local_zero_ai_report.md"
    with open(report_path, "w") as f:
        f.write(f"# Research Report: {topic}\n\n")
        f.write("> Generated 100% locally with Zero API calls (spaCy + TF-IDF).\n\n")
        
        for idx, indices in enumerate(clusters_indices):
            cluster_claims_list = [all_claims[i] for i in indices]
            domains = set(c.get('source_domain', '') for c in cluster_claims_list)
            
            # Simple Scoring
            score = min(100, len(domains) * 20 + 20)
            
            f.write(f"### Claim {idx+1} (Confidence: {score}%)\n")
            f.write(f"**{cluster_claims_list[0]['claim']}**\n\n")
            f.write(f"**Sources ({len(domains)} independent):**\n")
            for d in domains:
                f.write(f"- {d}\n")
            f.write("\n---\n")
            
    print(f"\nDone! Report saved to {report_path}")
    
if __name__ == "__main__":
    main("website must have features")
