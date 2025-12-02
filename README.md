# KalkulAI

Intelligente Angebotserstellung für Handwerker. FastAPI Backend mit LLM-Integration und React/Vite Frontend.

## 📁 Projektstruktur

```
kalkulai/
├── backend/                    # FastAPI Backend
│   ├── app/                    # Hauptanwendung
│   │   ├── auth.py            # Authentifizierung (User, JWT)
│   │   ├── auth_api.py        # Auth API Endpoints
│   │   ├── admin_api.py       # Admin API (Produktverwaltung)
│   │   ├── llm.py             # LLM Integration
│   │   ├── pdf.py             # PDF-Generierung
│   │   └── services/          # Business Logic
│   ├── data/                   # Produktdaten
│   ├── retriever/              # Vektor-Suche
│   ├── store/                  # Datenbank-Layer
│   ├── templates/              # PDF-Templates
│   ├── var/                    # Datenbank (kalkulai.db)
│   ├── main.py                 # FastAPI App
│   └── requirements.txt
│
├── frontend/                   # React/Vite Frontend
│   ├── src/
│   │   ├── components/        # UI Komponenten
│   │   ├── contexts/          # React Context (Auth)
│   │   ├── pages/             # Seiten (Login, Index)
│   │   └── lib/               # API Client, Utilities
│   └── package.json
│
└── docs/                       # Dokumentation
```

## 🚀 Schnellstart

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Umgebungsvariablen setzen
export OPENAI_API_KEY="sk-..."

# Server starten
python main.py
```

Backend läuft auf `http://localhost:7860`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend läuft auf `http://localhost:5173`

## 🔐 Login

Nach dem Start wird automatisch ein Demo-User erstellt:

- **E-Mail:** `admin@kalkulai.de`
- **Passwort:** `kalkulai2024`

## ⚙️ Umgebungsvariablen

### Backend (.env)

| Variable | Beschreibung | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API Key | - |
| `MODEL_PROVIDER` | LLM Provider (openai/ollama) | `openai` |
| `MODEL_LLM1` | Chat-Modell | `gpt-4o-mini` |
| `MODEL_LLM2` | Angebots-Modell | `gpt-4o-mini` |
| `VAT_RATE` | Mehrwertsteuersatz | `0.19` |
| `DEBUG` | Debug-Modus | `0` |
| `AZURE_SPEECH_KEY` | Azure Speech Services API Key (für Voice Input) | - |
| `AZURE_SPEECH_REGION` | Azure Region (z.B. "westeurope", "eastus") | `westeurope` |

### Frontend (.env)

| Variable | Beschreibung | Default |
|----------|-------------|---------|
| `VITE_API_BASE` | Backend URL | `http://localhost:7860` |

## 📋 Features

- **Chat-basierte Angebotserstellung** - Beschreibe dein Projekt, KalkulAI erstellt das Angebot
- **Wizard-Modus** - Geführte Eingabe für Maler-Projekte
- **Angebots-Editor** - Positionen manuell anpassen vor PDF-Export
- **Revenue Guard** - Vergessene Materialien automatisch vorschlagen
- **Produktdatenbank** - Eigene Produkte verwalten (CSV-Import)
- **Benutzerverwaltung** - Login, Passwort/E-Mail ändern
- **Voice Input** - Spracherkennung für Spracheingabe (Azure Speech Services)

## 🎤 Voice Input Setup

Das Voice-Input-Feature verwendet Azure Speech Services für die Spracherkennung.

### 1. Azure Speech Services einrichten

1. Erstelle eine Azure Speech Services Ressource im [Azure Portal](https://portal.azure.com)
2. Kopiere den **Key** und die **Region** (z.B. "westeurope") aus der Ressource

### 2. Umgebungsvariablen konfigurieren

Füge folgende Zeilen zu `backend/.env` hinzu:

```bash
AZURE_SPEECH_KEY=dein-azure-speech-key-hier
AZURE_SPEECH_REGION=westeurope
```

### 3. Backend neu starten

Nach dem Setzen der Umgebungsvariablen muss das Backend neu gestartet werden:

```bash
cd backend
python main.py
```

### 4. Testen

1. Öffne die Anwendung im Browser
2. Der Mikrofon-Button sollte jetzt aktiv (nicht ausgegraut) sein
3. Klicke auf den Mikrofon-Button und erlaube den Mikrofonzugriff
4. Sprich in das Mikrofon - deine Sprache wird in Text umgewandelt

**Hinweis:** Der Button ist ausgegraut, wenn:
- `AZURE_SPEECH_KEY` nicht gesetzt ist
- Das Backend nicht läuft
- Der Browser keine Mikrofonberechtigung erteilt hat

## 🧪 Tests

```bash
# Backend Tests
cd backend
pip install -r requirements-dev.txt
pytest testing/

# Frontend Tests
cd frontend
npm run test
```

## 📄 Lizenz

Proprietär - Alle Rechte vorbehalten.
