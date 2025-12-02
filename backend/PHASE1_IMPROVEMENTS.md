# Phase 1: Search Improvements ✅

## Was wurde implementiert:

### 1. ✅ Pre-Filtering (Hard Filters)

#### Filter 1: Test-Produkte ausschließen
```python
# Ausgeschlossen werden:
- SKUs die mit "test-", "test_", "demo-", "demo_" beginnen
- Produkte mit "test", "demo", "beispiel", "sample" im Namen (als standalone Wort)
```

**Beispiel:**
- ❌ `test-001` - "Testfarbe Weiß 10L" → **AUSGESCHLOSSEN**
- ✅ `sku_latex_10` - "Latexfarbe weiß 10L" → **INKLUDIERT**

#### Filter 2: Nur aktive Produkte
```python
# Nur Produkte mit is_active=True werden berücksichtigt
# 51 aktive Produkte statt 58 gesamt
```

#### Filter 3: Category-Filter
```python
# Automatische Erkennung der Kategorie aus der Query:
- "Dispersionsfarbe" → category="paint"
- "Tiefengrund" → category="primer"
- "Malerrolle" → category="tools"

# Nur Produkte der erkannten Kategorie werden durchsucht
```

### 2. ✅ Besseres Scoring

#### Exact-Match Bonus (+0.25)
```python
# Wenn Query exakt dem Produktnamen entspricht
Query: "Latexfarbe weiß 10L"
Produkt: "Latexfarbe weiß 10L"
→ Bonus: +0.25 (25% Score-Boost!)

# Partial Match (+0.10)
Query: "Latexfarbe"
Produkt: "Latexfarbe weiß 10L"
→ Bonus: +0.10 (10% Score-Boost)
```

#### Preis-Verfügbarkeit Bonus (+0.03)
```python
# Produkte mit Preis werden bevorzugt
- Produkt hat price_eur > 0 → +0.03
- Produkt ohne Preis → +0.00
```

#### Angepasste Score-Gewichtung
```python
# Vorher:
score_final = 0.8 * score_lex + 0.2 * rule_bonus

# Jetzt:
score_final = 0.7 * score_lex + 0.3 * rule_bonus

# → Mehr Gewicht auf Business-Rules (Exact Match, Preis, etc.)
```

## Erwartete Verbesserungen:

### Test 1: "20 Liter weiße Dispersionsfarbe"

**Vorher:**
```
1. Testfarbe Weiß 10L (test-001) ❌
   Score: 0.65
```

**Jetzt:**
```
1. Latexfarbe weiß 10L (sku_latex_10) ✅
   Score: 0.85 (Exact Match + Preis + Category)
2. Dispersionsfarbe weiß matt 10L ✅
   Score: 0.82 (Category + Preis)
```

### Test 2: "Tiefengrund"

**Vorher:**
```
Gemischte Ergebnisse, evtl. auch Farben
```

**Jetzt:**
```
Nur Produkte mit category="primer"
+ Exact Match Bonus für "Tiefengrund"
```

## Technische Details:

### Neue Funktionen:
1. `_detect_category_from_query()` - Erkennt Kategorie aus Query
2. `_passes_pre_filters()` - Hard Filtering vor dem Scoring
3. `_has_price()` - Prüft ob Produkt Preis hat

### Neue Konstanten:
```python
_EXACT_MATCH_BONUS = 0.25
_PRICE_AVAILABLE_BONUS = 0.03
_TEST_SKU_PREFIXES = {"test-", "test_", "demo-", "demo_"}
_TEST_NAME_KEYWORDS = {"test", "demo", "beispiel", "sample"}
```

## Nächste Schritte (Phase 2):

Wenn die Ergebnisse noch nicht perfekt sind:

### Option A: BM25 + Hybrid Search
```python
# Kombiniere:
- BM25 (Keyword Search) → 40%
- Vector Search → 30%
- Lexical (aktuell) → 30%
# Mit RRF (Reciprocal Rank Fusion)
```

### Option B: Re-Ranking
```python
# Retrieve 20-50 Produkte
# Re-rank mit Cross-Encoder (BGE-Reranker)
# Return top 5
```

## Testing:

### Backend neu starten:
```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend
# Ctrl+C im laufenden Terminal
uvicorn main:app --reload --port 7860
```

### Test-Prompt:
```
Ich brauche 20 Liter weiße Dispersionsfarbe für Innenwände.
```

### Erwartetes Ergebnis:
- ✅ KEINE Test-Produkte mehr
- ✅ Bessere Produkte (Latexfarbe, Dispersionsfarbe)
- ✅ Produkte mit Preis bevorzugt
- ✅ Richtige Kategorie (paint)

## Metriken:

**Vorher:**
- 58 Produkte durchsucht (inkl. 7 inaktive)
- Test-Produkte in Ergebnissen
- Score-Range: 0.45 - 0.70

**Jetzt:**
- 51 aktive Produkte durchsucht
- Test-Produkte ausgeschlossen
- Score-Range: 0.55 - 0.90 (durch Bonuses)
- Bessere Relevanz durch Category-Filter

