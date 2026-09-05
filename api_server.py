"""
Universal API & Web Dashboard Server for Truth-Filtering Research Pipeline.
Deployable on Render, Railway, Heroku, Google Cloud Run, or Docker.
"""
import numpy as np
import os
import sys
import uuid
import threading
import sqlite3
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string, send_file

# Add v2 and utils to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'v2')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'v2', 'utils')))

from utils.query_expander import expand_topic
from utils.ai_router import AIRouter
try:
    from utils.hdbscan_cluster import cluster_claims
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

import trafilatura
from bs4 import BeautifulSoup
import requests

app = Flask(__name__)

# Persistent in-memory & SQLite run status store
RUNS = {}

def get_db():
    conn = sqlite3.connect("research_runs.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                topic TEXT,
                status TEXT,
                mode TEXT,
                urls_discovered INTEGER DEFAULT 0,
                pages_scraped INTEGER DEFAULT 0,
                claims_extracted INTEGER DEFAULT 0,
                clusters_formed INTEGER DEFAULT 0,
                report_md TEXT,
                created_at TEXT
            )
        """)
init_db()

def search_ddg(query: str, max_results: int = 5) -> list[str]:
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
        print(f"Search warning: {e}")
    return urls

def execute_pipeline(run_id: str, topic: str, max_urls: int = 15, preferred_provider: str = ""):
    conn = get_db()
    router = AIRouter(preferred_provider=preferred_provider)
    try:
        RUNS[run_id] = {
            "status": "searching",
            "topic": topic,
            "mode": router.provider_label,
            "progress": f"Discovering URLs (using {router.provider_label})..."
        }
        
        # 1. Search & Discovery
        queries = router.expand_topic(topic, count=4)
        unique_urls = set()
        for q in queries:
            urls = search_ddg(q, max_results=3)
            unique_urls.update(urls)
            if len(unique_urls) >= max_urls:
                break
                
        candidate_urls = list(unique_urls)[:max_urls]
        RUNS[run_id]["urls_discovered"] = len(candidate_urls)
        RUNS[run_id]["status"] = "scraping"
        RUNS[run_id]["progress"] = f"Scraping {len(candidate_urls)} candidate articles..."
        
        # 2. Scrape & Extract
        all_claims = []
        pages_scraped = 0
        
        for url in candidate_urls:
            try:
                downloaded = trafilatura.fetch_url(url)
                if not downloaded:
                    continue
                text = trafilatura.extract(downloaded)
                if not text:
                    continue
                pages_scraped += 1
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
                
                claims = router.extract_claims(text[:25000], url, domain)
                all_claims.extend(claims)
            except Exception as e:
                print(f"Error scraping {url}: {e}")
                
        RUNS[run_id]["pages_scraped"] = pages_scraped
        RUNS[run_id]["claims_extracted"] = len(all_claims)
        RUNS[run_id]["status"] = "clustering"
        RUNS[run_id]["progress"] = f"Clustering {len(all_claims)} extracted facts..."
        
        # 3. Clustering
        texts = [c["claim"] for c in all_claims]
        clusters_indices = []
        if len(texts) >= 2 and HAS_HDBSCAN:
            try:
                clusters_indices = cluster_claims(texts, min_cluster_size=2)
            except Exception:
                clusters_indices = [[i] for i in range(len(texts))]
        else:
            clusters_indices = [[i] for i in range(len(texts))]
            
        RUNS[run_id]["clusters_formed"] = len(clusters_indices)
        RUNS[run_id]["status"] = "synthesizing"
        RUNS[run_id]["progress"] = "Generating research dossier..."
        
        # 4. Generate Report
        report_lines = [
            f"# Research Report: {topic}",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Engine Mode:** {router.provider_label}  ",
            f"**Verified Claims:** {len(all_claims)} from {pages_scraped} source pages\n",
            "## Key Findings\n"
        ]
        
        for idx, indices in enumerate(clusters_indices[:20]):
            cluster_items = [all_claims[i] for i in indices]
            domains = list(set(c.get("source_domain", "") for c in cluster_items if c.get("source_domain")))
            score = min(100, len(domains) * 20 + 20)
            badge = "🟢" if score >= 80 else "🟡"
            
            report_lines.append(f"### {badge} Claim #{idx+1} (Confidence: {score}%)")
            report_lines.append(f"**{cluster_items[0]['claim']}**\n")
            if domains:
                report_lines.append(f"*Sources ({len(domains)} independent):* {', '.join(domains)}\n")
            report_lines.append("---\n")
            
        report_md = "\n".join(report_lines)
        
        # Save to SQLite
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO runs 
                (run_id, topic, status, mode, urls_discovered, pages_scraped, claims_extracted, clusters_formed, report_md, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, topic, "completed", router.provider, len(candidate_urls), pages_scraped, len(all_claims), len(clusters_indices), report_md, datetime.now(timezone.utc).isoformat()))
            
        RUNS[run_id]["status"] = "completed"
        RUNS[run_id]["progress"] = "Research dossier ready!"
        RUNS[run_id]["report_md"] = report_md
        
    except Exception as e:
        RUNS[run_id]["status"] = "failed"
        RUNS[run_id]["error"] = str(e)
        print(f"Pipeline error for run {run_id}: {e}")

# ─── HTTP Endpoints ─────────────────────────────────────────

@app.route("/health")
def health():
    active_router = AIRouter()
    return jsonify({
        "status": "healthy",
        "service": "truth-filtering-research-pipeline",
        "version": "2.0.0",
        "active_ai_provider": active_router.provider,
        "active_ai_label": active_router.provider_label,
        "supported_ais": ["openai", "anthropic", "gemini", "zero-ai-local"],
        "platform_support": ["render", "railway", "heroku", "gcp", "cloudflare", "docker"]
    })

@app.route("/api/research", methods=["POST"])
def start_research():
    data = request.get_json() or {}
    topic = data.get("topic") or request.form.get("topic")
    if not topic:
        return jsonify({"error": "Missing 'topic' field"}), 400
        
    max_urls = int(data.get("max_urls", 15))
    preferred_provider = data.get("provider") or data.get("engine_mode") or ""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    
    active_router = AIRouter(preferred_provider=preferred_provider)
    RUNS[run_id] = {
        "run_id": run_id,
        "topic": topic,
        "mode": active_router.provider_label,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Run in background thread
    t = threading.Thread(target=execute_pipeline, args=(run_id, topic, max_urls, preferred_provider))
    t.daemon = True
    t.start()
    
    return jsonify({
        "message": "Research run started successfully",
        "run_id": run_id,
        "topic": topic,
        "mode": active_router.provider_label,
        "status_url": f"/api/research/{run_id}",
        "report_url": f"/api/research/{run_id}/report"
    }), 202

@app.route("/api/research/<run_id>")
def get_status(run_id):
    if run_id in RUNS:
        return jsonify(RUNS[run_id])
        
    conn = get_db()
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row:
        return jsonify(dict(row))
        
    return jsonify({"error": "Run not found"}), 404

@app.route("/api/research/<run_id>/report")
def get_report(run_id):
    report_md = None
    if run_id in RUNS and "report_md" in RUNS[run_id]:
        report_md = RUNS[run_id]["report_md"]
    else:
        conn = get_db()
        row = conn.execute("SELECT report_md FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row and row["report_md"]:
            report_md = row["report_md"]
            
    if not report_md:
        return jsonify({"error": "Report not ready or run not found"}), 404
        
    if request.args.get("format") == "json":
        return jsonify({"run_id": run_id, "markdown": report_md})
        
    return report_md, 200, {"Content-Type": "text/markdown; charset=utf-8"}

@app.route("/")
def dashboard():
    active_router = AIRouter()
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Truth-Filtering Research Engine</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <style>
            body { background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; }
            .btn-primary { background: #3b82f6; border: none; font-weight: 600; }
            .badge-green { background: #10b981; }
            pre { background: #0b1120; border-radius: 8px; padding: 16px; color: #94a3b8; }
        </style>
    </head>
    <body class="py-5">
        <div class="container" style="max-width: 860px;">
            <div class="text-center mb-5">
                <h1 class="fw-bold">🌐 Truth-Filtering Research Engine</h1>
                <p class="text-secondary">Scrapes, cross-checks facts across independent domains, and compiles textbook-grade dossiers.</p>
                <div class="mt-2">
                    <span class="badge bg-secondary p-2">Active AI: <strong class="text-info">{{ active_ai_label }}</strong></span>
                </div>
            </div>
            
            <div class="card p-4 shadow-lg mb-4">
                <form id="researchForm">
                    <div class="mb-3">
                        <label class="form-label fw-bold">Research Topic</label>
                        <input type="text" id="topicInput" class="form-control form-control-lg bg-dark text-light border-secondary" placeholder="e.g. Next-Generation Solid State Batteries 2026" required>
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Max Candidate Links</label>
                            <input type="number" id="maxUrls" class="form-control bg-dark text-light border-secondary" value="15" min="5" max="100">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">AI Engine Provider</label>
                            <select id="engineMode" class="form-select bg-dark text-light border-secondary">
                                <option value="">Auto-Detect ({{ active_ai_label }})</option>
                                <option value="none">Zero-AI Local Mode ($0.00 - spaCy & TF-IDF)</option>
                                <option value="openai">ChatGPT / OpenAI (GPT-4o-mini)</option>
                                <option value="anthropic">Claude / Anthropic (Claude 3.5 Haiku)</option>
                                <option value="gemini">Google Gemini (Gemini 3.5 Flash-Lite)</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary btn-lg w-100" id="submitBtn">Start Research Run</button>
                </form>
            </div>

            <div id="statusCard" class="card p-4 shadow-lg d-none">
                <h5 class="fw-bold mb-3" id="statusHeader">Run Progress</h5>
                <div class="progress mb-3" style="height: 12px;">
                    <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated bg-primary" style="width: 25%;"></div>
                </div>
                <p id="statusMsg" class="text-info fw-bold">Initializing...</p>
                <div id="statsBox" class="text-secondary small mb-3"></div>
                <div id="reportContainer" class="d-none mt-3">
                    <h6>Generated Dossier:</h6>
                    <pre id="reportContent" style="white-space: pre-wrap; max-height: 400px; overflow-y: auto;"></pre>
                    <a id="downloadBtn" class="btn btn-outline-info w-100" target="_blank">View Raw Markdown</a>
                </div>
            </div>
        </div>

        <script>
            let currentRunId = null;
            let pollInterval = null;

            document.getElementById('researchForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const topic = document.getElementById('topicInput').value;
                const maxUrls = document.getElementById('maxUrls').value;
                const engineMode = document.getElementById('engineMode').value;
                const btn = document.getElementById('submitBtn');
                
                btn.disabled = true;
                btn.innerText = "Launching Pipeline...";

                const res = await fetch('/api/research', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({topic, max_urls: maxUrls, provider: engineMode})
                });
                const data = await res.json();
                currentRunId = data.run_id;

                document.getElementById('statusCard').classList.remove('d-none');
                document.getElementById('statusMsg').innerText = "Pipeline started...";
                
                pollInterval = setInterval(checkStatus, 2000);
            });

            async function checkStatus() {
                if (!currentRunId) return;
                const res = await fetch(`/api/research/${currentRunId}`);
                const data = await res.json();

                const pBar = document.getElementById('progressBar');
                const sMsg = document.getElementById('statusMsg');
                const stats = document.getElementById('statsBox');

                sMsg.innerText = data.progress || data.status;

                if (data.status === 'searching') pBar.style.width = '25%';
                if (data.status === 'scraping') pBar.style.width = '50%';
                if (data.status === 'clustering') pBar.style.width = '75%';
                if (data.status === 'completed') {
                    pBar.style.width = '100%';
                    pBar.classList.remove('progress-bar-animated');
                    pBar.classList.add('bg-success');
                    sMsg.innerText = "Research Run Complete! ✅";
                    clearInterval(pollInterval);
                    document.getElementById('submitBtn').disabled = false;
                    document.getElementById('submitBtn').innerText = "Start New Run";

                    // Show Report
                    document.getElementById('reportContainer').classList.remove('d-none');
                    document.getElementById('reportContent').innerText = data.report_md;
                    document.getElementById('downloadBtn').href = `/api/research/${currentRunId}/report`;
                }

                stats.innerText = `URLs: ${data.urls_discovered || 0} | Pages Scraped: ${data.pages_scraped || 0} | Facts Extracted: ${data.claims_extracted || 0}`;
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html, active_ai_label=active_router.provider_label)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
