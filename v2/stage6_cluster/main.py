"""
Stage 6 — Clustering & Contradiction Detection (Production, Zero-AI default)

Uses TF-IDF + HDBSCAN by default. Zero API cost.
Set USE_AI_CLUSTERING=true to enable Gemini contradiction analysis.
"""
import os
import sys
import json
import hashlib
import time
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ClaimCluster

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'utils'))

from google.cloud import firestore

# Import zero-AI utilities
try:
    from hdbscan_cluster import cluster_claims, pick_representative
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

try:
    from contradiction import detect_contradictions
    HAS_CONTRADICTION = True
except ImportError:
    HAS_CONTRADICTION = False

# Optional AI Router (OpenAI, Claude, Gemini)
try:
    from ai_router import AIRouter
    HAS_AI_ROUTER = True
except ImportError:
    HAS_AI_ROUTER = False


def cluster_with_code(claims: List[dict]) -> List[List[int]]:
    """Cluster claims using HDBSCAN + TF-IDF. Zero cost, O(n log n)."""
    if HAS_HDBSCAN:
        texts = [c.get("claim", "") for c in claims]
        return cluster_claims(texts, min_cluster_size=2, min_samples=1)

    # Minimal fallback: exact string matching
    from collections import defaultdict
    groups = defaultdict(list)
    for i, c in enumerate(claims):
        # Group by first 50 chars as a rough key
        key = c.get("claim", "")[:50].lower().strip()
        groups[key].append(i)
    return [indices for indices in groups.values() if len(indices) >= 1]


def check_contradictions_code(cluster_claims_list: List[dict]) -> dict:
    """Check for contradictions using rule-based comparison. Zero cost."""
    if HAS_CONTRADICTION:
        contradictions = detect_contradictions(cluster_claims_list)
        return {
            "has_contradiction": len(contradictions) > 0,
            "contradictions": contradictions
        }
    return {"has_contradiction": False, "contradictions": []}


def check_contradictions_ai(cluster_claims_list: List[dict], model) -> dict:
    """Check contradictions using Gemini. Costs tokens."""
    claims_text = "\n".join([f"- {c.get('claim', '')}" for c in cluster_claims_list])
    prompt = f"""These claims were found on different websites about the same topic.
Do they assert the SAME specific fact, or do they contradict each other?
If they contradict, explain how.
Return JSON: {{"same_fact": true/false, "has_contradiction": true/false, "explanation": "..."}}

Claims:
{claims_text}"""

    try:
        response = model.generate_content(prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json"))
        result = json.loads(response.text)
        return {
            "has_contradiction": result.get("has_contradiction", False),
            "contradictions": [{"reason": result.get("explanation", "")}] if result.get("has_contradiction") else []
        }
    except Exception as e:
        print(f"  AI contradiction check failed: {e}. Falling back to code.")
        return check_contradictions_code(cluster_claims_list)


def main():
    run_id = os.environ.get("RUN_ID")
    if not run_id:
        print("Error: RUN_ID required.")
        sys.exit(1)

    router = AIRouter() if HAS_AI_ROUTER else None
    active_provider = router.provider if router else "none"
    use_ai = (os.environ.get("USE_AI_CLUSTERING", "false").lower() == "true") or (active_provider != "none")

    print("=== STAGE 6: Clustering & Contradiction Detection ===")
    print(f"Run: {run_id}")
    print(f"Engine: {router.provider_label if router else 'Zero-AI Local Code'}")

    db = firestore.Client(project=GCP_PROJECT, database="(default)")

    # Read all claims
    claims_col = f"run_{run_id}_claims"
    docs = list(db.collection(claims_col).stream())
    claims = [doc.to_dict() for doc in docs]
    print(f"Loaded {len(claims)} claims.")

    if not claims:
        print("No claims to cluster. Done.")
        return

    # Cluster claims (HDBSCAN or fallback)
    print("Clustering claims...")
    clusters_indices = cluster_with_code(claims)
    print(f"Formed {len(clusters_indices)} clusters.")

    # Process each cluster
    clusters_col = f"run_{run_id}_clusters"
    clusters_formed = 0
    contradictions_found = 0

    for cluster_idx, indices in enumerate(clusters_indices):
        cluster_claims_list = [claims[i] for i in indices]

        # Pick representative (longest claim)
        texts = [c.get("claim", "") for c in cluster_claims_list]
        if HAS_HDBSCAN:
            representative = pick_representative(texts)
        else:
            representative = max(texts, key=len)

        # Get unique source domains
        source_domains = list(set(c.get("source_domain", "") for c in cluster_claims_list))
        source_urls = list(set(c.get("source_url", "") for c in cluster_claims_list))

        # Check contradictions (only for multi-source clusters)
        has_contradiction = False
        contradicting = []

        if len(source_domains) >= 2:
            if router:
                result = router.check_contradiction(cluster_claims_list)
            else:
                result = check_contradictions_code(cluster_claims_list)

            has_contradiction = result["has_contradiction"]
            contradicting = [c.get("reason", "") for c in result.get("contradictions", [])]
            if has_contradiction:
                contradictions_found += 1

        # Build cluster record
        cluster_id = hashlib.sha256(representative.encode('utf-8')).hexdigest()[:16]
        cluster = ClaimCluster(
            cluster_id=cluster_id,
            representative_claim=representative,
            member_claim_ids=[claims[i].get("claim_id", "") for i in indices],
            source_domains=source_domains,
            source_urls=source_urls,
            independent_source_count=len(source_domains),
            has_contradictions=has_contradiction,
            contradicting_claims=contradicting,
            run_id=run_id
        )

        db.collection(clusters_col).document(cluster_id).set(cluster.to_dict())
        clusters_formed += 1

    print("\nStage 6 complete.")
    print(f"  Clusters formed: {clusters_formed}")
    print(f"  Contradictions found: {contradictions_found}")


if __name__ == '__main__':
    main()
