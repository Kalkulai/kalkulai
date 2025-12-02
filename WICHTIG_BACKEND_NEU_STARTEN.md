# ⚠️ WICHTIG: Backend MUSS neu gestartet werden!

## Problem
Die Test-Produkte werden immer noch angezeigt, weil:
1. Der Katalog wird **beim Startup** geladen
2. Die Pre-Filter greifen nur beim **Neuladen**
3. Das laufende Backend hat noch die alte Version im Speicher

## ✅ Lösung: Backend NEU STARTEN

### Schritt 1: Backend stoppen
```bash
# Im Terminal wo das Backend läuft:
# Drücke Ctrl+C
```

### Schritt 2: Backend starten
```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend
source venv/bin/activate
uvicorn main:app --reload --port 7860
```

### Schritt 3: Prüfe die Log-Meldung
**Du MUSST diese Meldung sehen:**
```
INFO:kalkulai:📦 Catalog loaded from database: 44 active products (test products excluded)
```

**Wichtige Zahlen:**
- **Vorher:** 51 active products
- **Jetzt:** ~44 active products (7 Test-Produkte ausgeschlossen)

**Wenn du stattdessen siehst:**
```
INFO:kalkulai:📦 Catalog loaded from database: 51 active products
```
→ Dann hat das Backend den neuen Code noch nicht geladen!

### Schritt 4: Frontend neu laden
```bash
# Im Browser:
Cmd+Shift+R (Mac) oder Ctrl+Shift+R (Windows)
```

### Schritt 5: Test-Prompt
```
Ich brauche 20 Liter weiße Dispersionsfarbe für Innenwände.
```

**Erwartetes Ergebnis:**
```
✅ Latexfarbe weiß 10L (sku_latex_10)
   2 Stück × 29.99 € = 59.98 €

❌ NICHT MEHR: Testfarbe Weiß 10L (test-001)
```

## Was wurde gefixt:

### 1. Katalog-Loading (main.py)
```python
# Pre-Filter beim Laden:
- Exclude SKUs: test-, test_, demo-, demo_
- Exclude names: test, demo, beispiel, sample
- Result: 44 statt 51 Produkte
```

### 2. Search-Filtering (thin.py)
```python
# Zusätzliche Filter bei der Suche:
- Exact-Match Bonus: +0.25
- Price-Available Bonus: +0.03
- Category Detection & Filtering
```

## Verifikation:

### Test 1: API-Endpunkt
```bash
curl 'http://localhost:7860/api/catalog/search?q=dispersionsfarbe&limit=5&company_id=demo'
```

**Erwartete Antwort:**
- KEINE Produkte mit `"sku": "test-001"`
- Nur Produkte wie: `sku_latex_10`, `sku_mineralfarbe_10`, etc.

### Test 2: LLM-Antwort
```
Query: "20 Liter weiße Dispersionsfarbe"
Result: Latexfarbe weiß 10L ✅
```

## Troubleshooting:

### Problem: Backend zeigt immer noch 51 Produkte
**Lösung:** 
1. Stelle sicher, dass du `main.py` gespeichert hast
2. Stoppe Backend vollständig (Ctrl+C)
3. Warte 2 Sekunden
4. Starte neu

### Problem: "test-001" ist immer noch in Ergebnissen
**Lösung:**
1. Prüfe Backend-Logs auf "44 active products"
2. Wenn nicht: Backend wurde nicht neu gestartet
3. Prüfe dass Port 7860 richtig ist

### Problem: Mengen-Berechnung falsch
**Lösung:**
1. Frontend neu laden (Cmd+Shift+R)
2. Chat-Historie löschen (Neue Session)
3. Prompt nochmal eingeben

