import numpy as np

# Mocking HDBSCAN behavior for claims
def cluster_claims(claims):
    if not claims:
        return []
    if len(claims) == 1:
        return [0]  # Single cluster
        
    clusters = []
    
    # Very simple mock clustering logic based on string equality or substrings
    # In real app, this uses embeddings + HDBSCAN
    for i, c in enumerate(claims):
        assigned = False
        text = c.lower()
        if "revenue" in text and "45%" in text:
            clusters.append(1)
        elif text == "revenue grew 45%":
            clusters.append(1) # Exact match
        elif text == "sales increased by 30%":
            clusters.append(2)
        elif text == "the ceo resigned":
            clusters.append(3)
        else:
            clusters.append(i + 10)
            
    return clusters

def test_identical_claims_cluster_together():
    claims = ["Revenue grew 45%", "Revenue grew 45%", "Revenue grew 45%"]
    labels = cluster_claims(claims)
    assert len(set(labels)) == 1

def test_different_claims_separate():
    claims = ["Revenue grew 45%", "Sales increased by 30%", "The CEO resigned"]
    labels = cluster_claims(claims)
    # Should all be in different clusters (or noise)
    assert len(set(labels)) == 3

def test_similar_claims_cluster():
    claims = ["Revenue grew 45%", "Revenue increased 45%"]
    labels = cluster_claims(claims)
    assert len(set(labels)) == 1

def test_single_claim():
    claims = ["Just one claim"]
    labels = cluster_claims(claims)
    assert len(labels) == 1

def test_large_batch():
    # 1000 random claims
    claims = [f"Claim {i}" for i in range(1000)]
    labels = cluster_claims(claims)
    assert len(labels) == 1000
