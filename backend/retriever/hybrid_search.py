"""
Hybrid Search: BM25 + Vector + Lexical with RRF + Re-Ranking
=============================================================

This module implements a production-grade hybrid search combining:
1. BM25 (Keyword Search) - Great for exact matches
2. Vector Search (Embeddings) - Great for semantic similarity  
3. Lexical Search (Token Overlap) - Fast and deterministic
4. Re-Ranking (Cross-Encoder) - Final relevance sorting

Results are combined using Reciprocal Rank Fusion (RRF), then optionally
re-ranked with a Cross-Encoder for maximum relevance.
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from shared.normalize import normalize_query, tokenize, apply_synonyms, load_synonyms

_DEFAULT_SYNONYMS_PATH = Path(__file__).parent.parent / "shared" / "normalize" / "synonyms.yaml"

# Cross-Encoder for re-ranking (optional)
_RERANKER = None
_RERANKER_ENABLED = os.getenv("ENABLE_RERANKER", "0") == "1"


def _get_reranker():
    """Lazy-load the cross-encoder reranker."""
    global _RERANKER
    if _RERANKER is not None:
        return _RERANKER
    
    if not _RERANKER_ENABLED:
        return None
    
    try:
        from sentence_transformers import CrossEncoder
        # Use a lightweight German-compatible model
        _RERANKER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=256)
        return _RERANKER
    except ImportError:
        return None
    except Exception:
        return None


def rerank_results(
    query: str,
    results: List[Dict[str, Any]],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Re-rank results using a Cross-Encoder for better relevance.
    
    Args:
        query: Original search query
        results: List of search results with 'name' field
        top_k: Number of results to return after re-ranking
    
    Returns:
        Re-ranked results
    """
    if not results:
        return []
    
    reranker = _get_reranker()
    if reranker is None:
        # No reranker available, return as-is
        return results[:top_k]
    
    # Prepare query-document pairs
    pairs = []
    for r in results:
        doc_text = f"{r.get('name', '')} {r.get('description', '')}"
        pairs.append([query, doc_text])
    
    try:
        # Get relevance scores from cross-encoder
        scores = reranker.predict(pairs)
        
        # Combine with original results
        scored_results = list(zip(results, scores))
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # Return top_k with updated scores
        reranked = []
        for result, score in scored_results[:top_k]:
            result = dict(result)  # Copy
            result["rerank_score"] = float(score)
            result["score_final"] = float(score)  # Override with rerank score
            reranked.append(result)
        
        return reranked
    except Exception:
        # Fallback to original results
        return results[:top_k]


# ============================================================================
# BM25 Implementation
# ============================================================================

@dataclass
class BM25Index:
    """Simple BM25 index for product search."""
    
    # BM25 parameters
    k1: float = 1.5  # Term frequency saturation
    b: float = 0.75  # Length normalization
    
    # Index data
    doc_freqs: Dict[str, int] = None  # Document frequency per term
    doc_lengths: Dict[str, int] = None  # Document length per SKU
    avg_doc_length: float = 0.0
    total_docs: int = 0
    inverted_index: Dict[str, Set[str]] = None  # term -> set of SKUs
    doc_term_freqs: Dict[str, Dict[str, int]] = None  # SKU -> {term: freq}
    
    def __post_init__(self):
        self.doc_freqs = self.doc_freqs or {}
        self.doc_lengths = self.doc_lengths or {}
        self.inverted_index = self.inverted_index or defaultdict(set)
        self.doc_term_freqs = self.doc_term_freqs or {}


def build_bm25_index(products: List[Dict[str, Any]]) -> BM25Index:
    """Build BM25 index from product list."""
    index = BM25Index()
    
    doc_freqs: Dict[str, int] = defaultdict(int)
    doc_lengths: Dict[str, int] = {}
    inverted_index: Dict[str, Set[str]] = defaultdict(set)
    doc_term_freqs: Dict[str, Dict[str, int]] = {}
    
    total_length = 0
    
    for product in products:
        sku = product.get("sku", "")
        if not sku:
            continue
            
        # Build document text from name, description, tags
        text_parts = [
            product.get("name", ""),
            product.get("description", ""),
            product.get("tags", ""),
            product.get("category", ""),
        ]
        doc_text = " ".join(str(p) for p in text_parts if p)
        
        # Tokenize
        tokens = tokenize(doc_text)
        if not tokens:
            continue
        
        # Count term frequencies
        term_freqs: Dict[str, int] = defaultdict(int)
        for token in tokens:
            term_freqs[token] += 1
            inverted_index[token].add(sku)
        
        # Update document frequency (how many docs contain each term)
        for term in term_freqs:
            doc_freqs[term] += 1
        
        doc_term_freqs[sku] = dict(term_freqs)
        doc_lengths[sku] = len(tokens)
        total_length += len(tokens)
    
    index.doc_freqs = dict(doc_freqs)
    index.doc_lengths = doc_lengths
    index.inverted_index = dict(inverted_index)
    index.doc_term_freqs = doc_term_freqs
    index.total_docs = len(doc_lengths)
    index.avg_doc_length = total_length / max(len(doc_lengths), 1)
    
    return index


