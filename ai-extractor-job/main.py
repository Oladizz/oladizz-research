import os
import json
import time
import google.generativeai as genai
from google.cloud import firestore

def get_db():
    project = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
    return firestore.Client(project=project)

def configure_gemini():
    # Use the free-tier API key stored in environment variables or Secret Manager
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARNING: GEMINI_API_KEY not set. Local testing requires this.")
    genai.configure(api_key=api_key)
    # Using Gemini 2.5 Flash-Lite as requested for high-volume extraction.
    return genai.GenerativeModel('gemini-2.5-flash-lite')

def extract_claims(model, text, source_url, source_domain):
    prompt = f"""
    You are an expert fact-extractor. Read the following article text and extract all specific, 
    atomic factual claims being made. Ignore opinions, fluff, and general summaries.
    
    Format the output as a JSON list of objects matching this exact structure:
    [
      {{
        "claim": "Specific factual statement",
        "subject": "The entity or person the claim is about",
        "numbers": ["List", "of", "any", "numbers", "or", "dates", "mentioned", "in", "the", "claim"],
        "source_url": "{source_url}",
        "source_domain": "{source_domain}"
      }}
    ]
    
    Article Text:
    {text[:30000]} # Truncated to avoid massive context token waste
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini API Error for {source_url}: {e}")
        return None

def process_pending_pages():
    db = get_db()
    model = configure_gemini()
    
    # Get all pages that have been scraped but not yet extracted
    pages_ref = db.collection("extracted_pages").where("status", "==", "ready_for_extraction").limit(50)
    pages = list(pages_ref.stream())
    
    if not pages:
        print("No pending pages found for extraction.")
        return

    print(f"Found {len(pages)} pages ready for extraction.")
    
    for page in pages:
        data = page.to_dict()
        source_url = data.get("source_url")
        source_domain = data.get("source_domain")
        raw_text = data.get("raw_text")
        
        print(f"Extracting claims from: {source_url}")
        
        claims = extract_claims(model, raw_text, source_url, source_domain)
        
        if claims:
            batch = db.batch()
            
            # Save each claim to the 'claims' collection
            for claim in claims:
                # Add status fields for the next stage (Clustering/Scoring)
                claim['status'] = 'pending_clustering'
                claim['confidence_score'] = None 
                
                claim_ref = db.collection("claims").document()
                batch.set(claim_ref, claim)
                
            # Mark the original page as successfully extracted
            batch.update(page.reference, {"status": "extracted", "claim_count": len(claims)})
            batch.commit()
            
            print(f"  -> Extracted {len(claims)} claims successfully.")
        else:
            # Mark as failed so we don't keep retrying it infinitely
            page.reference.update({"status": "extraction_failed"})
            
        # VERY IMPORTANT FOR ZERO COST:
        # The Gemini Free Tier has a rate limit of 15 Requests Per Minute (RPM).
        # We sleep for 4.5 seconds between requests to ensure we never exceed 15 RPM.
        # This means we process slowly, but it costs absolutely $0.00.
        print("Sleeping for 4.5s to respect Gemini Free Tier limits...")
        time.sleep(4.5)

if __name__ == "__main__":
    print("========================================")
    print("Oladizz Research Pipeline: Stage 4 (AI Extractor)")
    print("========================================")
    process_pending_pages()
