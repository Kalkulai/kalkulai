# Fix: Frontend zeigt "0 Produkte"

## Problem
Das Frontend zeigt "Gesamt: 0 Produkte, Aktiv: 0, Inaktiv: 0" obwohl die Datenbank 58 Produkte enthält.

## Ursache
Das Frontend lädt keine Daten, weil:
1. Der Backend-Server muss laufen
2. Das Frontend muss nach Code-Änderungen neu geladen werden
3. Die Admin API Keys müssen übereinstimmen (✅ bereits korrekt konfiguriert)

## Lösung

### Schritt 1: Backend-Server starten

```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend

# Aktiviere Virtual Environment
source venv/bin/activate

# Starte den Server
uvicorn main:app --reload --port 8000
```

Der Server sollte starten und ausgeben:
```
✅ Startup
   MODEL_PROVIDER=openai  LLM1=gpt-4o-mini  LLM2=gpt-4o-mini  VAT_RATE=0.19
   Produktdatei: OK
   CHROMA_DIR=...  (writable)
   OUTPUT_DIR=...  (writable)
   ALLOWED_ORIGINS=[...]
📦 Catalog loaded from database: 51 active products
```

**Wichtig:** Du solltest jetzt die Meldung sehen:
- `📦 Catalog loaded from database: 51 active products`
- **NICHT:** `📦 Catalog cache refreshed: 151 products loaded` (das wäre falsch!)

### Schritt 2: Frontend neu laden

Öffne deinen Browser und:
1. Gehe zu: http://localhost:5173
2. Drücke **Cmd+Shift+R** (Mac) oder **Ctrl+Shift+R** (Windows) für Hard Reload
3. Öffne die Browser-Konsole (F12)
4. Prüfe auf Fehler

### Schritt 3: Produktverwaltung öffnen

1. Klicke auf **Einstellungen** (⚙️)
2. Klicke auf **Datenbank**
3. Du solltest jetzt sehen:
   ```
   Gesamt: 58 Produkte
   Aktiv: 51
   Inaktiv: 7
   ```

## Verifikation

### Test 1: Produkte werden geladen
```bash
# Prüfe, ob die API funktioniert
curl -H "X-Admin-Key: kalkulai26!" \
  "http://localhost:8000/api/admin/products?company_id=demo&include_deleted=true&limit=100"
```

Erwartete Ausgabe: JSON-Array mit 58 Produkten

### Test 2: Katalog-Cache ist korrekt
```bash
# Prüfe die Logs beim Backend-Start
# Du solltest sehen:
# 📦 Catalog loaded from database: 51 active products
```

### Test 3: Frontend lädt Daten
1. Öffne Browser-Konsole (F12)
2. Gehe zu Network-Tab
3. Lade die Produktverwaltung
4. Du solltest einen Request sehen:
   ```
   GET /api/admin/products?company_id=demo&include_deleted=1&limit=500
   Status: 200
   Response: [... 58 Produkte ...]
   ```

## Häufige Probleme

### Problem: "Keine Produkte gefunden" im Frontend
**Lösung:**
- Backend-Server läuft nicht → Starte den Server (siehe Schritt 1)
- CORS-Fehler → Prüfe Browser-Konsole auf Fehler
- API-Key falsch → Beide müssen `kalkulai26!` sein (✅ bereits korrekt)

### Problem: Backend zeigt "151 products loaded"
**Lösung:**
- Die Code-Änderung wurde nicht übernommen
- Starte den Backend-Server neu
- Prüfe, dass `main.py` die neue Version hat (ohne statische Datei)

### Problem: Port 8000 bereits belegt
**Lösung:**
```bash
# Finde den Prozess
lsof -i :8000

# Beende den Prozess
kill -9 <PID>

# Oder verwende einen anderen Port
uvicorn main:app --reload --port 8001

# Dann im Frontend .env ändern:
# VITE_API_BASE=http://localhost:8001
```

## Nach dem Fix

Wenn alles funktioniert, solltest du:
1. ✅ 58 Produkte in der Produktverwaltung sehen
2. ✅ Neue Produkte hinzufügen können
3. ✅ Excel-Export mit 58 Produkten (nicht 151!)
4. ✅ CSV-Import funktioniert
5. ✅ Alle Änderungen werden sofort in der DB gespeichert

## Konfiguration (bereits korrekt)

### Frontend: `/Users/felixmagiera/Desktop/kalkulai/frontend/.env`
```env
VITE_API_BASE=http://localhost:8000
VITE_ADMIN_API_KEY=kalkulai26!
```

### Backend: `/Users/felixmagiera/Desktop/kalkulai/backend/.env`
```env
ADMIN_API_KEY=kalkulai26!
```

✅ Die Keys stimmen überein!

## Zusammenfassung

**Was gefixt wurde:**
1. ✅ Katalog lädt nur noch aus DB (nicht mehr statische Datei)
2. ✅ Doppelte Datenbank gelöscht
3. ✅ Admin API Keys sind korrekt konfiguriert

**Was du tun musst:**
1. Backend-Server starten (siehe Schritt 1)
2. Frontend im Browser neu laden (Cmd+Shift+R)
3. Produktverwaltung öffnen → sollte 58 Produkte zeigen

