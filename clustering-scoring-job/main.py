import os
import json
import time
import numpy as np
import google.generativeai as genai
from google.cloud import firestore

def get_db():
    project = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
    return firestore.Client(project=project)

def configure_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-3.7-flash')

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def check_for_contradictions(model, claims_texts):
    if len(claims_texts) <= 1:
        return 0.0 # No penalty if there's nothing to contradict
        
    prompt = f"""
    You are a logical consistency checker. Review the following claims which were grouped together 
    because they are semantically similar. 
    
    Do these claims contradict each other regarding specific numbers, facts, or outcomes?
    If they just use different words to say the exact same thing, that is NOT a contradiction.
    
    Claims:
    {json.dumps(claims_texts, indent=2)}
    
    Respond with a JSON object:
    {{
      "has_contradiction": boolean,
      "reasoning": "Brief explanation"
    }}
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        result = json.loads(response.text)
        return 0.5 if result.get("has_contradiction") else 0.0
    except Exception as e:
        print(f"Gemini Error during contradiction check: {e}")
        return 0.0

def process_clustering_and_scoring():
    db = get_db()
    model = configure_gemini()
    
    # 1. Fetch claims ready for clustering
    claims_ref = db.collection("claims").where("status", "==", "pending_clustering").limit(200)
    claims_docs = list(claims_ref.stream())
    
    if not claims_docs:
        print("No claims ready for clustering.")
        return
        
    print(f"Found {len(claims_docs)} claims. Generating embeddings...")
    
    # 2. Generate Embeddings (Batched to save API calls)
    claims_data = []
    texts_to_embed = []
    
    for doc in claims_docs:
        data = doc.to_dict()
        data['id'] = doc.id
        claims_data.append(data)
        texts_to_embed.append(data.get('claim', ''))
        
    try:
        embedding_result = genai.embed_content(
            model="models/text-embedding-004",
            content=texts_to_embed
        )
        embeddings = embedding_result['embedding']
    except Exception as e:
        print(f"Failed to generate embeddings: {e}")
        return
        
    # Assign embeddings back to claims
    for i, data in enumerate(claims_data):
        data['embedding'] = embeddings[i]
        
    # 3. Naive Clustering (O(N^2) - fine for small batches per run)
    clusters = []
    used_indices = set()
    
    for i in range(len(claims_data)):
        if i in used_indices:
            continue
            
        current_cluster = [claims_data[i]]
        used_indices.add(i)
        
        for j in range(i + 1, len(claims_data)):
            if j in used_indices:
                continue
                
            sim = cosine_similarity(claims_data[i]['embedding'], claims_data[j]['embedding'])
            if sim > 0.85: # Similarity threshold
                current_cluster.append(claims_data[j])
                used_indices.add(j)
                
        clusters.append(current_cluster)
        
    print(f"Grouped {len(claims_data)} claims into {len(clusters)} unique clusters.")
    
    # 4. Scoring & Contradiction Checking
    batch = db.batch()
    
    for cluster in clusters:
        # Get unique domains in this cluster (Independent source count)
        unique_domains = set(c.get('source_domain') for c in cluster)
        source_count = len(unique_domains)
        
        # Check for contradictions using Gemini
        claim_texts = [c.get('claim') for c in cluster]
        contradiction_penalty = check_for_contradictions(model, claim_texts)
        time.sleep(4.5) # Respect 15 RPM Free Tier Limit
        
        # Pull credibility (Mocking Firestore lookup for this domain)
        # In a real run, you'd do: db.collection("credibility").document(domain).get()
        avg_credibility = 0.7 # Placeholder for demonstration
        
        # THE SCORING FORMULA
        # base ceiling (0.8) * source count log * credibility * (1 - penalty)
        base_ceiling = 0.8 
        source_multiplier = min(1.0, 0.5 + (0.1 * source_count)) 
        confidence_score = base_ceiling * source_multiplier * avg_credibility * (1.0 - contradiction_penalty)
        
        # Convert to percentage
        final_score = round(confidence_score * 100, 1)
        print(f"Cluster Scored: {final_score}% | Sources: {source_count} | Contradiction: {contradiction_penalty > 0}")
        
        # 5. Save the final synthesized cluster
        cluster_doc_ref = db.collection("scored_clusters").document()
        batch.set(cluster_doc_ref, {
            "representative_claim": cluster[0].get("claim"),
            "confidence_score": final_score,
            "source_count": source_count,
            "sources": list(unique_domains),
            "had_contradictions": contradiction_penalty > 0,
            "status": "ready_for_synthesis"
        })
        
        # Mark original claims as processed
        for c in cluster:
            doc_ref = db.collection("claims").document(c['id'])
            batch.update(doc_ref, {"status": "scored", "cluster_id": cluster_doc_ref.id})
            
    # Commit all changes to Firestore
    batch.commit()
    print("Scoring complete. Clusters saved to Firestore.")

if __name__ == "__main__":
    print("========================================")
    print("Oladizz Research Pipeline: Stage 5 & 8")
    print("========================================")
    process_clustering_and_scoring()
