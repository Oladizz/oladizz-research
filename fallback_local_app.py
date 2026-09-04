import os
import time
import json
import sqlite3
import hashlib
import urllib.parse
import numpy as np
import requests
from bs4 import BeautifulSoup
import trafilatura
import google.generativeai as genai
import markdown
from weasyprint import HTML
from datetime import datetime

DB_FILE = "local_research.db"

# ==========================================
# DATABASE SETUP
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY, domain TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pages (content_hash TEXT PRIMARY KEY, url TEXT, domain TEXT, raw_text TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY AUTOINCREMENT, claim TEXT, subject TEXT, numbers TEXT, source_url TEXT, source_domain TEXT, status TEXT, cluster_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS clusters (id INTEGER PRIMARY KEY AUTOINCREMENT, representative_claim TEXT, confidence_score REAL, source_count INTEGER, sources TEXT, had_contradictions BOOLEAN, status TEXT)''')
    conn.commit()
    return conn

# ==========================================
# STAGE 1: SEARCH & QUERY EXPANDER
# ==========================================
def generate_queries(topic, model, count=5):
    print(f"\n--- STAGE 1a: Expanding topic into {count} search queries ---")
    prompt = f"Generate {count} distinct search engine queries to comprehensively research: '{topic}'. Return ONLY a JSON list of strings. Format: [\"query1\", \"query2\"]"
    try:
        resp = model.generate_content(prompt, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
        queries = json.loads(resp.text)
        print(f"Generated queries: {queries}")
        return queries
    except Exception as e:
        print(f"Failed to expand queries: {e}")
        return [topic]

def run_search(conn, queries, target_urls_per_query=10):
    print(f"\n--- STAGE 1b: Searching DuckDuckGo for {len(queries)} queries ---")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = "https://html.duckduckgo.com/html/"
    
    discovered = set()
    c = conn.cursor()
    
    for query in queries:
        print(f"Searching: '{query}'...")
        payload = {'q': query, 'b': ''}
        try:
            response = requests.post(url, data=payload, headers=headers)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                results = soup.find_all('a', class_='result__url')
                
                count = 0
                for result in results:
                    if count >= target_urls_per_query: break
                    href = result.get('href')
                    if href and href.startswith('http'):
                        domain = urllib.parse.urlparse(href).netloc.replace("www.", "")
                        discovered.add((href, domain))
                        count += 1
        except Exception as e:
            print(f"Search failed for '{query}': {e}")
            
        time.sleep(3) # Polite delay between searches
        
    for href, domain in discovered:
        try:
            c.execute("INSERT INTO urls (url, domain, status) VALUES (?, ?, 'pending')", (href, domain))
        except sqlite3.IntegrityError:
            pass # Already exists
            
    conn.commit()
    print(f"Saved {len(discovered)} unique URLs to local database.")

# ==========================================
# STAGE 2 & 3: FETCH & DEDUP
# ==========================================
def run_fetch(conn):
    print("\n--- STAGE 2 & 3: Fetching and Cleaning Pages ---")
    c = conn.cursor()
    c.execute("SELECT url, domain FROM urls WHERE status='pending'")
    urls = c.fetchall()
    
    for url, domain in urls:
        print(f"Fetching: {url}")
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text:
                content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                try:
                    c.execute("INSERT INTO pages (content_hash, url, domain, raw_text, status) VALUES (?, ?, ?, ?, 'ready')", 
                              (content_hash, url, domain, text))
                    c.execute("UPDATE urls SET status='fetched' WHERE url=?", (url,))
                    print("  -> Saved clean text.")
                except sqlite3.IntegrityError:
                    print("  -> Duplicate content (syndicated). Skipping.")
                    c.execute("UPDATE urls SET status='duplicate' WHERE url=?", (url,))
        else:
            print("  -> Failed to download.")
            c.execute("UPDATE urls SET status='failed' WHERE url=?", (url,))
            
        conn.commit()
        time.sleep(2) # Polite delay for local fetching

# ==========================================
# STAGE 4: AI EXTRACT
# ==========================================
def run_extract(conn, model):
    print("\n--- STAGE 4: AI Claim Extraction ---")
    c = conn.cursor()
    c.execute("SELECT content_hash, raw_text, url, domain FROM pages WHERE status='ready' LIMIT 10")
    pages = c.fetchall()
    
    for content_hash, raw_text, url, domain in pages:
        print(f"Extracting claims from: {url}")
        prompt = f"""Extract specific factual claims from this text. 
        Format as JSON array of objects: [{{"claim": "...", "subject": "...", "numbers": ["..."], "source_url": "{url}", "source_domain": "{domain}"}}]
        Text: {raw_text[:20000]}"""
        
        try:
            resp = model.generate_content(prompt, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
            claims = json.loads(resp.text)
            for claim in claims:
                numbers = json.dumps(claim.get('numbers', []))
                c.execute("INSERT INTO claims (claim, subject, numbers, source_url, source_domain, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                          (claim.get('claim'), claim.get('subject'), numbers, url, domain))
            c.execute("UPDATE pages SET status='extracted' WHERE content_hash=?", (content_hash,))
            conn.commit()
            print(f"  -> Extracted {len(claims)} claims.")
        except Exception as e:
            print(f"  -> Extraction failed: {e}")
            c.execute("UPDATE pages SET status='failed' WHERE content_hash=?", (content_hash,))
            conn.commit()
            
        print("Sleeping 4.5s for Free Tier RPM limits...")
        time.sleep(4.5)

# ==========================================
# STAGE 5 & 8: CLUSTER & SCORE
# ==========================================
def run_score(conn, model):
    print("\n--- STAGE 5 & 8: Clustering and Scoring ---")
    c = conn.cursor()
    c.execute("SELECT id, claim, source_domain FROM claims WHERE status='pending'")
    rows = c.fetchall()
    if not rows:
        return
        
    print(f"Generating embeddings for {len(rows)} claims...")
    texts = [r[1] for r in rows]
    
    try:
        emb_resp = genai.embed_content(model="models/gemini-embedding-2", content=texts)
        embeddings = emb_resp['embedding']
    except Exception as e:
        print(f"Embedding failed: {e}")
        return
        
    clusters = []
    used = set()
    
    for i in range(len(rows)):
        if i in used: continue
        current_cluster = [rows[i]]
        used.add(i)
        for j in range(i + 1, len(rows)):
            if j in used: continue
            sim = np.dot(embeddings[i], embeddings[j]) / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]))
            if sim > 0.85:
                current_cluster.append(rows[j])
                used.add(j)
        clusters.append(current_cluster)
        
    for cluster in clusters:
        domains = list(set([r[2] for r in cluster]))
        claim_texts = [r[1] for r in cluster]
        
        # Mock contradiction check
        contradiction_penalty = 0.0
        if len(claim_texts) > 1:
            try:
                resp = model.generate_content(f"Do these claims contradict? Return JSON {{\"has_contradiction\": true/false}}. Claims: {json.dumps(claim_texts)}", 
                                              generation_config=genai.GenerationConfig(response_mime_type="application/json"))
                if json.loads(resp.text).get("has_contradiction"):
                    contradiction_penalty = 0.5
            except:
                pass
            time.sleep(4.5)
            
        # Score
        base = 0.8
        src_mult = min(1.0, 0.5 + (0.1 * len(domains)))
        credibility = 0.7 # Local mock credibility
        score = round((base * src_mult * credibility * (1.0 - contradiction_penalty)) * 100, 1)
        
        c.execute("INSERT INTO clusters (representative_claim, confidence_score, source_count, sources, had_contradictions, status) VALUES (?, ?, ?, ?, ?, 'ready')",
                  (claim_texts[0], score, len(domains), json.dumps(domains), contradiction_penalty > 0))
        cluster_id = c.lastrowid
        
        for r in cluster:
            c.execute("UPDATE claims SET status='scored', cluster_id=? WHERE id=?", (cluster_id, r[0]))
            
    conn.commit()
    print("Scoring complete.")

# ==========================================
# STAGE 9 & 11: SYNTHESIZE & PDF
# ==========================================
def run_synthesis(conn):
    print("\n--- STAGE 9 & 11: Synthesis & PDF Generation ---")
    c = conn.cursor()
    c.execute("SELECT representative_claim, confidence_score, sources, had_contradictions FROM clusters WHERE status='ready' AND confidence_score >= 60.0 ORDER BY confidence_score DESC")
    clusters = c.fetchall()
    
    md = f"# Local Fallback Research Report\n**Generated:** {datetime.now().strftime('%Y-%m-%d')}\n---\n\n"
    
    for claim, score, sources_json, had_contra in clusters:
        sources = json.loads(sources_json)
        indicator = "🟢" if score >= 85 else "🟡"
        md += f"### {indicator} {score}% Confidence\n**{claim}**\n- **Sources ({len(sources)}):** {', '.join(sources)}\n"
        if had_contra:
            md += "- ⚠️ *Conflicting details penalized.*\n"
        md += "\n---\n\n"
        
    md += "## Works Cited (Trusted Links)\n"
    c.execute("SELECT DISTINCT source_url FROM claims WHERE source_url IS NOT NULL")
    for (url,) in c.fetchall():
        md += f"- {url}\n"
        
    html = markdown.markdown(md)
    styled = f"<html><head><style>body {{ font-family: sans-serif; line-height: 1.6; margin: 2em; }}</style></head><body>{html}</body></html>"
    
    pdf_path = "local_report.pdf"
    HTML(string=styled).write_pdf(pdf_path)
    print(f"PDF Generated: {pdf_path}")
    
    # Export Trusted Links
    c.execute("SELECT DISTINCT source_url FROM claims WHERE source_url IS NOT NULL")
    trusted_urls = c.fetchall()
    with open("trusted_links.txt", "w") as f:
        f.write("=== TRUSTED RESEARCH LINKS ===\n")
        for (url,) in trusted_urls:
            f.write(url + "\n")
    print(f"Saved {len(trusted_urls)} trusted URLs to trusted_links.txt")
    
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        print("Sending to Telegram...")
        requests.post(f"https://api.telegram.org/bot{bot_token}/sendDocument", files={'document': open(pdf_path, 'rb')}, data={'chat_id': chat_id, 'caption': '📊 Local Fallback Report'})
        print("Sent!")
    else:
        print("TELEGRAM_BOT_TOKEN or CHAT_ID not set. Skipping Telegram.")

if __name__ == "__main__":
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is required.")
        exit(1)
        
    genai.configure(api_key=api_key)
    model_extract = genai.GenerativeModel('gemini-3.5-flash-lite')
    model_cluster = genai.GenerativeModel('gemini-3.7-flash')
    
    conn = init_db()
    
    # 1. Expand the topic into multiple distinct search queries
    queries = generate_queries("website must have", model_extract, count=5)
    
    # 2. Run searches for ALL queries (Finding up to 50 URLs)
    run_search(conn, queries, target_urls_per_query=10)
    
    run_fetch(conn)
    run_extract(conn, model_extract)
    run_score(conn, model_cluster)
    run_synthesis(conn)
    conn.close()
    print("\nLocal Fallback Pipeline Finished Successfully.")
