# 🔧 Environment Setup - WICHTIG!

## Problem: Frontend zeigt "0 Produkte"

**Ursache:** Die Admin API Key Environment-Variablen fehlen!

## ✅ Lösung: Environment-Dateien erstellen

### Schritt 1: Backend `.env` erstellen

```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend
cp .env.example .env
```

Die Datei sollte enthalten:
```env
ADMIN_API_KEY=dev-admin-key-12345
KALKULAI_DB_URL=sqlite:///backend/var/kalkulai.db

# Optional: Login für Entwicklung deaktivieren
DISABLE_AUTH=true
```

**💡 Tipp für Entwicklung:** Mit `DISABLE_AUTH=true` kannst du den Login überspringen und musst dich nicht immer wieder anmelden. Für Produktion sollte dies auf `false` stehen!

### Schritt 2: Frontend `.env` erstellen

```bash
cd /Users/felixmagiera/Desktop/kalkulai/frontend
cp .env.example .env
```

Die Datei sollte enthalten:
```env
VITE_API_BASE=http://localhost:8000
VITE_ADMIN_API_KEY=dev-admin-key-12345
```

**WICHTIG:** Die `ADMIN_API_KEY` (Backend) und `VITE_ADMIN_API_KEY` (Frontend) **MÜSSEN identisch sein**!

### Schritt 3: Backend neu starten

```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend
source venv/bin/activate  # oder: source ../venv/bin/activate
uvicorn main:app --reload --port 8000
```

### Schritt 4: Frontend neu starten

```bash
cd /Users/felixmagiera/Desktop/kalkulai/frontend
npm run dev
```

**WICHTIG:** Nach dem Erstellen der `.env` Dateien MUSS das Frontend neu gestartet werden, damit die Variablen geladen werden!

## 🧪 Testen

1. Öffne: http://localhost:5173
2. Gehe zu: **Einstellungen > Datenbank**
3. Du solltest jetzt sehen: **"Gesamt: 58 Produkte, Aktiv: 51, Inaktiv: 7"**

## 🔍 Troubleshooting

### Problem: Immer noch "0 Produkte"

**Checkliste:**
- [ ] `.env` Dateien existieren in `backend/` und `frontend/`
- [ ] `ADMIN_API_KEY` ist in beiden Dateien identisch
- [ ] Backend wurde neu gestartet
- [ ] Frontend wurde neu gestartet (wichtig für Vite!)
- [ ] Browser-Cache geleert (Strg+Shift+R / Cmd+Shift+R)

### Problem: "Admin-Zugriff erforderlich" Meldung

Das bedeutet, dass `VITE_ADMIN_API_KEY` im Frontend nicht gesetzt ist.

**Lösung:**
1. Prüfe, ob `frontend/.env` existiert
2. Prüfe, ob `VITE_ADMIN_API_KEY=dev-admin-key-12345` drin steht
3. Frontend neu starten: `npm run dev`

### Problem: "HTTP 401 - Unauthorized"

Das bedeutet, dass die API Keys nicht übereinstimmen.

**Lösung:**
1. Vergleiche `backend/.env` → `ADMIN_API_KEY`
2. Vergleiche `frontend/.env` → `VITE_ADMIN_API_KEY`
3. Beide müssen identisch sein!
4. Beide Server neu starten

### Datenbank prüfen

```bash
cd /Users/felixmagiera/Desktop/kalkulai
sqlite3 backend/var/kalkulai.db "SELECT COUNT(*) FROM products WHERE company_id='demo' AND is_active=1;"
# Sollte zeigen: 51
```

## 📝 Für Produktion

Für Produktion solltest du einen sicheren API Key generieren:

```bash
# Generiere einen sicheren 32-Byte Hex-Key
openssl rand -hex 32
```

Dann ersetze `dev-admin-key-12345` in beiden `.env` Dateien mit dem generierten Key.

## 🎯 Nächste Schritte

Nach dem Setup kannst du:
1. ✅ Produkte im Frontend sehen
2. ✅ Neue Produkte hinzufügen
3. ✅ Produkte bearbeiten/löschen
4. ✅ CSV importieren/exportieren
5. ✅ Synonyme verwalten

Alle Änderungen werden sofort in der Datenbank gespeichert!

