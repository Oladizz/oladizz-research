import re
import random
import hashlib
from typing import List, Dict, Set
from collections import defaultdict

class LSHDedup:
    """
    Locality Sensitive Hashing for content dedup at 1M scale.
    """
    def __init__(self, num_bands: int = 20, rows_per_band: int = 5):
        self.num_bands = num_bands
        self.rows_per_band = rows_per_band
        self.num_permutations = num_bands * rows_per_band
        self.buckets = defaultdict(list)
        self.doc_store = {}
        self.doc_signatures = {}
        
        # Generate hash functions
        self.hash_coeffs = [(random.randint(1, 1000000), random.randint(0, 1000000)) 
                            for _ in range(self.num_permutations)]
        self.prime = 4294967291 # Large prime for hashing
        
        self.total_docs = 0
        self.duplicates_found = 0

    def _shingles(self, text: str) -> Set[int]:
        words = text.lower().split()
        shingles = set()
        for i in range(len(words) - 2):
            shingle = " ".join(words[i:i+3])
            shingles.add(hash(shingle) & 0xffffffff)
        return shingles

    def compute_minhash(self, text: str, num_permutations: int = 100) -> List[int]:
        """Compute MinHash signature."""
        shingles = self._shingles(text)
        signature = [float('inf')] * self.num_permutations
        
        if not shingles:
            return [0] * self.num_permutations

        for s in shingles:
            for i, (a, b) in enumerate(self.hash_coeffs):
                h = (a * s + b) % self.prime
                if h < signature[i]:
                    signature[i] = h
        return signature

    def _jaccard_similarity(self, sig1: List[int], sig2: List[int]) -> float:
        matches = sum(1 for i, j in zip(sig1, sig2) if i == j)
        return matches / len(sig1)

    def add_document(self, doc_id: str, text: str) -> bool:
        """
        Returns False if near-duplicate found.
        """
        self.total_docs += 1
        signature = self.compute_minhash(text)
        
        candidates = set()
        for i in range(self.num_bands):
            band = tuple(signature[i * self.rows_per_band : (i + 1) * self.rows_per_band])
            bucket_key = (i, hash(band))
            for cand_id in self.buckets[bucket_key]:
                candidates.add(cand_id)
                
        # Verify candidates
        is_duplicate = False
        for cand_id in candidates:
            cand_sig = self.doc_signatures[cand_id]
            sim = self._jaccard_similarity(signature, cand_sig)
            if sim > 0.8:
                is_duplicate = True
                break
                
        if is_duplicate:
            self.duplicates_found += 1
            return False
            
        # Store if not duplicate
        self.doc_store[doc_id] = text
        self.doc_signatures[doc_id] = signature
        for i in range(self.num_bands):
            band = tuple(signature[i * self.rows_per_band : (i + 1) * self.rows_per_band])
            bucket_key = (i, hash(band))
            self.buckets[bucket_key].append(doc_id)
            
        return True

    def find_duplicates(self, doc_id: str) -> List[str]:
        """Find all near-duplicate doc IDs"""
        if doc_id not in self.doc_signatures:
            return []
            
        signature = self.doc_signatures[doc_id]
        candidates = set()
        for i in range(self.num_bands):
            band = tuple(signature[i * self.rows_per_band : (i + 1) * self.rows_per_band])
            bucket_key = (i, hash(band))
            for cand_id in self.buckets[bucket_key]:
                if cand_id != doc_id:
                    candidates.add(cand_id)
                    
        duplicates = []
        for cand_id in candidates:
            cand_sig = self.doc_signatures[cand_id]
            if self._jaccard_similarity(signature, cand_sig) > 0.8:
                duplicates.append(cand_id)
                
        return duplicates

    def get_stats(self) -> Dict:
        return {
            "total_docs": self.total_docs,
            "unique_docs": len(self.doc_store),
            "duplicates_found": self.duplicates_found
        }
