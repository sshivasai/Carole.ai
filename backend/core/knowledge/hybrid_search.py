"""
# backend/core/knowledge/hybrid_search.py

Dual Hybrid Code Retrieval Engine (Semble Pattern).
Uses production rank_bm25 (BM25Okapi) for exact symbol matching and
Model2Vec static code embeddings for sub-250ms indexing & 1.5ms CPU inference,
fused via Reciprocal Rank Fusion (RRF).
"""

import re
import logging
import numpy as np
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

from core.knowledge.ast_parser import ASTChunk

logger = logging.getLogger("carole.hybrid_search")

# ─────────────────────────────────────────────────────────────────────────────
# Code Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

def tokenize_code(text: str) -> List[str]:
    """
    Code-aware tokenizer for BM25:
    Splits identifiers into snake_case and camelCase subwords while
    preserving the original full identifier for exact matching.
    Example: 'getUserById' -> ['getuserbyid', 'get', 'user', 'by', 'id']
    """
    if not text:
        return []

    tokens: List[str] = []
    raw_tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text)

    for tok in raw_tokens:
        tok_lower = tok.lower()
        tokens.append(tok_lower)

        # Split snake_case
        if "_" in tok:
            parts = [p.lower() for p in tok.split("_") if p]
            tokens.extend(parts)

        # Split camelCase / PascalCase
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)", tok)
        if len(camel_parts) > 1:
            tokens.extend([p.lower() for p in camel_parts if p])

    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Production BM25 Index (rank_bm25)
# ─────────────────────────────────────────────────────────────────────────────

