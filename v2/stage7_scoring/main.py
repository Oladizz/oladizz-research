import os
import sys
import argparse
from datetime import datetime

# Import shared config and models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import *
from models import ClaimCluster, DomainCredibility, ScoredClaim, ResearchRun

from google.cloud import firestore
from google.cloud import bigquery

def main(run_id):
    print(f"Starting Stage 7+8: Scoring for run {run_id}")
    db = firestore.Client(project=GCP_PROJECT)
    bq = bigquery.Client(project=GCP_PROJECT)

    clusters_ref = db.collection(FS_CLUSTERS).where("run_id", "==", run_id).stream()
    clusters = []
    for doc in clusters_ref:
        data = doc.to_dict()
        clusters.append(ClaimCluster(**data))
        
    if not clusters:
        # Fallback to run-specific collection
        alt_ref = db.collection(f"run_{run_id}_clusters").stream()
        for doc in alt_ref:
            data = doc.to_dict()
            clusters.append(ClaimCluster(**data))

    print(f"Loaded {len(clusters)} clusters to score.")

    credibility_cache = {}
    scored_claims = []
    
    # 1. Credibility Lookup & 2. Routing & 3. Scoring
    for cluster in clusters:
        domain_creds = []
        for domain in cluster.source_domains:
            if domain not in credibility_cache:
                doc_ref = db.collection(FS_CREDIBILITY).document(domain)
                doc = doc_ref.get()
                if doc.exists:
                    cred = DomainCredibility(**doc.to_dict())
                else:
                    cred = DomainCredibility(domain=domain, credibility_score=0.5, domain_type='unknown')
                credibility_cache[domain] = cred
            domain_creds.append(credibility_cache[domain])
        
        # Calculate average credibility
        avg_cred = sum(c.effective_score() for c in domain_creds) / len(domain_creds) if domain_creds else 0.5
        
        # Routing tier
        text = cluster.representative_claim.lower()
        has_specifics = any(c.isdigit() or x in text for c in text for x in ["http", "www", "0x", "%"])
        
        if has_specifics:
            tier = "checkable_data"
        elif cluster.independent_source_count >= 2:
            tier = "corroboration"
        else:
            tier = "anecdotal"
            
        ceiling = TIER_CEILINGS.get(tier, 0.4)
        
        # Formula parts
        source_f = min(1.0, SOURCE_COUNT_BASE + SOURCE_COUNT_STEP * cluster.independent_source_count)
        contradicting_count = len(cluster.contradicting_claims)
        penalty = min(1.0, CONTRADICTION_PENALTY_PER * contradicting_count)
        
        confidence = ceiling * source_f * avg_cred * (1.0 - penalty) * 100.0
        
        scored = ScoredClaim(
            cluster_id=cluster.cluster_id,
            representative_claim=cluster.representative_claim,
            confidence_score=confidence,
            verifiability_tier=tier,
            independent_source_count=cluster.independent_source_count,
            source_domains=cluster.source_domains,
            source_urls=cluster.source_urls,
            avg_source_credibility=avg_cred,
            has_contradictions=cluster.has_contradictions,
            contradiction_penalty=penalty,
            run_id=run_id
        )
        scored_claims.append(scored)

        # Update credibility
        for cred in domain_creds:
            cred.total_claims_seen += 1
            if confidence >= CONFIDENCE_THRESHOLD and not cluster.has_contradictions:
                cred.claims_verified += 1
            elif cluster.has_contradictions:
                cred.claims_contradicted += 1
            
            # Simple credibility adjustment
            ver_ratio = cred.claims_verified / cred.total_claims_seen if cred.total_claims_seen else 0.5
            cred.credibility_score = 0.5 + (ver_ratio - 0.5) * 0.5

    # 4. Write to Firestore run_{RUN_ID}_scored
    scored_collection = f"{run_id}_scored"
    batch = db.batch()
    count = 0
    for sc in scored_claims:
        doc_ref = db.collection(scored_collection).document(sc.cluster_id)
        batch.set(doc_ref, sc.to_dict())
        count += 1
        if count == 500:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
        
    print(f"Wrote {len(scored_claims)} scored claims to Firestore.")

    # 5. Update credibility
    batch = db.batch()
    count = 0
    for domain, cred in credibility_cache.items():
        doc_ref = db.collection(FS_CREDIBILITY).document(domain)
        batch.set(doc_ref, cred.to_dict())
        count += 1
        if count == 500:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
        
    print("Updated domain credibility.")

    # 6. BigQuery Archive (graceful fallback if BigQuery is unconfigured)
    try:
        dataset_ref = bq.dataset(BQ_DATASET)
        try:
            bq.get_dataset(dataset_ref)
        except Exception:
            bq.create_dataset(dataset_ref)

        if scored_claims:
            claims_table_id = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE_CLAIMS}"
            errors = bq.insert_rows_json(claims_table_id, [sc.to_dict() for sc in scored_claims])
            if errors:
                print(f"BigQuery claims insert errors: {errors}")
            else:
                print("Archived claims to BigQuery.")

        runs_table_id = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE_RUNS}"
        run_meta = {
            "run_id": run_id,
            "status": "scored",
            "claims_above_threshold": len([c for c in scored_claims if c.confidence_score >= CONFIDENCE_THRESHOLD]),
            "finished_at": datetime.utcnow().isoformat()
        }
        errors = bq.insert_rows_json(runs_table_id, [run_meta])
        if errors:
            print(f"BigQuery runs insert errors: {errors}")
        else:
            print("Archived run metadata to BigQuery.")
    except Exception as e:
        print(f"BigQuery archive skipped/deferred: {e}")
        
    print("Stage 7+8 complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run_id', default=os.environ.get("RUN_ID", "default-run"), help="Run ID")
    args = parser.parse_args()
    main(args.run_id)
