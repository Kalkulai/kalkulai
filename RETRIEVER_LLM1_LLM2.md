# Retriever-Verwendung: LLM1 vs LLM2

## Übersicht

| LLM | Retriever | Verwendung | Konfiguration |
|-----|-----------|------------|---------------|
| **LLM1** | **Hybrid Search (thin.py)** | Katalog-Vorschläge während Chat | `LLM1_THIN_RETRIEVAL=1` |
| **LLM1** | **Kein Retriever** | Standard Chat (ohne Vorschläge) | `LLM1_THIN_RETRIEVAL=0` (default) |
| **LLM2** | **Vector Index (index_manager)** | Context-Erweiterung für Angebotsgenerierung | Immer (wenn `retriever` vorhanden) |

---

## LLM1 (Chat/Erfassung)

### Chain-Struktur
```python
# llm.py, Zeile 259
chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1)
# → KEIN Retriever direkt in Chain1 integriert
```

### Retriever-Verwendung

#### **Option A: Mit Thin Search (Hybrid Search)**
**Aktivierung**: `LLM1_THIN_RETRIEVAL=1`

**Code-Stelle**: `quote_service.py`, Zeile 3106-3130
```python
if ctx.llm1_thin_retrieval and lookup_materials:
    catalog_candidates = _build_catalog_candidates(lookup_materials, ctx, ...)
    # → Nutzt _run_thin_catalog_search() (Hybrid Search)
    # → Zeigt Produktvorschläge in Chat-Antwort
```

**Funktion**: `_build_catalog_candidates()` (Zeile 1717)
- Nutzt `_run_thin_catalog_search()` → `search_catalog_thin()`
- Hybrid Search: BM25 + Lexical + RRF
- Gibt Katalog-Vorschläge zurück, die in Chat-Antwort eingefügt werden

**Zweck**:
- Schnelle Produktvorschläge während des Chats
- Tippfehlerkorrektur
- Synonym-Erkennung
- Deterministisch (keine LLM-Calls für Suche)

#### **Option B: Ohne Retriever (Standard)**
**Aktivierung**: `LLM1_THIN_RETRIEVAL=0` (default)

**Code-Stelle**: `quote_service.py`, Zeile 3024
```python
result = ctx.chain1.run(human_input=message)
# → Nur LLM + Memory, kein Retriever
```

**Zweck**:
- Schnellerer Chat (keine zusätzliche Suche)
- LLM1 arbeitet nur mit Memory/Context
- Katalog-Vorschläge werden nicht angezeigt

---

## LLM2 (Angebotsgenerierung)

### Chain-Struktur
```python
# llm.py, Zeile 289
chain2 = ConversationalRetrievalChain.from_llm(
    llm=llm2,
    retriever=retriever,  # ← Vector Retriever integriert
    combine_docs_chain_kwargs={"prompt": prompt2},
)
# → Vector Retriever ist direkt in Chain2 integriert
```

### Retriever-Verwendung

#### **Vector Index (index_manager) - IMMER aktiv**

**WICHTIG**: LLM2 nutzt **NUR Vector Search**, NICHT den kombinierten Ablauf (BM25 + Lexical + Vector + RRF)!

**Code-Stellen**:

1. **Context-Erweiterung** (`quote_service.py`, Zeile 3419-3429)
```python
def find_exact_catalog_lines(terms: list[str], skus: list[str]) -> list[str]:
    if ctx.retriever is not None:
        for t in terms:
            hits = ctx.retriever.get_relevant_documents(t)[:8]
            # → NUR Vector Search (kein BM25, kein Lexical, kein RRF)
            # → Erweitert Context für LLM2 Prompt
```

2. **Business-Scoring** (`quote_service.py`, Zeile 3517-3525, 3530-3549)
```python
if ctx.retriever is not None:
    rerank = _run_rank_main(
        normalized_names[0],
        ctx.retriever,  # ← Vector Retriever
        top_k=1,
        business_cfg=business_cfg,
    )
    # → rank_main() nutzt Vector Search + zusätzliches Lexical Scoring
    # → ABER: Kein BM25, kein RRF
```

