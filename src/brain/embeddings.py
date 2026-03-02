"""Local embeddings using sentence-transformers.

No OpenAI dependency. Runs 100% locally on CPU.
"""

from __future__ import annotations

import json
import logging
import numpy as np
from typing import List, Union

logger = logging.getLogger(__name__)

# Model cache
_model = None
_model_name = "all-MiniLM-L6-v2"
_dimensions = 384


class LocalEmbedder:
    """Local sentence transformer for embeddings.
    
    Uses all-MiniLM-L6-v2 (80MB download, runs on CPU).
    384-dimensional embeddings, good enough for semantic search.
    """
    
    def __init__(self, model_name: str = _model_name):
        self.model_name = model_name
        self._model = None
        self._dimensions = _dimensions
    
    def _load_model(self):
        """Lazy load the model."""
        global _model
        if _model is not None:
            self._model = _model
            return
            
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            _model = SentenceTransformer(self.model_name)
            self._model = _model
            logger.info(f"Embedding model loaded ({self._dimensions} dims)")
        except ImportError:
            logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
            raise
    
    def encode(self, text: Union[str, List[str]]) -> np.ndarray:
        """Encode text to embedding vector(s).
        
        Args:
            text: String or list of strings to encode
            
        Returns:
            Numpy array of shape (dims,) for single string or (n, dims) for list
        """
        if self._model is None:
            self._load_model()
        
        # Normalize embeddings for cosine similarity
        return self._model.encode(text, normalize_embeddings=True)
    
    def encode_single(self, text: str) -> bytes:
        """Encode single text to bytes for SQLite storage.
        
        Returns:
            Float32 bytes
        """
        embedding = self.encode(text)
        if len(embedding.shape) > 1:
            embedding = embedding[0]
        return embedding.astype(np.float32).tobytes()
    
    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.
        
        Vectors should already be normalized from encode().
        """
        return float(np.dot(a, b))


def get_embedder() -> LocalEmbedder:
    """Get singleton embedder instance."""
    return LocalEmbedder()