class BM25Index:
    """
    Production BM25 index powered by rank-bm25 (BM25Okapi).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.bm25_model = None
        self.chunks: List[ASTChunk] = []

    def index_chunks(self, chunks: List[ASTChunk]) -> None:
        """Tokenizes and indexes ASTChunk objects using rank_bm25."""
        try:
            from rank_bm25 import BM25Plus as BM25Engine
        except ImportError:
            from rank_bm25 import BM25Okapi as BM25Engine

        self.chunks = chunks
        tokenized_corpus = []

        for chunk in chunks:
            text = f"{chunk.file_path} {chunk.name} {chunk.kind} {' '.join(chunk.params)} {' '.join(chunk.calls)} {chunk.code}"
            tokens = tokenize_code(text)
            tokenized_corpus.append(tokens)

        if tokenized_corpus:
            self.bm25_model = BM25Engine(tokenized_corpus, k1=self.k1, b=self.b)
        else:
            self.bm25_model = None

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """Returns top matching doc indices and BM25 scores."""
        if not self.bm25_model or not self.chunks:
            return []

        query_tokens = tokenize_code(query)
        if not query_tokens:
            return []

        scores = self.bm25_model.get_scores(query_tokens)
        scored_pairs = [(idx, float(score)) for idx, score in enumerate(scores) if score > 0.0]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
# Static CPU Code Embeddings (Model2Vec Semble Pattern)
# ─────────────────────────────────────────────────────────────────────────────

class StaticCodeEmbedder:
    """
    Lightweight CPU code embeddings using Model2Vec (minishlab/potion-base-8M).
    Zero GPU requirement, ~1.5ms query encoding time, sub-250ms workspace indexing.
    """

    _instance = None
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                from model2vec import StaticModel
                logger.info("⚡ [Semble] Loading static code embedding model (minishlab/potion-base-8M)...")
                cls._model = StaticModel.from_pretrained("minishlab/potion-base-8M")
                logger.info("⚡ [Semble] Static code embedding model loaded successfully.")
            except Exception as e:
                logger.warning("Could not load Model2Vec, semantic search will fallback: %s", e)
                cls._model = None
        return cls._model

    @classmethod
    def encode(cls, texts: List[str]) -> Optional[np.ndarray]:
        model = cls.get_model()
        if model is None:
            return None
        try:
            return model.encode(texts)
        except Exception as e:
            logger.debug("Model2Vec encode error: %s", e)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid Search Engine (BM25 + Static Embeddings + RRF)
# ─────────────────────────────────────────────────────────────────────────────

class HybridCodeSearch:
    """
    Dual Retrieval Pipeline combining BM25 exact symbol matching with
    static code vectors fused via Reciprocal Rank Fusion (RRF).
    """

    def __init__(self):
        self.bm25 = BM25Index()
        self.chunks: List[ASTChunk] = []
        self.embeddings: Optional[np.ndarray] = None
        self._ranker = None
        self._ranker_loaded = False

    def _get_ranker(self):
        if not self._ranker_loaded:
            try:
                from flashrank import Ranker
                self._ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
                logger.info("⚡ [HybridSearch] FlashRank cross-encoder reranker loaded.")
            except Exception as e:
                logger.debug("FlashRank unavailable, falling back to pure RRF: %s", e)
                self._ranker = None
            self._ranker_loaded = True
        return self._ranker

    def index_workspace_chunks(self, chunks: List[ASTChunk]) -> None:
        """Indexes workspace AST chunks for both BM25 and static embeddings."""
        self.chunks = chunks
        self.bm25.index_chunks(chunks)

        # Generate lightweight embeddings for code signatures + docstrings
        if chunks:
            texts = [
                f"{c.file_path} {c.kind} {c.name}({', '.join(c.params)}) {c.docstring or ''} {c.code[:200]}"
                for c in chunks
            ]
            self.embeddings = StaticCodeEmbedder.encode(texts)
        else:
            self.embeddings = None

    def search_vectors(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """Performs fast cosine similarity search over static code embeddings."""
        if self.embeddings is None or not self.chunks:
            return []

        query_vec = StaticCodeEmbedder.encode([query])
        if query_vec is None:
            return []

        # Cosine similarity
        norm_q = np.linalg.norm(query_vec[0])
        if norm_q == 0:
            return []

        norm_docs = np.linalg.norm(self.embeddings, axis=1)
        norm_docs = np.where(norm_docs == 0, 1e-9, norm_docs)

        scores = np.dot(self.embeddings, query_vec[0]) / (norm_docs * norm_q)
        scored_pairs = [(idx, float(score)) for idx, score in enumerate(scores)]
        scored_pairs.sort(key=lambda x: x[1], reverse=True)
        return scored_pairs[:top_k]

    def reciprocal_rank_fusion(
        self,
        bm25_ranked: List[Tuple[int, float]],
        vector_ranked: List[Tuple[int, float]],
        k: int = 60
    ) -> List[Tuple[int, float]]:
        """
        Computes Reciprocal Rank Fusion (RRF) scores:
        RRF_score(d) = sum(1 / (k + rank_m(d)))
        """
        rrf_scores: Dict[int, float] = defaultdict(float)

        for rank, (doc_idx, _) in enumerate(bm25_ranked, 1):
            rrf_scores[doc_idx] += 1.0 / (k + rank)

        for rank, (doc_idx, _) in enumerate(vector_ranked, 1):
            rrf_scores[doc_idx] += 1.0 / (k + rank)

        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_rrf

    async def search(
        self,
        query: str,
        top_k: int = 10,
        vector_search_fn: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Dual Hybrid Retrieval:
        1. BM25 lexical ranking (exact identifiers, stack traces).
        2. Static vector ranking (CPU Model2Vec / dense embeddings).
        3. Fused with Reciprocal Rank Fusion (RRF).
        """
        if not self.chunks:
            return []

        # 1. BM25 Lexical Ranking
        bm25_results = self.bm25.search(query, top_k=top_k * 2)

        # 2. Vector Ranking (prefer custom vector fn or built-in static Model2Vec)
        if vector_search_fn is not None:
            try:
                vector_results = await vector_search_fn(query, top_k=top_k * 2)
            except Exception:
                vector_results = self.search_vectors(query, top_k=top_k * 2)
        else:
            vector_results = self.search_vectors(query, top_k=top_k * 2)

        # 3. Reciprocal Rank Fusion
        if vector_results:
            fused = self.reciprocal_rank_fusion(bm25_results, vector_results, k=60)
        else:
            fused = [(idx, score) for idx, score in bm25_results]

        # 4. Neural Cross-Encoder Re-ranking via FlashRank (if available)
        ranker = self._get_ranker()
        final_ranked: List[Tuple[int, float]] = []

        if ranker is not None and fused:
            try:
                from flashrank import RerankRequest
                candidate_pool = fused[: max(top_k * 3, 15)]
                passages = [
                    {
                        "id": doc_idx,
                        "text": f"{self.chunks[doc_idx].file_path} {self.chunks[doc_idx].name} ({self.chunks[doc_idx].kind}): {self.chunks[doc_idx].code[:600]}"
                    }
                    for doc_idx, _ in candidate_pool
                ]
                rerank_req = RerankRequest(query=query, passages=passages)
                reranked = ranker.rerank(rerank_req)
                for item in reranked:
                    final_ranked.append((item["id"], float(item["score"])))
            except Exception as e:
                logger.debug("FlashRank rerank error, using RRF: %s", e)
                final_ranked = fused[:top_k]
        else:
            final_ranked = fused[:top_k]

        # 5. Assemble Top Snippets
        results = []
        for doc_idx, score in final_ranked[:top_k]:
            chunk = self.chunks[doc_idx]
            results.append({
                "file_path": chunk.file_path,
                "name": chunk.name,
                "kind": chunk.kind,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "code": chunk.code,
                "params": chunk.params,
                "docstring": chunk.docstring,
                "score": round(score, 4),
            })

        return results


# Global singleton instance
hybrid_code_search = HybridCodeSearch()