**Was `rank_main()` macht** (`retriever/main.py`, Zeile 182-190):
```python
docs = retriever.get_relevant_documents(query)  # ← Vector Search
# Dann: Lexical Scoring auf Vector-Ergebnissen
# ABER: Kein BM25, kein RRF
```

**Zweck**:
- Semantische Suche für Produktkontext
- Context-Erweiterung für LLM2 Prompt
- Business-Scoring (Margen, Verfügbarkeit)
- Multi-Tenant Support (company-scoped)

**Technologie**:
- DocArray Vector Index
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Cosine Similarity
- **KEIN BM25**
- **KEIN RRF**
- **Nur Vector Search + Lexical Post-Processing**

---

## Vergleich: LLM1 vs LLM2

| Aspekt | LLM1 | LLM2 |
|--------|------|------|
| **Retriever-Typ** | Hybrid Search (optional) | Vector Index (immer) |
| **Aktivierung** | `LLM1_THIN_RETRIEVAL=1` | Automatisch (wenn `retriever` vorhanden) |
| **Zweck** | Katalog-Vorschläge | Context-Erweiterung |
| **Geschwindigkeit** | Sehr schnell (deterministisch) | Langsamer (Embedding-Generierung) |
| **Integration** | Extern (wird in Antwort eingefügt) | Integriert in Chain |
| **Use-Case** | Chat-Interaktion | Angebotsgenerierung |
| **BM25 + Lexical + Vector + RRF** | ✅ Ja (wenn aktiviert) | ❌ Nein (nur Vector Search) |

---

## Kombination beider Retriever

### Für LLM1
**Aktuell**: Hybrid Search (BM25 + Lexical + RRF) wenn `LLM1_THIN_RETRIEVAL=1`
- ✅ Nutzt vollständigen Ablauf: BM25 + Lexical + RRF
- ⚠️ Vector Search wird NICHT kombiniert (nur BM25 + Lexical)

**Möglichkeit**: Beide kombinieren
- Hybrid Search für Vorschläge (schnell)
- Vector Search für Context-Erweiterung (semantisch)
- **Nicht implementiert** (Chain1 hat keinen Retriever)

### Für LLM2
**Aktuell**: Nur Vector Index (kein BM25, kein RRF)
- ❌ Nutzt NUR Vector Search
- ❌ Kein BM25
- ❌ Kein RRF
- ✅ Zusätzliches Lexical Post-Processing in `rank_main()`

**Möglichkeit**: Beide kombinieren
- Hybrid Search für exakte Matches
- Vector Search für semantische Suche
- **Bereits möglich** via `COMBINE_HYBRID_VECTOR=1` in `search_catalog()`
- **Aber**: Wird aktuell **NICHT** in `generate_offer_positions()` genutzt
- **Würde erfordern**: `find_exact_catalog_lines()` müsste `hybrid_search()` statt `retriever.get_relevant_documents()` nutzen

---

## Code-Referenzen

### LLM1 - Thin Search
- **Aktivierung**: `main.py`, Zeile 87: `LLM1_THIN_RETRIEVAL`
- **Verwendung**: `quote_service.py`, Zeile 3106: `if ctx.llm1_thin_retrieval`
- **Funktion**: `quote_service.py`, Zeile 1717: `_build_catalog_candidates()`
- **Search**: `quote_service.py`, Zeile 1738: `_run_thin_catalog_search()`

### LLM2 - Vector Index
- **Chain**: `llm.py`, Zeile 289: `ConversationalRetrievalChain`
- **Context**: `quote_service.py`, Zeile 3419: `find_exact_catalog_lines()`
- **Scoring**: `quote_service.py`, Zeile 3532: `_run_rank_main()`

---

## Empfehlungen

### Für LLM1
- **Standard**: `LLM1_THIN_RETRIEVAL=0` (schneller Chat)
- **Mit Vorschlägen**: `LLM1_THIN_RETRIEVAL=1` (bessere UX)

### Für LLM2
- **Immer**: Vector Index aktivieren (bessere Angebotsqualität)
- **Optional**: `COMBINE_HYBRID_VECTOR=1` für beste Ergebnisse (aber langsamer)

---

**Stand**: 2025-01-27  
**Version**: 1.0

