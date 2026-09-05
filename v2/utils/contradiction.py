import difflib
from typing import List, Dict
from collections import defaultdict

OPPOSITE_PAIRS = [
    ("increase", "decrease"), ("increased", "decreased"),
    ("grow", "shrink"), ("grew", "shrank"),
    ("rise", "fall"), ("rose", "fell"),
    ("more", "less"), ("higher", "lower"),
    ("gain", "loss"), ("profit", "loss"),
    ("up", "down"), ("expand", "contract"),
    ("improve", "worsen")
]

def detect_contradictions(claims: List[Dict]) -> List[Dict]:
    """
    Detect contradictions based on rule-based comparison.
    Input: list of claim dicts with "claim", "subject", "numbers"
    """
    contradictions = []
    
    # Group by subject using fuzzy match
    subject_groups = defaultdict(list)
    
    def get_group_key(subj: str) -> str:
        if not subj:
            return "UNKNOWN"
        for existing_key in subject_groups.keys():
            if existing_key == "UNKNOWN": continue
            if difflib.SequenceMatcher(None, subj.lower(), existing_key.lower()).ratio() > 0.8:
                return existing_key
        return subj

    for c in claims:
        key = get_group_key(c.get("subject", ""))
        subject_groups[key].append(c)
        
    # Compare within groups
    for subj, group_claims in subject_groups.items():
        if len(group_claims) < 2:
            continue
            
        for i in range(len(group_claims)):
            for j in range(i + 1, len(group_claims)):
                c1 = group_claims[i]
                c2 = group_claims[j]
                
                c1_text = c1.get("claim", "").lower()
                c2_text = c2.get("claim", "").lower()
                
                # Check opposite directional words
                found_opposite = False
                for w1, w2 in OPPOSITE_PAIRS:
                    if (w1 in c1_text and w2 in c2_text) or (w2 in c1_text and w1 in c2_text):
                        contradictions.append({
                            "claim_a": c1.get("claim"),
                            "claim_b": c2.get("claim"),
                            "reason": f"Opposite directional words: {w1}/{w2}"
                        })
                        found_opposite = True
                        break
                        
                if found_opposite:
                    continue
                    
                # Check numbers
                nums1 = set(c1.get("numbers", []))
                nums2 = set(c2.get("numbers", []))
                
                if nums1 and nums2 and not nums1.intersection(nums2):
                    # They have different numbers
                    n1_str = ", ".join(nums1)
                    n2_str = ", ".join(nums2)
                    contradictions.append({
                        "claim_a": c1.get("claim"),
                        "claim_b": c2.get("claim"),
                        "reason": f"conflicting numbers: {n1_str} vs {n2_str}"
                    })

    return contradictions
