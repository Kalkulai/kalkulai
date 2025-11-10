from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from math import sqrt
from datetime import datetime

from backend.store.catalog_store import get_active_products

logger = logging.getLogger("kalkulai.index")

try:
    from docarray import Document, DocumentArray
    from docarray.index.backends.inmemory import InMemoryExactNNIndex as DocArrayExactNN

    _DOCARRAY_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback implementation
    _DOCARRAY_AVAILABLE = False

    class Document:  # type: ignore[override]
        def __init__(self, id: Optional[str] = None, text: str = "", embedding=None, tags=None):
            self.id = id
            self.text = text
            self.embedding = embedding
            self.tags = tags or {}

    class DocumentArray(list):  # type: ignore[override]
        pass

    class DocArrayExactNN:  # Very small cosine index
        def __init__(self, docs: Optional[DocumentArray] = None, **_: Any):
            self._docs: Dict[str, Document] = {}
            if docs:
                self.index(docs)

        def index(self, docs: DocumentArray):
            for doc in docs:
                if doc.id is None:
                    continue
                self._docs[doc.id] = doc

        def delete(self, ids: List[str]):
            for entry in ids:
                self._docs.pop(entry, None)

        def search(self, query_doc: Document, limit: int = 5):
            if not query_doc.embedding:
                return []
            q = query_doc.embedding
            results = []
            for doc in self._docs.values():
                emb = doc.embedding
                if not emb:
                    continue
                denom = _vector_norm(q) * _vector_norm(emb)
                score = _dot(q, emb) / denom if denom else 0.0
                results.append((score, doc))
            results.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in results[:limit]]

        @property
        def doc_count(self) -> int:
            return len(self._docs)


EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_ST_CLASS = None
_EMBEDDER: Optional[Any] = None
_INDEX_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        try:
            from sentence_transformers import SentenceTransformer as _ST  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers is required for the dynamic retriever index."
            ) from exc
        _EMBEDDER = _ST(EMBED_MODEL)
    return _EMBEDDER


def _product_to_text(product: Dict[str, Any]) -> str:
    name = product.get("name") or ""
    description = product.get("description") or ""
    return f"{name}. {description}".strip() or name


def _to_vector(raw) -> List[float]:
    if raw is None:
        return []
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    return [float(x) for x in raw]


def _dot(a: List[float], b: List[float]) -> float:
    length = min(len(a), len(b))
    return float(sum(a[i] * b[i] for i in range(length)))


def _vector_norm(vec: List[float]) -> float:
    return sqrt(sum(v * v for v in vec))


def _build_docs(products: List[Dict[str, Any]]) -> DocumentArray:
    texts = [_product_to_text(prod) for prod in products]
    embedder = _get_embedder()
    embeddings = embedder.encode(texts) if texts else []
    docs = DocumentArray()
    for prod, text, emb in zip(products, texts, embeddings):
        doc = Document(
            id=str(prod["sku"]),
            text=text,
            embedding=_to_vector(emb),
            tags={"sku": prod["sku"], "name": prod.get("name", ""), "text": text},
        )
        docs.append(doc)
    return docs


def _build_index(company_id: str) -> DocArrayExactNN:
    products = get_active_products(company_id)
    docs = _build_docs(products)
    index = DocArrayExactNN(docs=docs, metric="cosine") if _DOCARRAY_AVAILABLE else DocArrayExactNN(docs=docs)
    logger.info("index built for company=%s docs=%d", company_id, len(docs))
    return index


def ensure_index(company_id: str) -> DocArrayExactNN:
    with _CACHE_LOCK:
        entry = _INDEX_CACHE.get(company_id)
        if entry:
            return entry["index"]
    return rebuild_index(company_id)


def ensure_company_index(company_id: str) -> DocArrayExactNN:
    """Compatibility helper for callers that expect explicit naming."""

    return ensure_index(company_id)


def rebuild_index(company_id: str) -> DocArrayExactNN:
    index = _build_index(company_id)
    with _CACHE_LOCK:
        _INDEX_CACHE[company_id] = {
            "index": index,
            "doc_count": _get_doc_count(index),
            "last_build_ts": time.time(),
        }
    return index


def update_index_incremental(company_id: str, changed_skus: List[str]) -> None:
    if not changed_skus:
        return
    index = ensure_index(company_id)
    active_map = {prod["sku"]: prod for prod in get_active_products(company_id)}
    embedder = _get_embedder()
    upsert_docs = DocumentArray()
    removed = 0
    for sku in changed_skus:
        prod = active_map.get(sku)
        if prod:
            text = _product_to_text(prod)
            embedding = _to_vector(embedder.encode([text])[0])
            doc = Document(
                id=sku,
                text=text,
                embedding=embedding,
                tags={"sku": sku, "name": prod.get("name", ""), "text": text},
            )
            upsert_docs.append(doc)
        else:
            try:
                index.delete([sku])
                removed += 1
            except Exception:
                pass
    if upsert_docs:
        index.index(upsert_docs)
        logger.info("index upsert company=%s count=%d", company_id, len(upsert_docs))
    if removed:
        logger.info("index delete company=%s count=%d", company_id, removed)
    with _CACHE_LOCK:
        entry = _INDEX_CACHE.get(company_id)
        if entry:
            entry["doc_count"] = _get_doc_count(index)
            entry["last_build_ts"] = time.time()


def update_index(company_id: str, skus: List[str]) -> None:
    """Update embeddings for specific *skus*. Empty lists trigger a rebuild."""

    if not skus:
        rebuild_index(company_id)
        return
    update_index_incremental(company_id, skus)


def index_stats(company_id: str) -> Dict[str, Any]:
    backend_name = "docarray" if _DOCARRAY_AVAILABLE else "fallback"
    with _CACHE_LOCK:
        entry = _INDEX_CACHE.get(company_id)
        if not entry:
            return {
                "company_id": company_id,
                "docs": 0,
                "last_build_ts": None,
                "built_at": None,
                "backend": backend_name,
            }
        timestamp = entry.get("last_build_ts")
        iso_ts = datetime.utcfromtimestamp(timestamp).isoformat() if timestamp is not None else None
        return {
            "company_id": company_id,
            "docs": entry.get("doc_count", 0),
            "last_build_ts": timestamp,
            "built_at": iso_ts,
            "backend": backend_name,
        }


def get_index_stats(company_id: str) -> Dict[str, Any]:
    """Backward compatible wrapper."""

    return index_stats(company_id)


def search_index(company_id: str, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    index = ensure_index(company_id)
    embedder = _get_embedder()
    embedding = _to_vector(embedder.encode([query_text])[0])
    query_doc = Document(embedding=embedding)
    if _DOCARRAY_AVAILABLE:
        results = index.search(query_doc, limit=top_k)
        if hasattr(results, "documents"):
            docs = results.documents
        else:
            docs = results
    else:
        docs = index.search(query_doc, limit=top_k)
    hits: List[Dict[str, Any]] = []
    for doc in docs:
        tags = getattr(doc, "tags", {}) or {}
        hits.append(
            {
                "sku": tags.get("sku"),
                "name": tags.get("name"),
                "text": tags.get("text") or getattr(doc, "text", ""),
            }
        )
    return hits


def _get_doc_count(index: DocArrayExactNN) -> int:
    for attr in ("doc_count", "num_docs"):
        if hasattr(index, attr):
            return int(getattr(index, attr))
    if hasattr(index, "__len__"):
        try:
            return len(index)  # type: ignore[arg-type]
        except TypeError:
            pass
    if hasattr(index, "_docs"):
        return len(getattr(index, "_docs"))
    return 0
