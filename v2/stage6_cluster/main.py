import os
import sys
import time
import json
import uuid
import numpy as np
from typing import List, Dict

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ClaimCluster

from google.cloud import firestore
import google.generativeai as genai

def get_db():
    return firestore.Client(project=GCP_PROJECT, database="(default)")

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def process_clusters(run_id: str):
    print(f"Starting Stage 6: Clustering & Contradiction Detection for run {run_id}")
    genai.configure(api_key=GEMINI_API_KEY)
    db = get_db()
    
    claims_col = f"run_{run_id}_claims"
    clusters_col = f"run_{run_id}_clusters"
    
    # 1. Read all claims
    claims_ref = db.collection(claims_col).stream()
    claims = []
    for doc in claims_ref:
        claims.append(doc.to_dict())
        
    print(f"Read {len(claims)} total claims.")
    if not claims:
        print("No claims found. Exiting.")
        return
        
    # 2. Generate embeddings in batches of 100
    texts = [c['claim'] for c in claims]
    embeddings = []
    
    print("Generating embeddings...")
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        try:
            result = genai.embed_content(
                model=MODEL_EMBEDDING,
                content=batch,
                task_type="retrieval_document"
            )
            embeddings.extend(result['embedding'])
        except Exception as e:
            print(f"Error generating embeddings for batch {i//batch_size}: {e}")
            sys.exit(1)
        time.sleep(1.0) # Small delay to avoid rate limits on embeddings
        
    for idx, claim in enumerate(claims):
        claim['embedding'] = embeddings[idx]
        
    # 3. Cluster claims
    print("Clustering claims...")
    unclustered = list(range(len(claims)))
    clusters = []
    
    while unclustered:
        base_idx = unclustered.pop(0)
        base_claim = claims[base_idx]
        base_emb = np.array(base_claim['embedding'])
        
        current_cluster_indices = [base_idx]
        
        # Find similar unclustered claims
        to_remove = []
        for i, idx in enumerate(unclustered):
            target_claim = claims[idx]
            target_emb = np.array(target_claim['embedding'])
            sim = cosine_similarity(base_emb, target_emb)
            
            if sim > EMBEDDING_CLUSTER_THRESHOLD:
                current_cluster_indices.append(idx)
                to_remove.append(i)
                
        # Remove grouped items from unclustered in reverse order to not mess up indices
        for i in reversed(to_remove):
            unclustered.pop(i)
            
        # Create cluster
        cluster_claims = [claims[idx] for idx in current_cluster_indices]
        
        # Pick the longest claim as representative
        longest_claim = max(cluster_claims, key=lambda c: len(c['claim']))
        
        unique_domains = list(set([c['source_domain'] for c in cluster_claims if c['source_domain']]))
        unique_urls = list(set([c['source_url'] for c in cluster_claims if c['source_url']]))
        
        cluster = ClaimCluster(
            cluster_id=f"cluster_{uuid.uuid4().hex[:8]}",
            representative_claim=longest_claim['claim'],
            member_claim_ids=[c['claim_id'] for c in cluster_claims],
            source_domains=unique_domains,
            source_urls=unique_urls,
            independent_source_count=len(unique_domains),
            run_id=run_id
        )
        
        # Keep original claim texts for contradiction detection
        cluster_claims_texts = [c['claim'] for c in cluster_claims]
        clusters.append((cluster, cluster_claims_texts))
        
    print(f"Formed {len(clusters)} clusters.")
    
    # 4. Check for contradictions
    print("Checking for contradictions...")
    model_cluster = genai.GenerativeModel(MODEL_CLUSTER)
    generation_config = genai.GenerationConfig(response_mime_type="application/json")
    
    contradictions_found = 0
    clusters_formed = len(clusters)
    
    for i, (cluster_obj, claim_texts) in enumerate(clusters):
        # Only check clusters with 2+ members from different domains
        if cluster_obj.independent_source_count >= 2:
            prompt = f"""
These claims were found on different websites about the same topic.
Do they assert the SAME specific fact, or do they contradict each other?
If they contradict, explain how.
Return JSON: {{"same_fact": true/false, "has_contradiction": true/false, "explanation": "..."}}

Claims:
"""
            for j, text in enumerate(claim_texts):
                prompt += f"{j+1}. {text}\n"
                
            try:
                response = model_cluster.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                result = json.loads(response.text)
                
                if result.get("has_contradiction", False):
                    cluster_obj.has_contradictions = True
                    # In a real system, you might specify exactly which ones contradict.
                    # Here we just mark the cluster and store the explanation.
                    cluster_obj.contradicting_claims = [result.get("explanation", "")]
                    contradictions_found += 1
                    
            except Exception as e:
                print(f"  Error checking contradiction for cluster {cluster_obj.cluster_id}: {e}")
                
            # Respect free-tier limits
            time.sleep(GEMINI_FREE_TIER_DELAY)
            
        # 5. Write to Firestore
        db.collection(clusters_col).document(cluster_obj.cluster_id).set(cluster_obj.to_dict())
        
        if (i+1) % 10 == 0:
            print(f"Processed {i+1}/{len(clusters)} clusters...")
            
    print(f"Stage 6 complete. Total claims: {len(claims)}, Clusters formed: {clusters_formed}, Contradictions found: {contradictions_found}.")

def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("Error: RUN_ID environment variable is required.")
        sys.exit(1)
        
    process_clusters(run_id)

if __name__ == '__main__':
    main()
