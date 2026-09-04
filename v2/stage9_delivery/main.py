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
    scored_collection = f"{run_id}_scored"
    scored_ref = db.collection(scored_collection).where("confidence_score", ">=", CONFIDENCE_THRESHOLD).stream()
    
    claims = []
    for doc in scored_ref:
        data = doc.to_dict()
        claims.append(ScoredClaim(**data))

    claims.sort(key=lambda x: x.confidence_score, reverse=True)
    print(f"Loaded {len(claims)} high-confidence claims.")

    trusted_urls = set()
    for c in claims:
        trusted_urls.update(c.source_urls)

    md_content = f"# Research Report: {topic}\n"
    md_content += f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
    md_content += f"## Executive Summary\n"
    md_content += f"Found {len(claims)} verified claims from {len(trusted_urls)} trusted sources.\n\n"
    md_content += f"## Verified Claims\n"
    
    for c in claims[:MAX_CLAIMS_IN_REPORT]:
        badge = "🟢" if c.confidence_score >= 85 else "🟡"
        md_content += f"### {badge} {c.representative_claim}\n"
        md_content += f"- **Confidence:** {c.confidence_score:.1f}%\n"
        md_content += f"- **Sources ({c.independent_source_count}):** {', '.join(c.source_domains)}\n\n"
    
    md_content += f"## Works Cited\n"
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

    # 3. GCS Upload
    bucket = storage_client.bucket(GCS_BUCKET)
    if not bucket.exists():
        bucket = storage_client.create_bucket(bucket)
        
    blob = bucket.blob(f"reports/{run_id}/{pdf_filename}")
    blob.storage_class = GCS_STORAGE_CLASS
    blob.upload_from_filename(pdf_filename)
    
    signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(days=7), method="GET")

    # 5. Trusted Links
    links_blob = bucket.blob(f"reports/{run_id}/trusted_links.txt")
    links_blob.upload_from_string("\n".join(sorted(list(trusted_urls))))

    # 4. Telegram Delivery
    msg = f"📄 *New Research Report*\nTopic: {topic}\nVerified Claims: {len(claims)}\n[Download PDF]({signed_url})"
    send_telegram(msg, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

    # 6. Cleanup
    collections_to_delete = [
        f"{run_id}_claims", 
        f"{run_id}_clusters", 
        f"{run_id}_scored"
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
            
    # Also delete run specific docs in DISCOVERED_URLS and SCRAPED_PAGES
    for coll in [FS_DISCOVERED_URLS, FS_SCRAPED_PAGES]:
        docs = db.collection(coll).where("run_id", "==", run_id).stream()
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

    print(f"Stats: {len(claims)} claims in report. PDF size: {pdf_size} bytes. GCS Path: gs://{GCS_BUCKET}/reports/{run_id}/")
    print("Stage 9+10 complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_id', required=True, help="Run ID")
    parser.add_argument('--topic', required=True, help="Topic")
    args = parser.parse_args()
    main(args.run_id, args.topic)
