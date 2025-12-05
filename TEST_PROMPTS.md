# Test-Prompts für Retriever-Testing

## 🧪 Test 1: Einfach (2 Produkte)

```
Ich brauche ein Angebot für 50m² Wand streichen. 
Benötige Dispersionsfarbe weiß und Tiefengrund.
```

**Erwartete Produkte**:
- Dispersionsfarbe weiß
- Tiefengrund

**Test-Zweck**:
- Exakte Matches
- Standard-Produkte ohne Synonyme
- Schnelle Verarbeitung

---

## 🧪 Test 2: Mix aus Synonymen und direkten Treffern (3 Produkte)

```
Für ein Innenanstrich-Projekt benötige ich:
- Dispersionsfarbe weiß (direkter Treffer)
- Malerkrepp (synonym → sollte Abklebeband finden)
- Acryllack hochglänzend (neues/unbekanntes Produkt → sollte ähnliche Lacke finden oder "kein Treffer")
```

**Erwartete Produkte**:
- Dispersionsfarbe weiß → sollte "Dispersionsfarbe weiß" finden (direkter Match/BM25)
- Malerkrepp → sollte "Abklebeband" finden (Synonym/Lexical - ist in synonyms.yaml definiert)
- Acryllack hochglänzend → sollte ähnliche Lack-Produkte finden (semantisch/Vector) oder "kein Treffer" melden

**Test-Zweck**:
- Mix aus direkten Treffern, Synonymen und unbekannten Produkten
- Testet alle Retriever-Methoden gleichzeitig
- BM25 (direkt) + Lexical (Synonym) + Vector (semantisch für unbekanntes Produkt)
- Testet Fallback-Verhalten bei unbekannten Produkten

---

## 🧪 Test 3: Mit Tippfehlern (Bonus)

```
Ich brauche Disperionsfarbe weiss und Tieffgrund für 30m².
```

**Erwartete Produkte**:
- Disperionsfarbe weiss → sollte "Dispersionsfarbe weiß" finden (Tippfehler)
- Tieffgrund → sollte "Tiefengrund" finden (Tippfehler)

**Test-Zweck**:
- Tippfehlerkorrektur
- Fuzzy-Matching
- Lexical Search

---

## 📋 Test-Plan

### 1. Test mit LLM1 Chat
```bash
POST /api/chat
{
  "message": "<Test-Prompt hier>"
}
```

**Erwartetes Ergebnis**:
- Katalog-Vorschläge werden angezeigt (wenn `LLM1_THIN_RETRIEVAL=1`)
- Format: `- <Query> → <Gefundenes Produkt>`
- Bei Synonymen: Sollte korrekte Zuordnung zeigen

### 2. Test mit API Search
```bash
GET /api/catalog/search?q=<Produktname>
```

**Erwartetes Ergebnis**:
- Top-K Ergebnisse mit Scores
- Bei Synonymen: Sollte beide Varianten finden
- Bei Tippfehlern: Sollte korrigierte Version finden

### 3. Test mit LLM2 Angebot
```bash
POST /api/offer
{
  "message": "<Test-Prompt hier>",
  "products": ["<Produkt1>", "<Produkt2>"]
}
```

**Erwartetes Ergebnis**:
- Angebotspositionen werden generiert
- Produkte werden korrekt zugeordnet
- Preise werden aus Katalog übernommen

---

## 🔍 Was testen?

### Hybrid Search (BM25 + Lexical)
- ✅ Exakte Matches finden
- ✅ Tippfehler korrigieren
- ✅ Synonyme erkennen

### Vector Search (wenn kombiniert)
- ✅ Semantische Ähnlichkeit ("Außenfarbe" = "Fassadenfarbe")
- ✅ Kontext-Verständnis

### RRF (Reciprocal Rank Fusion)
- ✅ Beste Ergebnisse aus allen Methoden kombinieren
- ✅ Ranking-Qualität

---

## 📊 Erwartete Ergebnisse

### Test 1 (Einfach)
```
✅ Dispersionsfarbe weiß → Dispersionsfarbe weiß (exakter Match)
✅ Tiefengrund → Tiefengrund (exakter Match)
```

### Test 2 (Mix: Synonyme + Direkte Treffer + Unbekanntes Produkt)
```
✅ Dispersionsfarbe weiß → Dispersionsfarbe weiß (direkter Match/BM25)
✅ Malerkrepp → Abklebeband (Synonym/Lexical - aus synonyms.yaml)
⚠️ Acryllack hochglänzend → Ähnliche Lack-Produkte (semantisch/Vector) oder "kein Treffer"
```

### Test 3 (Tippfehler)
```
✅ Disperionsfarbe weiss → Dispersionsfarbe weiß (Fuzzy-Match)
✅ Tieffgrund → Tiefengrund (Fuzzy-Match)
```

---

## 🚀 Test ausführen

### 1. Backend starten
```bash
cd backend
python main.py
```

### 2. Test-Prompts senden
```bash
# Test 1
curl -X POST http://localhost:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Ich brauche ein Angebot für 50m² Wand streichen. Benötige Dispersionsfarbe weiß und Tiefengrund."}'

# Test 2
curl -X POST http://localhost:7860/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Für ein Fassadenprojekt benötige ich: Außenfarbe, Grundierung und Malerkrepp."}'
```

### 3. Ergebnisse prüfen
- Katalog-Vorschläge in Antwort?
- Korrekte Produktzuordnung?
- Synonyme erkannt?
- Tippfehler korrigiert?

---

**Stand**: 2025-01-27

