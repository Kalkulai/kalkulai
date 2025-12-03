# 🔓 Login für Entwicklung deaktivieren

## Problem
Du musst dich bei jeder Entwicklungssession immer wieder neu einloggen, was lästig ist.

## ✅ Lösung: Auth für Dev deaktivieren

### Schritt 1: .env Datei bearbeiten

Öffne die Datei `/Users/felixmagiera/Desktop/kalkulai/backend/.env` und füge diese Zeile hinzu:

```env
DISABLE_AUTH=true
```

Alternativ kannst du den Wert auch auf `1` oder `yes` setzen:

```env
DISABLE_AUTH=1
```

### Schritt 2: Backend neu starten

```bash
cd /Users/felixmagiera/Desktop/kalkulai/backend
# Stoppe das laufende Backend (Strg+C)
# Starte es neu:
uvicorn main:app --reload --port 8000
```

### Schritt 3: Fertig! 🎉

Jetzt wird automatisch ein Dev-User verwendet:
- **Email:** `dev@kalkulai.local`
- **Name:** `Dev User`
- **ID:** `1`

Du musst dich **nicht mehr einloggen** und kannst direkt loslegen!

## 🔒 Für Produktion

**WICHTIG:** In Produktion sollte `DISABLE_AUTH` **NICHT** gesetzt oder auf `false` gesetzt sein:

```env
DISABLE_AUTH=false
```

Oder einfach die Zeile ganz weglassen.

## 🧪 Testen

1. Starte das Backend mit `DISABLE_AUTH=true`
2. Öffne das Frontend: http://localhost:5173
3. Du solltest automatisch eingeloggt sein, ohne Login-Screen

## 🔍 Technische Details

### Was passiert im Hintergrund?

Wenn `DISABLE_AUTH=true` gesetzt ist, gibt die `get_current_user()` Dependency in `auth_api.py` automatisch einen Mock-User zurück, anstatt das JWT Token zu validieren.

### Mock User Details

```python
{
    "id": 1,
    "email": "dev@kalkulai.local",
    "name": "Dev User",
    "created_at": "2024-01-01 00:00:00",
    "updated_at": "2024-01-01 00:00:00",
}
```

### Betroffene Endpoints

Alle geschützten Endpoints verwenden weiterhin die gleiche Dependency, funktionieren aber ohne Token:

- `/api/auth/me` - Profil abrufen
- `/api/auth/change-password` - Passwort ändern
- `/api/auth/change-email` - Email ändern
- `/api/auth/profile` - Profil aktualisieren
- `/api/auth/layout/offer` - Layout speichern/laden
- und alle anderen geschützten Endpoints

## 🎯 Vorteile

✅ Keine nervigen Login-Prompts während der Entwicklung
✅ Schnellerer Entwicklungs-Workflow
✅ Einfach per Environment-Variable zu aktivieren/deaktivieren
✅ Keine Code-Änderungen nötig
✅ Sicher für Produktion (einfach nicht setzen)

## 🛠️ Troubleshooting

### Problem: Login ist immer noch aktiv

**Checkliste:**
- [ ] `.env` Datei existiert in `backend/`
- [ ] `DISABLE_AUTH=true` ist in der Datei
- [ ] Kein Kommentar (#) vor der Zeile
- [ ] Backend wurde neu gestartet
- [ ] Keine Tippfehler in der Variable

### Problem: "Nicht authentifiziert" Fehler

Das bedeutet, dass die Umgebungsvariable nicht geladen wurde.

**Lösung:**
1. Prüfe, ob `backend/.env` existiert
2. Prüfe, ob `DISABLE_AUTH=true` drin steht (ohne #)
3. Backend komplett neu starten (nicht nur reload)
4. Console-Output prüfen beim Start

### Variable zur Laufzeit prüfen

Du kannst prüfen, ob die Variable geladen wurde:

```python
import os
print(f"DISABLE_AUTH: {os.getenv('DISABLE_AUTH')}")
```

Oder im Backend-Code einen Debug-Print in `auth_api.py` hinzufügen:

```python
print(f"🔓 DISABLE_AUTH is: {DISABLE_AUTH}")
```

