import os
import sys
import time
from google.cloud import firestore
import google.generativeai as genai

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ScrapedPage

db = firestore.Client(project=GCP_PROJECT)
genai.configure(api_key=GEMINI_API_KEY)

def hamming_distance(h1_str: str, h2_str: str) -> int:
    h1 = int(h1_str, 16)
    h2 = int(h2_str, 16)
    x = (h1 ^ h2) & ((1 << 64) - 1)
    return bin(x).count('1')

def get_embedding(text):
    result = genai.embed_content(
        model=MODEL_EMBEDDING,
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']

def cosine_similarity(v1, v2):
    dot = sum(a*b for a, b in zip(v1, v2))
    norm1 = sum(a*a for a in v1) ** 0.5
    norm2 = sum(b*b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("RUN_ID not set. Exiting.")
        sys.exit(1)
        
    run_ref = db.collection(BQ_TABLE_RUNS).document(run_id)
    run_doc = run_ref.get()
    if not run_doc.exists:
        print("Run not found.")
        sys.exit(1)
    
    topic = run_doc.to_dict().get("topic")
    if not topic:
        print("No topic found for run.")
        sys.exit(1)
        
    print(f"Starting dedup for run: {run_id}")
    topic_emb = get_embedding(topic)
    
    pages = []
    page_docs = []
    docs = db.collection(FS_SCRAPED_PAGES).where("run_id", "==", run_id).stream()
    for d in docs:
        pages.append(d.to_dict())
        page_docs.append(d)
        
    total_pages = len(pages)
    print(f"Total pages: {total_pages}")
    
    duplicates_removed = 0
    irrelevant_removed = 0
    
    valid_indices = []
    
    for i in range(total_pages):
        page = pages[i]
        doc = page_docs[i]
        
        is_dup = False
        for j in valid_indices:
            prev_page = pages[j]
            if hamming_distance(page['content_hash'], prev_page['content_hash']) <= SIMHASH_DISTANCE_THRESHOLD:
                is_dup = True
                break
                
        if is_dup:
            doc.reference.update({"is_duplicate": True})
            duplicates_removed += 1
            continue
            
        valid_indices.append(i)
        
        # Relevance filter based on first 500 chars
        summary = page.get('raw_text', '')[:500]
        if not summary:
            doc.reference.update({"is_relevant": False})
            irrelevant_removed += 1
            continue
            
        try:
            page_emb = get_embedding(summary)
            sim = cosine_similarity(topic_emb, page_emb)
            if sim < RELEVANCE_SIMILARITY_THRESHOLD:
                doc.reference.update({"is_relevant": False})
                irrelevant_removed += 1
            else:
                doc.reference.update({"is_relevant": True})
            time.sleep(GEMINI_FREE_TIER_DELAY)
        except Exception as e:
            print(f"Error getting embedding for page {page.get('url')}: {e}")
            doc.reference.update({"is_relevant": False})
            irrelevant_removed += 1
            time.sleep(GEMINI_FREE_TIER_DELAY)
            
    pages_surviving = total_pages - duplicates_removed - irrelevant_removed
    print(f"Duplicates removed: {duplicates_removed}")
    print(f"Irrelevant removed: {irrelevant_removed}")
    print(f"Pages surviving to extraction: {pages_surviving}")
    
    run_ref.update({"pages_after_dedup": pages_surviving})

if __name__ == "__main__":
    main()