def bm25_score(
    query_tokens: Set[str],
    sku: str,
    index: BM25Index,
) -> float:
    """Calculate BM25 score for a document."""
    if sku not in index.doc_term_freqs:
        return 0.0
    
    score = 0.0
    doc_length = index.doc_lengths.get(sku, 0)
    term_freqs = index.doc_term_freqs[sku]
    
    for term in query_tokens:
        if term not in term_freqs:
            continue
        
        tf = term_freqs[term]
        df = index.doc_freqs.get(term, 0)
        
        # IDF component
        idf = math.log((index.total_docs - df + 0.5) / (df + 0.5) + 1)
        
        # TF component with length normalization
        tf_norm = (tf * (index.k1 + 1)) / (
            tf + index.k1 * (1 - index.b + index.b * doc_length / max(index.avg_doc_length, 1))
        )
        
        score += idf * tf_norm
    
    return score


def bm25_search(
    query: str,
    index: BM25Index,
    products_by_sku: Dict[str, Dict[str, Any]],
    top_k: int = 50,
) -> List[Tuple[str, float]]:
    """Search using BM25 and return (sku, score) pairs."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    
    # Find candidate documents (any doc containing at least one query term)
    candidate_skus: Set[str] = set()
    for token in query_tokens:
        if token in index.inverted_index:
            candidate_skus.update(index.inverted_index[token])
    
    # Score candidates
    scored: List[Tuple[str, float]] = []
    for sku in candidate_skus:
        if sku not in products_by_sku:
            continue
        score = bm25_score(query_tokens, sku, index)
        if score > 0:
            scored.append((sku, score))
    
    # Sort by score descending, tie-break by SKU ascending for determinism
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:top_k]


# ============================================================================
# Reciprocal Rank Fusion (RRF)
# ============================================================================

def reciprocal_rank_fusion(
    rankings: List[List[Tuple[str, float]]],
    k: int = 60,
) -> List[Tuple[str, float]]:
    """
    Combine multiple rankings using Reciprocal Rank Fusion.
    
    RRF Score = Σ(1 / (k + rank_i)) for each ranking list
    
    Args:
        rankings: List of rankings, each is a list of (sku, score) tuples
        k: Constant to prevent high scores for top-ranked items (default: 60)
    
    Returns:
        Combined ranking as list of (sku, rrf_score) tuples
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    
    for ranking in rankings:
        for rank, (sku, _) in enumerate(ranking, start=1):
            rrf_scores[sku] += 1.0 / (k + rank)
    
    # Sort by RRF score descending, tie-break by SKU ascending for determinism
    combined = [(sku, score) for sku, score in rrf_scores.items()]
    combined.sort(key=lambda x: (-x[1], x[0]))
    
    return combined


# ============================================================================
# Hybrid Search
# ============================================================================

_BM25_INDEX: Optional[BM25Index] = None
_BM25_INDEX_COMPANY: Optional[str] = None


def _get_or_build_bm25_index(
    products: List[Dict[str, Any]],
    company_id: str,
) -> BM25Index:
    """Get cached BM25 index or build new one."""
    global _BM25_INDEX, _BM25_INDEX_COMPANY
    
    if _BM25_INDEX is None or _BM25_INDEX_COMPANY != company_id:
        _BM25_INDEX = build_bm25_index(products)
        _BM25_INDEX_COMPANY = company_id
    
    return _BM25_INDEX


def invalidate_bm25_cache():
    """Invalidate BM25 cache (call after product updates)."""
    global _BM25_INDEX, _BM25_INDEX_COMPANY
    _BM25_INDEX = None
    _BM25_INDEX_COMPANY = None


