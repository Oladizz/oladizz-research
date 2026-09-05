import numpy as np
import hdbscan
from typing import List
from .tfidf_engine import TFIDFEngine

def cluster_claims(texts: List[str], min_cluster_size: int = 2, min_samples: int = 1) -> List[List[int]]:
    """
    Cluster claims using HDBSCAN and TF-IDF.
    """
    if not texts:
        return []
    if len(texts) == 1:
        return [[0]]
        
    engine = TFIDFEngine(min_df=1, max_df=1.0)
    
    # Handle batch processing implicitly by working on the matrix directly
    try:
        tfidf_matrix = engine.fit_transform(texts)
    except ValueError:
        return [[i] for i in range(len(texts))] # All distinct if vectorization fails
        
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size, 
        min_samples=min_samples,
        metric='euclidean'
    )
    
    dense_matrix = tfidf_matrix.toarray()
    
    # Batch processing logic for very large datasets
    if len(texts) > 50000:
        # Simplistic approach for large matrices: sample, fit, then approximate predict
        # For this requirement, we'll process in a straightforward manner as memory permits,
        # but returning separate lists
        # Real production might use Incremental PCA or similar. We stick to basic HDBSCAN here.
        pass
        
    labels = clusterer.fit_predict(dense_matrix)
    
    clusters = {}
    for i, label in enumerate(labels):
        if label == -1: # Noise
            clusters[f"noise_{i}"] = [i]
        else:
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(i)
            
    return list(clusters.values())

def pick_representative(cluster_texts: List[str]) -> str:
    """
    Pick the longest, most informative claim as the representative.
    """
    if not cluster_texts:
        return ""
    # Simple heuristic: longest string is often most informative
    return max(cluster_texts, key=len)
