# Performance-Empfehlungen: Retriever-Konfiguration

## 📊 Performance-Vergleich

| Methode | Latenz | Qualität | Ressourcen | Beste für |
|---------|--------|----------|------------|-----------|
| **Nur Hybrid (BM25+Lexical+RRF)** | ~20ms | ⭐⭐⭐⭐ | Niedrig | Schnelle Suchen, Tippfehler |
| **Nur Vector Search** | ~50-100ms | ⭐⭐⭐⭐ | Mittel | Semantische Suche |
| **Hybrid + Vector + RRF** | ~70-120ms | ⭐⭐⭐⭐⭐ | Hoch | Beste Qualität |
| **Kein Retriever** | ~0ms | ⭐⭐ | Sehr niedrig | Schnellster Chat |

*Latenz-Werte basieren auf typischen Kataloggrößen (100-1000 Produkte)*

---

## 🎯 Empfehlungen nach Use-Case

### 1. **LLM1 Chat (Interaktive Konversation)**

**Priorität**: Geschwindigkeit > Qualität

#### **Option A: Schnellste Performance** ⚡
```bash
LLM1_THIN_RETRIEVAL=0
```
- **Latenz**: ~0ms (kein Retriever)
- **Qualität**: ⭐⭐ (nur LLM + Memory)
- **Use-Case**: Schnelle Chat-Antworten, keine Produktvorschläge nötig
- **Vorteil**: Sehr schnell, niedrige Kosten

#### **Option B: Beste Balance** ⚖️ (EMPFOHLEN)
```bash
LLM1_THIN_RETRIEVAL=1
```
- **Latenz**: ~20ms (Hybrid Search)
- **Qualität**: ⭐⭐⭐⭐ (BM25 + Lexical + RRF)
- **Use-Case**: Chat mit Produktvorschlägen
- **Vorteil**: Schnell + gute Qualität, deterministisch

#### **Option C: Maximale Qualität** 🎯
```bash
LLM1_THIN_RETRIEVAL=1
COMBINE_HYBRID_VECTOR=1  # Falls in LLM1 integriert
```
- **Latenz**: ~70-120ms (Hybrid + Vector)
- **Qualität**: ⭐⭐⭐⭐⭐
- **Use-Case**: Wenn Qualität wichtiger als Geschwindigkeit
- **Nachteil**: Deutlich langsamer

**🏆 Empfehlung für LLM1**: **Option B** (`LLM1_THIN_RETRIEVAL=1`)
- Beste Balance zwischen Geschwindigkeit und Qualität
- 20ms ist für Chat-Interaktionen akzeptabel
- Gute Tippfehlerkorrektur und Synonym-Erkennung

---

### 2. **LLM2 Angebotsgenerierung**

**Priorität**: Qualität > Geschwindigkeit

#### **Aktuell**: Nur Vector Search
```python
# quote_service.py, Zeile 3424
hits = ctx.retriever.get_relevant_documents(t)[:8]
```
- **Latenz**: ~50-100ms
- **Qualität**: ⭐⭐⭐⭐ (nur semantisch)
- **Problem**: Verpasst exakte Matches, keine Tippfehlerkorrektur

#### **Option A: Hybrid + Vector kombiniert** 🎯 (EMPFOHLEN)
```bash
COMBINE_HYBRID_VECTOR=1
```
- **Latenz**: ~70-120ms
- **Qualität**: ⭐⭐⭐⭐⭐ (BM25 + Lexical + Vector + RRF)
- **Vorteil**: 
  - Deckt alle Fälle ab (exakt, fuzzy, semantisch)
  - Beste Recall-Rate
  - Bessere Angebotsqualität
- **Nachteil**: ~20-50ms langsamer

**🏆 Empfehlung für LLM2**: **Hybrid + Vector kombiniert**
- Qualität ist wichtiger als Geschwindigkeit bei Angebotsgenerierung
- 70-120ms ist akzeptabel (nicht interaktiv)
- Deutlich bessere Ergebnisse durch Kombination

---

### 3. **API `/api/catalog/search`**

**Priorität**: Balance zwischen Geschwindigkeit und Qualität

#### **Option A: Schnell** ⚡
```bash
COMBINE_HYBRID_VECTOR=0  # Default
```
- **Latenz**: ~20ms (nur Hybrid Search)
- **Qualität**: ⭐⭐⭐⭐
- **Use-Case**: Schnelle API-Antworten, typische Suchen

#### **Option B: Beste Qualität** 🎯 (EMPFOHLEN)
```bash
COMBINE_HYBRID_VECTOR=1
```
- **Latenz**: ~70-120ms
- **Qualität**: ⭐⭐⭐⭐⭐
- **Use-Case**: Wenn API-Qualität wichtig ist
- **Vorteil**: Deckt alle Suchszenarien ab

