"""Source library retrieval: models, ingestion, embeddings, search, and rerank."""

from retrieval.passage_search import search
from retrieval.schemas import RetrievedPassage

__all__ = ["RetrievedPassage", "search"]
