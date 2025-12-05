# Retriever-Verwendung - Quick Reference

## 🎯 Übersicht

| Komponente | Retriever | Konfiguration | Latenz | Qualität |
|------------|-----------|---------------|--------|----------|
| **LLM1 Chat** | Hybrid Search (BM25+Lexical+RRF) | `LLM1_THIN_RETRIEVAL=1` ✅ | ~20ms | ⭐⭐⭐⭐ |
| **LLM2 Angebot** | Hybrid + Vector + RRF | `COMBINE_HYBRID_VECTOR=1` ✅ | ~70-120ms | ⭐⭐⭐⭐⭐ |
| **API Search** | Hybrid + Vector + RRF | `COMBINE_HYBRID_VECTOR=1` ✅ | ~70-120ms | ⭐⭐⭐⭐⭐ |

**Defaults**: Beide aktiviert ✅

---

## 📋 Was wird wo verwendet?

### LLM1 (`chat_turn()`)
```
LLM1_THIN_RETRIEVAL=1
  ↓
_build_catalog_candidates()
  ↓
search_catalog_thin() → hybrid_search()
  ↓
BM25 + Lexical + RRF
  ↓
Katalog-Vorschläge in Chat-Antwort
```

### LLM2 (`generate_offer_positions()`)
```
COMBINE_HYBRID_VECTOR=1
  ↓
find_exact_catalog_lines()
  ↓
hybrid_search() + vector_search_fn()
  ↓
BM25 + Lexical + Vector + RRF
  ↓
Context-Erweiterung für LLM2 Prompt
```

### API (`/api/catalog/search`)
```
COMBINE_HYBRID_VECTOR=1
  ↓
search_catalog()
  ↓
hybrid_search() + vector_search_fn()
  ↓
BM25 + Lexical + Vector + RRF
  ↓
Direkte Produktsuche
```

---

## 🔧 Konfiguration

### Standard (Empfohlen)
```bash
LLM1_THIN_RETRIEVAL=1          # Hybrid Search für LLM1
COMBINE_HYBRID_VECTOR=1        # Hybrid + Vector für LLM2 & API
```

### Performance-Modus (Schnell)
```bash
LLM1_THIN_RETRIEVAL=0          # Kein Retriever für LLM1
COMBINE_HYBRID_VECTOR=0        # Nur Vector für LLM2 & API
```

---

## 📊 Retriever-Details

### Hybrid Search (`thin.py`)
- **BM25**: Keyword-Matches (TF/IDF)
- **Lexical**: Fuzzy-Matching, Synonyme
- **RRF**: Kombiniert Rankings
- **Ohne Vector**: ~20ms
- **Mit Vector**: ~70-120ms

### Vector Search (`index_manager.py`)
- **Embeddings**: MiniLM-L6-v2
- **Similarity**: Cosine
- **Latenz**: ~50-100ms
- **Stärke**: Semantische Ähnlichkeit

### Kombiniert (Hybrid + Vector)
- **Alle 3 Methoden**: BM25 + Lexical + Vector
- **RRF**: Fusioniert alle Rankings
- **Latenz**: ~70-120ms
- **Qualität**: Beste Ergebnisse

---

## 🎯 Wann welcher Retriever?

| Use-Case | Retriever | Warum |
|----------|-----------|-------|
| **LLM1 Chat** | Hybrid (ohne Vector) | Schnell, gute Qualität, deterministisch |
| **LLM2 Angebot** | Hybrid + Vector | Beste Qualität, alle Fälle abgedeckt |
| **API Search** | Hybrid + Vector | Beste Qualität, nicht interaktiv |
| **Material-Validierung** | Hybrid (ohne Vector) | Schnell, deterministisch |

---

## ⚡ Performance-Vergleich

| Methode | Latenz | Exakte Matches | Tippfehler | Semantisch |
|---------|--------|----------------|------------|------------|
| **Nur Hybrid** | ~20ms | ✅✅✅ | ✅✅✅ | ❌ |
| **Nur Vector** | ~50-100ms | ✅✅ | ❌ | ✅✅✅ |
| **Hybrid + Vector** | ~70-120ms | ✅✅✅ | ✅✅✅ | ✅✅✅ |

---

## 🔍 Code-Stellen

### LLM1
- `quote_service.py:3106` - `_build_catalog_candidates()`
- `quote_service.py:1738` - `_run_thin_catalog_search()`

### LLM2
- `quote_service.py:3403` - `find_exact_catalog_lines()`
- `quote_service.py:3424` - Hybrid + Vector Search

### API
- `quote_service.py:2880` - `search_catalog()`
- `quote_service.py:2908` - `hybrid_search()` mit Vector

---

**Stand**: 2025-01-27  
**Version**: 1.0


