"""
Stage 5 — Claim Extraction (Production, Zero-AI default)

Uses spaCy NER + regex by default. Zero API cost.
Set USE_AI_EXTRACTION=true to enable Gemini enhancement.
"""
import os
import sys
import time
import json
import hashlib
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ExtractedClaim

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from google.cloud import firestore

# Try loading code-only extractor
try:
    from spacy_extractor import extract_claims_from_text as code_extract
    HAS_SPACY_EXTRACTOR = True
except ImportError:
    HAS_SPACY_EXTRACTOR = False

# Optional AI
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def extract_claims_code(text: str, source_url: str, source_domain: str) -> List[dict]:
    """Extract claims using spaCy + regex. Zero AI cost."""
    if HAS_SPACY_EXTRACTOR:
        return code_extract(text, source_url, source_domain)

    # Minimal fallback if spaCy isn't installed: regex-only extraction
    import re
    claims = []
    sentences = text.replace('\n', ' ').split('.')

    # Patterns that indicate factual claims
    number_pattern = re.compile(r'\b\d+[\d,.]*%?|\$[\d,.]+[MBKmk]?\b')
    opinion_markers = {'i think', 'i believe', 'in my opinion', 'arguably',
                       'it seems', 'probably', 'maybe', 'might', 'could be'}
    promo_markers = {'click here', 'subscribe', 'sign up', 'buy now',
                     'limited time', 'free trial', 'download now'}

    for sent in sentences:
        sent = sent.strip()
        if len(sent.split()) < 8 or len(sent.split()) > 60:
            continue
        if sent.endswith('?'):
            continue
        lower = sent.lower()
        if any(m in lower for m in opinion_markers):
            continue
        if any(m in lower for m in promo_markers):
            continue

        numbers = number_pattern.findall(sent)
        if numbers:
            claims.append({
                "claim": sent,
                "subject": "",
                "numbers": numbers,
                "source_url": source_url,
                "source_domain": source_domain
            })

    return claims


def extract_claims_ai(text: str, source_url: str, source_domain: str, model) -> List[dict]:
    """Extract claims using Gemini. Costs AI tokens."""
    prompt = f"""Extract every specific, atomic factual claim from this article. Return ONLY a JSON array.
Each claim must have: "claim" (the factual statement), "subject" (what/who it's about), "numbers" (any specific numbers/dates/amounts mentioned).
Do NOT include opinions, predictions, or vague statements. Only extract verifiable factual claims.

Article Text:
{text[:30000]}"""

    try:
        response = model.generate_content(prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json"))
        claims_data = json.loads(response.text)
        if not isinstance(claims_data, list):
            return []

        results = []
        for item in claims_data:
            claim_text = item.get("claim", "")
            if claim_text:
                results.append({
                    "claim": claim_text,
                    "subject": item.get("subject", ""),
                    "numbers": item.get("numbers", []),
                    "source_url": source_url,
                    "source_domain": source_domain
                })
        return results
    except Exception as e:
        print(f"  AI extraction failed: {e}. Falling back to code.")
        return extract_claims_code(text, source_url, source_domain)


def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("Error: RUN_ID environment variable is required.")
        sys.exit(1)

    use_ai = os.environ.get("USE_AI_EXTRACTION", "false").lower() == "true"

    print("=== STAGE 5: Claim Extraction ===")
    print(f"Run: {run_id}")
    print(f"Mode: {'AI-assisted (costs tokens)' if use_ai else 'Code-only (zero cost)'}")

    db = firestore.Client(project=GCP_PROJECT, database="(default)")

    # Set up AI model if requested
    ai_model = None
    if use_ai and HAS_GENAI and GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        ai_model = genai.GenerativeModel(MODEL_EXTRACT)

    # Read scraped pages
    pages_ref = db.collection(FS_SCRAPED_PAGES)
    query = pages_ref.where("run_id", "==", run_id) \
                     .where("is_duplicate", "==", False) \
                     .where("is_relevant", "==", True)

    docs = list(query.stream())
    print(f"Found {len(docs)} pages to process.")

    total_claims = 0
    claims_col = f"run_{run_id}_claims"

    for i, doc in enumerate(docs):
        page = doc.to_dict()
        url = page.get('url', '')
        domain = page.get('domain', '')
        raw_text = page.get('raw_text', '')

        if not raw_text:
            continue

        print(f"Processing page {i+1}/{len(docs)}: {url}")

        # Extract claims
        if use_ai and ai_model:
            claims = extract_claims_ai(raw_text, url, domain, ai_model)
            time.sleep(GEMINI_FREE_TIER_DELAY)  # Rate limit
        else:
            claims = extract_claims_code(raw_text, url, domain)

        # Save to Firestore
        page_claims = 0
        for claim_data in claims:
            claim_text = claim_data.get("claim", "")
            if not claim_text:
                continue

            claim_id = hashlib.sha256(
                (claim_text + url).encode('utf-8')
            ).hexdigest()

            claim_obj = ExtractedClaim(
                claim=claim_text,
                subject=claim_data.get("subject", ""),
                numbers=claim_data.get("numbers", []),
                source_url=url,
                source_domain=domain,
                run_id=run_id,
                claim_id=claim_id
            )

            db.collection(claims_col).document(claim_id).set(claim_obj.to_dict())
            page_claims += 1
            total_claims += 1

        print(f"  -> Extracted {page_claims} claims.")

    print(f"\nStage 5 complete. {len(docs)} pages processed, {total_claims} claims extracted.")


if __name__ == '__main__':
    main()
