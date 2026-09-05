import os
import sys
import argparse
import markdown
import requests
from datetime import datetime, timedelta

from weasyprint import HTML, CSS

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ScoredClaim

from google.cloud import firestore
from google.cloud import storage

def send_telegram(message, bot_token, chat_id):
    if not bot_token or not chat_id:
        print("Telegram missing config.")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def main(run_id, topic):
    print(f"Starting Stage 9+10: Synthesis & Delivery for run {run_id}")
    db = firestore.Client(project=GCP_PROJECT)
    storage_client = storage.Client(project=GCP_PROJECT)

    # 1. Synthesis
    claims = []
    # Check FS_SCORED_CLAIMS with run_id filter (in-memory threshold filter to avoid composite index requirement)
    all_scored = []
    try:
        scored_ref = db.collection(FS_SCORED_CLAIMS).where("run_id", "==", run_id).stream()
        for doc in scored_ref:
            all_scored.append(ScoredClaim(**doc.to_dict()))
    except Exception as e:
        print(f"Query FS_SCORED_CLAIMS warning: {e}")
        
    if not all_scored:
        for coll_name in [f"{run_id}_scored", f"run_{run_id}_scored"]:
            try:
                scored_ref = db.collection(coll_name).stream()
                for doc in scored_ref:
                    all_scored.append(ScoredClaim(**doc.to_dict()))
                if all_scored:
                    break
            except Exception:
                pass
                
    # Filter by confidence threshold or take top claims
    claims = [c for c in all_scored if c.confidence_score >= CONFIDENCE_THRESHOLD]
    if not claims and all_scored:
        print(f"No claims >= {CONFIDENCE_THRESHOLD}%, taking top {min(30, len(all_scored))} scored claims.")
        all_scored.sort(key=lambda x: x.confidence_score, reverse=True)
        claims = all_scored[:30]

    claims.sort(key=lambda x: x.confidence_score, reverse=True)
    print(f"Loaded {len(claims)} high-confidence claims.")

    trusted_urls = set()
    for c in claims:
        trusted_urls.update(c.source_urls)

    md_content = f"# Research Report: {topic}\n"
    md_content += f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
    md_content += "## Executive Summary\n"
    md_content += f"Found {len(claims)} verified claims from {len(trusted_urls)} trusted sources.\n\n"
    md_content += "## Verified Claims\n"
    
    for c in claims[:MAX_CLAIMS_IN_REPORT]:
        badge = "🟢" if c.confidence_score >= 85 else "🟡"
        md_content += f"### {badge} {c.representative_claim}\n"
        md_content += f"- **Confidence:** {c.confidence_score:.1f}%\n"
        md_content += f"- **Sources ({c.independent_source_count}):** {', '.join(c.source_domains)}\n\n"
    
    md_content += "## Works Cited\n"
    for i, url in enumerate(sorted(list(trusted_urls))):
        md_content += f"{i+1}. {url}\n"

    # 2. PDF Generation
    html_content = markdown.markdown(md_content)
    # Simple CSS styling
    css = CSS(string='''
        body { font-family: sans-serif; margin: 2cm; }
        h1, h2 { page-break-after: avoid; }
        h2 { margin-top: 1.5em; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
        h3 { margin-top: 1em; }
    ''')
    
    pdf_filename = f"report_{run_id}.pdf"
    HTML(string=html_content).write_pdf(pdf_filename, stylesheets=[css])
    pdf_size = os.path.getsize(pdf_filename)

    # Also save Markdown copy
    md_filename = f"report_{run_id}.md"
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved Markdown report to: {md_filename}")

    # 3. GCS Upload (Safe)
    signed_url = None
    try:
        bucket = storage_client.bucket(GCS_BUCKET)
        if not bucket.exists():
            bucket = storage_client.create_bucket(bucket)
            
        blob = bucket.blob(f"reports/{run_id}/{pdf_filename}")
        blob.storage_class = GCS_STORAGE_CLASS
        blob.upload_from_filename(pdf_filename)
        
        signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")

        links_blob = bucket.blob(f"reports/{run_id}/trusted_links.txt")
        links_blob.upload_from_string("\n".join(sorted(list(trusted_urls))))
        print(f"Uploaded to GCS: gs://{GCS_BUCKET}/reports/{run_id}/")
    except Exception as e:
        print(f"GCS upload skipped/deferred: {e}")

    # 4. Telegram Delivery (Safe)
    try:
        download_text = f"[Download PDF]({signed_url})" if signed_url else "PDF generated locally."
        msg = f"📄 *New Research Report*\nTopic: {topic}\nVerified Claims: {len(claims)}\n{download_text}"
        send_telegram(msg, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    except Exception as e:
        print(f"Telegram delivery skipped: {e}")

    # 5. Optional Cleanup
    if os.environ.get("DO_CLEANUP", "false").lower() == "true":
        print("Cleaning up ephemeral collections...")
        collections_to_delete = [
            f"{run_id}_claims", 
            f"{run_id}_clusters", 
            f"{run_id}_scored",
            f"run_{run_id}_claims",
            f"run_{run_id}_clusters",
            f"run_{run_id}_scored"
        ]
        
        for coll_name in collections_to_delete:
            docs = db.collection(coll_name).stream()
            batch = db.batch()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                if count == 500:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            if count > 0:
                batch.commit()

    print(f"Stats: {len(claims)} claims in report. PDF size: {pdf_size} bytes. Local path: {os.path.abspath(pdf_filename)}")
    print("Stage 9+10 complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_id', default=os.environ.get("RUN_ID", "default-run"), help="Run ID")
    parser.add_argument('--topic', default=os.environ.get("RESEARCH_TOPIC", "Research Report"), help="Topic")
    args = parser.parse_args()
    main(args.run_id, args.topic)