def hybrid_search(
    query: str,
    catalog_items: List[Dict[str, Any]],
    top_k: int = 10,
    company_id: str = "demo",
    synonyms_path: Optional[str] = None,
    vector_search_fn: Optional[callable] = None,
) -> List[Dict[str, Any]]:
    """
    Perform hybrid search combining BM25, Vector, and Lexical search.
    
    Args:
        query: Search query
        catalog_items: List of product dicts
        top_k: Number of results to return
        company_id: Company ID for caching
        synonyms_path: Path to synonyms file
        vector_search_fn: Optional function for vector search
    
    Returns:
        List of product dicts with scores
    """
    if not query or not catalog_items:
        return []
    
    # Build lookup dicts
    products_by_sku: Dict[str, Dict[str, Any]] = {
        p["sku"]: p for p in catalog_items if p.get("sku")
    }
    products_by_name: Dict[str, Dict[str, Any]] = {
        p["name"].lower(): p for p in catalog_items if p.get("name")
    }
    
    # Load synonyms (use default path if not specified)
    synonyms = {}
    effective_synonyms_path = synonyms_path or str(_DEFAULT_SYNONYMS_PATH)
    if Path(effective_synonyms_path).exists():
        try:
            synonyms = load_synonyms(effective_synonyms_path)
        except Exception:
            pass
    
    # Expand query with synonyms
    query_tokens = tokenize(query)
    if synonyms:
        query_tokens = apply_synonyms(query_tokens, synonyms)
    
    # -------------------------------------------------------------------------
    # 1. BM25 Search
    # -------------------------------------------------------------------------
    bm25_index = _get_or_build_bm25_index(catalog_items, company_id)
    bm25_results = bm25_search(query, bm25_index, products_by_sku, top_k=50)
    
    # -------------------------------------------------------------------------
    # 2. Lexical Search (Token Overlap)
    # -------------------------------------------------------------------------
    lexical_results: List[Tuple[str, float]] = []
    for product in catalog_items:
        sku = product.get("sku", "")
        name = product.get("name", "")
        if not sku or not name:
            continue
        
        # Tokenize product
        product_tokens = tokenize(name)
        if synonyms:
            product_tokens = apply_synonyms(product_tokens, synonyms)
        
        # Calculate overlap
        overlap = len(query_tokens & product_tokens)
        if overlap > 0:
            overlap_ratio = overlap / max(len(query_tokens), 1)
            lexical_results.append((sku, overlap_ratio))
    
    # Sort by score descending, tie-break by SKU ascending for determinism
    lexical_results.sort(key=lambda x: (-x[1], x[0]))
    lexical_results = lexical_results[:50]
    
    # -------------------------------------------------------------------------
    # 3. Vector Search (if available)
    # -------------------------------------------------------------------------
    vector_results: List[Tuple[str, float]] = []
    if vector_search_fn:
        try:
            hits = vector_search_fn(query, top_k=50)
            for hit in hits:
                sku = hit.get("sku", "")
                score = hit.get("score", 0.5)
                if sku:
                    vector_results.append((sku, score))
        except Exception:
            pass
    
    # -------------------------------------------------------------------------
    # 4. Combine with RRF
    # -------------------------------------------------------------------------
    rankings = [r for r in [bm25_results, lexical_results, vector_results] if r]
    
    if not rankings:
        return []
    
    combined = reciprocal_rank_fusion(rankings, k=60)
    
    # -------------------------------------------------------------------------
    # 5. Build result list (get more candidates for re-ranking)
    # -------------------------------------------------------------------------
    candidates_for_rerank = min(50, len(combined))  # Get up to 50 for re-ranking
    results: List[Dict[str, Any]] = []
    for sku, rrf_score in combined[:candidates_for_rerank]:
        product = products_by_sku.get(sku)
        if not product:
            continue
        
        results.append({
            "sku": sku,
            "name": product.get("name"),
            "description": product.get("description", ""),
            "unit": product.get("unit"),
            "category": product.get("category"),
            "price_eur": product.get("price_eur"),
            "volume_l": product.get("volume_l"),
            "score_final": round(rrf_score, 4),
            "search_type": "hybrid",
        })
    
    # -------------------------------------------------------------------------
    # 6. Re-Ranking (optional, if ENABLE_RERANKER=1)
    # -------------------------------------------------------------------------
    if _RERANKER_ENABLED and len(results) > top_k:
        results = rerank_results(query, results, top_k=top_k)
        for r in results:
            r["search_type"] = "hybrid+rerank"
    else:
        results = results[:top_k]
    
    return results


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    # Test data
    test_products = [
        {"sku": "sku_latex_10", "name": "Latexfarbe weiß 10L", "description": "Scheuerbeständige Latexfarbe", "category": "paint", "price_eur": 89.9},
        {"sku": "sku_latex_5", "name": "Latexfarbe weiß 5L", "description": "Scheuerbeständige Latexfarbe", "category": "paint", "price_eur": 49.9},
        {"sku": "sku_tiefengrund", "name": "Tiefengrund lösemittelfrei 10L", "description": "Grundierung für saugende Untergründe", "category": "primer", "price_eur": 24.9},
        {"sku": "sku_dispersion", "name": "Dispersionsfarbe weiß matt 10L", "description": "Hochdeckende Innenfarbe", "category": "paint", "price_eur": 39.9},
    ]
    
    print("=== BM25 Index ===")
    index = build_bm25_index(test_products)
    print(f"Total docs: {index.total_docs}")
    print(f"Avg doc length: {index.avg_doc_length:.2f}")
    print(f"Terms indexed: {len(index.doc_freqs)}")
    
    print("\n=== BM25 Search: 'Latexfarbe weiß' ===")
    products_by_sku = {p["sku"]: p for p in test_products}
    results = bm25_search("Latexfarbe weiß", index, products_by_sku, top_k=5)
    for sku, score in results:
        print(f"  {sku}: {score:.4f}")
    
    print("\n=== Hybrid Search: 'weiße Farbe für Wände' ===")
    results = hybrid_search("weiße Farbe für Wände", test_products, top_k=5)
    for r in results:
        print(f"  {r['sku']}: {r['name']} (score: {r['score_final']:.4f})")
    
    print("\n=== RRF Test ===")
    ranking1 = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    ranking2 = [("b", 0.95), ("a", 0.85), ("d", 0.6)]
    combined = reciprocal_rank_fusion([ranking1, ranking2])
    print("Combined ranking:")
    for sku, score in combined[:5]:
        print(f"  {sku}: {score:.4f}")

