import os
import sys
import time
import json
import hashlib
from typing import List

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ScrapedPage, ExtractedClaim

from google.cloud import firestore
import google.generativeai as genai

def get_db():
    return firestore.Client(project=GCP_PROJECT, database="(default)")

def process_pages(run_id: str):
    print(f"Starting Stage 5: Claim Extraction for run {run_id}")
    genai.configure(api_key=GEMINI_API_KEY)
    db = get_db()
    
    # Read scraped pages
    pages_ref = db.collection(FS_SCRAPED_PAGES)
    query = pages_ref.where("run_id", "==", run_id) \
                     .where("is_duplicate", "==", False) \
                     .where("is_relevant", "==", True)
    
    docs = query.stream()
    
    pages = []
    for doc in docs:
        d = doc.to_dict()
        # Since to_dict in ScrapedPage removes some fields or changes them (e.g. raw_text_length),
        # we might need to handle raw_text if it was stored. If raw_text is missing from the stream,
        # we assume it's in the document.
        if 'raw_text' in d:
            pages.append(d)

    print(f"Found {len(pages)} pages to process.")
    
    model = genai.GenerativeModel(MODEL_EXTRACT)
    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    
    prompt_template = """
Extract every specific, atomic factual claim from this article. Return ONLY a JSON array.
Each claim must have: "claim" (the factual statement), "subject" (what/who it's about), "numbers" (any specific numbers/dates/amounts mentioned).
Do NOT include opinions, predictions, or vague statements. Only extract verifiable factual claims.

Article Text:
{text}
"""

    total_claims = 0
    claims_col = f"run_{run_id}_claims"
    
    for i, page in enumerate(pages):
        print(f"Processing page {i+1}/{len(pages)}: {page.get('url')}")
        
        raw_text = page.get('raw_text', '')
        if not raw_text:
            continue
            
        # Truncate to first 30,000 chars
        text_to_process = raw_text[:30000]
        prompt = prompt_template.format(text=text_to_process)
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Parse JSON
            claims_data = json.loads(response.text)
            
            if not isinstance(claims_data, list):
                print(f"  Warning: Expected JSON array, got {type(claims_data)}. Skipping.")
                claims_data = []
            
            page_claims = 0
            for item in claims_data:
                claim_text = item.get("claim", "")
                subject = item.get("subject", "")
                numbers = item.get("numbers", [])
                
                if not claim_text:
                    continue
                    
                # Generate unique claim_id
                hash_input = (claim_text + page.get('url', '')).encode('utf-8')
                claim_id = hashlib.sha256(hash_input).hexdigest()
                
                claim_obj = ExtractedClaim(
                    claim=claim_text,
                    subject=subject,
                    numbers=numbers,
                    source_url=page.get('url', ''),
                    source_domain=page.get('domain', ''),
                    run_id=run_id,
                    claim_id=claim_id
                )
                
                db.collection(claims_col).document(claim_id).set(claim_obj.to_dict())
                page_claims += 1
                total_claims += 1
                
            print(f"  Extracted {page_claims} claims.")
            
        except Exception as e:
            print(f"  Error extracting claims for page {page.get('url')}: {e}")
            
        # Respect free-tier limits
        time.sleep(GEMINI_FREE_TIER_DELAY)
        
    print(f"Stage 5 complete. Processed {len(pages)} pages, extracted {total_claims} total claims.")

def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("Error: RUN_ID environment variable is required.")
        sys.exit(1)
        
    process_pages(run_id)

if __name__ == '__main__':
    main()
