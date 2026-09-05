import numpy as np
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import scipy.sparse

class TFIDFEngine:
    """
    Replaces Gemini embeddings with TF-IDF vectorization.
    """
    def __init__(self, max_features: int = 50000, ngram_range=(1,2), min_df=2, max_df=0.95):
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            min_df=min_df,
            max_df=max_df
        )
        self.tfidf_matrix = None
        self.texts = []

    def fit_transform(self, texts: List[str]) -> scipy.sparse.csr_matrix:
        """
        Fit and transform texts in one call.
        """
        self.texts = texts
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        return self.tfidf_matrix

    def get_similarity_matrix(self) -> np.ndarray:
        """
        Pairwise cosine similarity.
        """
        if self.tfidf_matrix is None:
            raise ValueError("Must call fit_transform first.")
        return cosine_similarity(self.tfidf_matrix)

    def get_topic_similarities(self, topic: str, texts: List[str]) -> List[float]:
        """
        Similarity of each text to a topic string.
        """
        if not texts:
            return []
        
        # Transform topic and texts using a fresh vectorizer to avoid state side-effects
        # or fit on texts, then transform topic
        vectorizer = TfidfVectorizer(
            max_features=self.vectorizer.max_features,
            ngram_range=self.vectorizer.ngram_range,
            min_df=1, # Change min_df to 1 so small text batches don't break
            max_df=1.0
        )
        try:
            texts_matrix = vectorizer.fit_transform(texts)
            topic_matrix = vectorizer.transform([topic])
            sims = cosine_similarity(topic_matrix, texts_matrix).flatten()
            return sims.tolist()
        except ValueError:
            # Fallback if texts are empty or only stop words
            return [0.0] * len(texts)