**🏆 Empfehlung für API**: **Option B** (`COMBINE_HYBRID_VECTOR=1`)
- API-Calls sind nicht interaktiv (kein User wartet direkt)
- Bessere Qualität rechtfertigt zusätzliche Latenz
- Kann bei Bedarf per Request-Parameter deaktiviert werden

---

## 📈 Performance-Optimierungen

### 1. **Caching**
- **Hybrid Search**: Cache-TTL 60s (bereits implementiert)
- **Vector Search**: Index-Cache pro Company (bereits implementiert)
- **Empfehlung**: Cache-TTL beibehalten

### 2. **Pre-Filtering**
- Test-Produkte werden früh ausgefiltert ✅
- Inactive Products werden ignoriert ✅
- **Empfehlung**: Beibehalten (reduziert Suchraum)

### 3. **Parallelisierung**
- BM25 + Lexical können parallel laufen
- Vector Search kann parallel zu BM25/Lexical laufen
- **Aktuell**: Sequenziell implementiert
- **Potenzial**: ~30-40% Geschwindigkeitsgewinn möglich

### 4. **Index-Größe**
- BM25 Index: In-Memory (sehr schnell)
- Vector Index: In-Memory (DocArray)
- **Empfehlung**: Bei >10.000 Produkten → Externe Vector-DB (Pinecone, Weaviate)

---

## 🎯 Finale Empfehlungen

### **Produktions-Setup** (Beste Balance)

```bash
# LLM1: Schnell mit guten Vorschlägen
LLM1_THIN_RETRIEVAL=1

# LLM2: Beste Qualität (wichtig für Angebote)
COMBINE_HYBRID_VECTOR=1

# API: Beste Qualität
COMBINE_HYBRID_VECTOR=1
```

**Erwartete Performance**:
- **LLM1 Chat**: ~20ms (Hybrid Search)
- **LLM2 Angebot**: ~70-120ms (Hybrid + Vector)
- **API Search**: ~70-120ms (Hybrid + Vector)

### **Performance-kritisches Setup** (Schnellste Option)

```bash
# LLM1: Kein Retriever (schnellster Chat)
LLM1_THIN_RETRIEVAL=0

# LLM2: Nur Vector (schneller als kombiniert)
COMBINE_HYBRID_VECTOR=0

# API: Nur Hybrid (schnell)
COMBINE_HYBRID_VECTOR=0
```

**Erwartete Performance**:
- **LLM1 Chat**: ~0ms (kein Retriever)
- **LLM2 Angebot**: ~50-100ms (nur Vector)
- **API Search**: ~20ms (nur Hybrid)

### **Qualitäts-Setup** (Beste Ergebnisse)

```bash
# LLM1: Hybrid mit Vorschlägen
LLM1_THIN_RETRIEVAL=1

# LLM2: Hybrid + Vector kombiniert
COMBINE_HYBRID_VECTOR=1

# API: Hybrid + Vector kombiniert
COMBINE_HYBRID_VECTOR=1
```

**Erwartete Performance**:
- **LLM1 Chat**: ~20ms (Hybrid Search)
- **LLM2 Angebot**: ~70-120ms (Hybrid + Vector)
- **API Search**: ~70-120ms (Hybrid + Vector)

---

## 🔍 Performance-Metriken messen

### Benchmark-Query-Beispiele:
```python
# Exakter Match
"Dispersionsfarbe weiß"

# Tippfehler
"Disperionsfarbe weiss"

# Semantisch ähnlich
"Außenfarbe für Fassade"

# Synonym
"Tiefengrund" vs "Tiefgrund"
```

### Erwartete Ergebnisse:
- **Hybrid Search**: Gut bei exakten Matches + Tippfehlern
- **Vector Search**: Gut bei semantischer Ähnlichkeit
- **Kombiniert**: Gut bei allen Szenarien

---

## 💡 Zusammenfassung

**Beste Performance = Beste Balance**:

1. **LLM1**: `LLM1_THIN_RETRIEVAL=1` (Hybrid Search)
   - Schnell genug (~20ms)
   - Gute Qualität
   - Deterministisch

2. **LLM2**: `COMBINE_HYBRID_VECTOR=1` (Hybrid + Vector)
   - Beste Qualität für Angebote
   - Latenz akzeptabel (~70-120ms)
   - Deckt alle Fälle ab

3. **API**: `COMBINE_HYBRID_VECTOR=1` (Hybrid + Vector)
   - Beste Qualität
   - Nicht interaktiv (Latenz weniger kritisch)

**Warum diese Kombination?**
- ✅ LLM1: Geschwindigkeit wichtig → Hybrid Search reicht
- ✅ LLM2: Qualität wichtig → Kombiniert für beste Ergebnisse
- ✅ API: Qualität wichtig → Kombiniert für beste Ergebnisse

**Trade-off**: 
- ~50-100ms zusätzliche Latenz bei LLM2/API
- Deutlich bessere Qualität rechtfertigt dies

---

**Stand**: 2025-01-27  
**Version**: 1.0


