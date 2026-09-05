from typing import List, Dict

def detect_contradictions(claims: List[Dict]) -> List[tuple]:
    contradictions = []
    
    if not claims or len(claims) < 2:
        return contradictions
        
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            c1 = claims[i]
            c2 = claims[j]
            
            # Must be about same subject to contradict
            if c1.get("subject", "").lower() != c2.get("subject", "").lower():
                continue
                
            t1 = c1.get("claim", "").lower()
            t2 = c2.get("claim", "").lower()
            
            # Directional contradictions
            if ("increased" in t1 and "decreased" in t2) or ("decreased" in t1 and "increased" in t2):
                contradictions.append((i, j))
                continue
                
            # Number contradictions
            n1 = set(c1.get("numbers", []))
            n2 = set(c2.get("numbers", []))
            
            if n1 and n2 and not n1.intersection(n2):
                # E.g., one says $5M, other says $3M
                contradictions.append((i, j))
                
    return contradictions

def test_conflicting_numbers():
    claims = [
        {"claim": "revenue was $5M", "subject": "revenue", "numbers": ["$5M"]},
        {"claim": "revenue was $3M", "subject": "revenue", "numbers": ["$3M"]}
    ]
    contradictions = detect_contradictions(claims)
    assert len(contradictions) > 0

def test_opposite_directions():
    claims = [
        {"claim": "sales increased", "subject": "sales", "numbers": []},
        {"claim": "sales decreased", "subject": "sales", "numbers": []}
    ]
    contradictions = detect_contradictions(claims)
    assert len(contradictions) > 0

def test_agreeing_claims():
    claims = [
        {"claim": "revenue was $5M", "subject": "revenue", "numbers": ["$5M"]},
        {"claim": "revenue reached $5M", "subject": "revenue", "numbers": ["$5M"]}
    ]
    contradictions = detect_contradictions(claims)
    assert len(contradictions) == 0

def test_different_subjects():
    claims = [
        {"claim": "Apple revenue $5M", "subject": "Apple revenue", "numbers": ["$5M"]},
        {"claim": "Google revenue $3M", "subject": "Google revenue", "numbers": ["$3M"]}
    ]
    contradictions = detect_contradictions(claims)
    assert len(contradictions) == 0

def test_empty_input():
    assert len(detect_contradictions([])) == 0
