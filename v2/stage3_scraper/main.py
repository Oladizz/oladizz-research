import os
import sys
import hashlib
import re
from flask import Flask, request
import trafilatura
from google.cloud import firestore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ScrapedPage

app = Flask(__name__)
db = firestore.Client(project=GCP_PROJECT)

def get_shingles(text, k=3):
    words = re.findall(r'\w+', text.lower())
    return [" ".join(words[i:i+k]) for i in range(len(words) - k + 1)]

def compute_simhash(text) -> str:
    shingles = get_shingles(text)
    v = [0] * 64
    for shingle in shingles:
        h = int(hashlib.md5(shingle.encode('utf-8')).hexdigest(), 16)
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1
    ans = 0
    for i in range(64):
        if v[i] > 0:
            ans |= (1 << i)
    return hex(ans)[2:].zfill(16)

def hamming_distance(h1_str: str, h2_str: str) -> int:
    h1 = int(h1_str, 16)
    h2 = int(h2_str, 16)
    x = (h1 ^ h2) & ((1 << 64) - 1)
    return bin(x).count('1')

@app.route("/", methods=["POST"])
def scrape():
    data = request.get_json()
    if not data:
        return "No json data", 400
    
    url = data.get("url")
    domain = data.get("domain")
    run_id = data.get("run_id")

    if not all([url, domain, run_id]):
        return "Missing required fields", 400
    
    url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    seen_ref = db.collection(FS_SEEN_HASHES).document(url_hash)
    if seen_ref.get().exists:
        return "URL already seen", 200
        
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return "Fetch failed", 200
        
    text = trafilatura.extract(downloaded)
    if not text:
        return "Extraction failed", 200
        
    simhash_val = compute_simhash(text)
    
    seen_ref.set({"url": url, "added_at": firestore.SERVER_TIMESTAMP})
    
    page = ScrapedPage(
        url=url,
        domain=domain,
        run_id=run_id,
        url_hash=url_hash,
        content_hash=simhash_val,
        raw_text=text,
        char_count=len(text)
    )
    db.collection(FS_SCRAPED_PAGES).add(page.to_dict())
    
    return "OK", 200

def run_batch(run_id: str, limit: int = 50):
    print(f"Running Stage 3 Batch Scraper for run: {run_id}")
    urls_ref = db.collection(FS_DISCOVERED_URLS).where("run_id", "==", run_id).limit(limit)
    docs = list(urls_ref.stream())
    print(f"Found {len(docs)} discovered URLs to scrape.")
    
    scraped_count = 0
    for doc in docs:
        d = doc.to_dict()
        url = d.get("url")
        domain = d.get("domain")
        print(f"Scraping: {url} ({domain})...")
        
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        seen_ref = db.collection(FS_SEEN_HASHES).document(url_hash)
        if seen_ref.get().exists:
            print("  -> Already seen, skipping.")
            continue
            
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                print("  -> Fetch failed.")
                continue
            text = trafilatura.extract(downloaded)
            if not text:
                print("  -> Extraction failed.")
                continue
                
            simhash_val = compute_simhash(text)
            seen_ref.set({"url": url, "added_at": firestore.SERVER_TIMESTAMP})
            
            page = ScrapedPage(
                url=url,
                domain=domain,
                run_id=run_id,
                url_hash=url_hash,
                content_hash=simhash_val,
                raw_text=text,
                char_count=len(text)
            )
            db.collection(FS_SCRAPED_PAGES).add(page.to_dict())
            scraped_count += 1
            print(f"  -> Successfully scraped ({len(text)} chars).")
        except Exception as e:
            print(f"  -> Error: {e}")
            
    print(f"Stage 3 Batch complete. Successfully scraped {scraped_count} pages to Firestore.")

if __name__ == "__main__":
    if os.environ.get("BATCH_MODE", "false").lower() == "true":
        run_batch(os.environ.get("RUN_ID", "default-run"))
    else:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
