# Kalkulai Backend - Technische Übersicht

## 🎯 Zweck des Systems

Kalkulai ist ein intelligentes Angebotserstellungssystem für Handwerker (speziell Maler- und Lackiererbetriebe). Das Backend verarbeitet natürliche Sprache, erkennt Materialbedarf, generiert Angebote und erstellt PDF-Dokumente.

---

## 🏗️ Architektur-Übersicht

```
Frontend (React/Vite)
    ↓ HTTP/REST
FastAPI Backend (main.py)
    ↓
Service Layer (quote_service.py) ← Single Source of Truth
    ↓
├── LLM Integration (llm.py)
├── Vector Search (retriever/)
├── Database Layer (store/)
├── PDF Generation (pdf.py)
└── MCP Server (mcp/) - Optional für externe LLM-Hosts
```

### Kernprinzipien

1. **Service Layer First**: Alle Business-Logik liegt in `quote_service.py`
2. **Zwei-LLM-Architektur**: LLM1 (Chat/Erfassung) + LLM2 (Angebotsgenerierung)
3. **Hybrid Search**: BM25 + Lexical + RRF für Produktsuche
4. **Multi-Tenant**: Company-basierte Datenisolation
5. **Stateful Sessions**: Wizard-Sessions für mehrstufige Workflows

---

## 📁 Projektstruktur

```
backend/
├── main.py                    # FastAPI App Entry Point
├── app/
│   ├── services/
│   │   └── quote_service.py   # ⭐ KERN-MODUL: Alle Business-Logik
│   ├── llm.py                 # LLM-Initialisierung & Chain-Building
│   ├── db.py                  # Legacy: Statische Produktdateien laden
│   ├── pdf.py                 # PDF-Generierung (WeasyPrint + Jinja2)
│   ├── admin_api.py           # CRUD für Produkte (REST API)
│   ├── auth_api.py            # Authentifizierung (JWT)
│   ├── auth.py                # User-Management (SQLite)
│   ├── offers_api.py          # Angebots-Verwaltung
│   ├── speech_api.py           # Azure Speech-to-Text
│   ├── uom_convert.py         # Einheiten-Umrechnung
│   ├── utils.py               # Helper-Funktionen
│   └── mcp/                   # Model Context Protocol Server
│       ├── server.py          # MCP JSON-over-stdio Dispatcher
│       └── tools.py           # MCP Tool Wrapper
├── retriever/
│   ├── thin.py                # ⭐ Hybrid Search (BM25 + Lexical + RRF)
│   ├── index_manager.py        # Vector Index Management (DocArray)
│   ├── hybrid_search.py       # BM25 Implementation
│   └── main.py                # Legacy: ChromaDB Retriever
├── store/
│   └── catalog_store.py       # ⭐ SQLModel ORM für Produkte
├── shared/
│   ├── normalize/              # Text-Normalisierung & Synonyme
│   └── package_converter.py   # Gebinde-Umrechnung
├── templates/                  # Jinja2 PDF-Templates
├── data/                      # Statische Produktdateien (.txt)
└── var/                       # SQLite DB (kalkulai.db)
```

---

## 🔑 Kernkomponenten im Detail

### 1. Service Layer (`app/services/quote_service.py`)

**Rolle**: Single Source of Truth für alle Business-Logik

**Wichtigste Funktionen**:
- `chat_turn()` - LLM1 Chat-Interaktion (Erfassung von Projektanforderungen)
- `generate_offer_positions()` - LLM2 Angebotsgenerierung (JSON-Output)
- `search_catalog()` - Produktsuche mit Fuzzy-Matching
- `render_offer_or_invoice_pdf()` - PDF-Generierung
- `wizard_next_step()` / `wizard_finalize()` - Wizard-Workflow
- `run_revenue_guard()` - Margenprüfung

**QuoteServiceContext**:
- Zentraler Context-Container mit:
  - LLM-Instanzen (llm1, llm2)
  - LangChain Chains (chain1, chain2)
  - Memory (memory1)
  - Retriever
  - Catalog-Datenstrukturen
  - Wizard-Sessions
  - Jinja2 Environment
  - Konfiguration (VAT, Thresholds, etc.)

**Design-Pattern**: 
- Alle Funktionen nehmen `ctx: QuoteServiceContext` als Parameter
- Keine globalen Zustände innerhalb des Service-Layers
- ServiceError für strukturierte Fehlerbehandlung

---

### 2. LLM-Integration (`app/llm.py`)

**Zwei-LLM-System**:

**LLM1** (Chat/Erfassung):
- **Modell**: `MODEL_LLM1` (default: `gpt-4o-mini`)
- **Temperature**: 0.15 (kreativer, aber kontrolliert)
- **Aufgabe**: 
  - Projektanforderungen erfassen
  - Materialbedarf schätzen
  - Rückfragen stellen
  - Status-Tracking (noch_zu_leisten / bereits_erledigt / unklar)
- **Memory**: ConversationBufferWindowMemory (letzte N Nachrichten)
- **Output**: Markdown-Text + Maschinenanhang (projekt_id, version, status, materialien[])

**LLM2** (Angebotsgenerierung):
- **Modell**: `MODEL_LLM2` (default: `gpt-4o-mini`)
- **Temperature**: 0.0 (deterministisch)
- **Aufgabe**: 
  - Strukturierte Angebotspositionen generieren (JSON)
  - Preise berechnen
  - Einheiten harmonisieren
- **Input**: Chat-History + Catalog-Candidates
- **Output**: JSON mit positions[], raw_llm, error?

**Chain-Building**:
- `build_chains()` erstellt LangChain Chains mit Retrieval-Augmented Generation (RAG)
- Retriever wird in Chain integriert für Kontext-Erweiterung
- Prompts sind in `llm.py` definiert (sehr detailliert, ~200 Zeilen)

**Provider-Support**:
- OpenAI (default)
- Ollama (lokal)
- HuggingFace (optional)

---

### 3. Produktsuche - Zwei Retriever-Systeme

Das System verwendet **zwei verschiedene Retriever**, die je nach Use-Case eingesetzt werden:

---

#### **A) Hybrid Search (`retriever/thin.py`)** ⚡

**Schnelle, deterministische Produktsuche ohne LLM.**

**Technologie**:
1. **BM25** (Keyword-basiert):
   - Term-Frequency / Inverse Document Frequency
   - Gute Performance für exakte Matches

2. **Lexical Search** (Fuzzy-Matching):
   - SequenceMatcher für Ähnlichkeit
   - Synonym-Erkennung
   - Prefix/Substring-Boosts
   - Confusion-Pair-Penalties (z.B. "krepp" vs "kreide")

3. **RRF** (Reciprocal Rank Fusion):
   - Kombiniert BM25 + Lexical Scores
   - Formel: `score = 1 / (k + rank)` für beide Rankings

**Scoring-Boni**:
- Exact Match: +0.25
- Synonym Hit: +0.15
- Keyword Match: +0.15
- Price Available: +0.03
- Confusion Penalty: -0.3

**Pre-Filtering**:
- Test-Produkte werden ausgefiltert (SKU-Prefixes: `test-`, `demo-`)
- Inactive Products werden ignoriert
- Category-Filterung möglich

**Wann wird Hybrid Search verwendet?**

1. **LLM1 Chat (`chat_turn()`)**:
   - **Nur wenn** `LLM1_THIN_RETRIEVAL=1` gesetzt ist
   - Funktion: `_build_catalog_candidates()` → `_run_thin_catalog_search()`
   - Zweck: Schnelle Produktvorschläge während des Chats
   - Output: Katalog-Vorschläge werden in Chat-Antwort eingefügt

2. **API `/api/catalog/search`**:
   - **Primär** wenn kein Vector Retriever vorhanden (`ctx.retriever == None`)
   - Funktion: `search_catalog()` → `_catalog_lookup()` → Fallback zu `search_catalog_thin()`
   - Zweck: Direkte Produktsuche via API

3. **Material-Validierung**:
   - Funktion: `_validate_materials()` → `_run_thin_catalog_search()`
   - Zweck: Prüfung ob Materialien im Katalog existieren

**Vorteile**:
- ✅ Sehr schnell (keine Embedding-Generierung)
- ✅ Deterministisch (reproduzierbare Ergebnisse)
- ✅ Gute Tippfehlerkorrektur
- ✅ Synonym-Erkennung
- ✅ Keine LLM-Abhängigkeit

---

#### **B) Vector Index (`retriever/index_manager.py`)** 🧠

**Semantische Suche über Embeddings.**

**Technologie**:
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2`
- **Backend**: DocArray InMemoryExactNN
- **Similarity**: Cosine Similarity
- **Multi-Tenant**: Separate Indizes pro Company-ID

**Wann wird Vector Index verwendet?**

1. **LLM1 Chat Context-Erweiterung**:
   - **Wenn** `ctx.retriever` vorhanden ist UND `LLM1_THIN_RETRIEVAL=0`
   - Funktion: `chat_turn()` → LangChain Chain mit Retriever
   - Zweck: Semantische Kontext-Erweiterung für LLM1
   - Input: Chat-History wird als Query verwendet

2. **LLM2 Angebotsgenerierung (`generate_offer_positions()`)**:
   - **Immer** wenn `ctx.retriever` vorhanden ist
   - Funktion: `find_exact_catalog_lines()` → `ctx.retriever.get_relevant_documents()`
   - Zweck: Semantische Suche für Produktkontext
   - Verwendung: Context-Erweiterung für LLM2 Prompt

3. **Ranking (`rank_main()`)**:
   - Funktion: `_run_rank_main()` → `rank_main()` → `ctx.retriever.get_relevant_documents()`
   - Zweck: Business-Scoring mit semantischen Kandidaten
   - Verwendung: In `generate_offer_positions()` für bessere Produktauswahl

4. **Company-spezifische Suche**:
   - Funktion: `_company_catalog_search()` → `index_manager.search_index()`
   - Zweck: Multi-Tenant Produktsuche

**Vorteile**:
- ✅ Semantisches Verständnis ("Außenfarbe" = "Fassadenfarbe")
- ✅ Bedeutungsähnlichkeit (nicht nur Keyword-Match)
- ✅ Gute Performance bei unklaren Begriffen
- ✅ Multi-Tenant Support

**Nachteile**:
- ⚠️ Langsamer als Hybrid Search (Embedding-Generierung)
- ⚠️ Benötigt initialen Index-Build
- ⚠️ Abhängig von Embedding-Modell-Qualität

---

#### **Entscheidungslogik: Welcher Retriever wird wann verwendet?**

```python
# 1. LLM1 Chat - Katalog-Vorschläge
if ctx.llm1_thin_retrieval == True:
    # → Hybrid Search (thin.py)
    candidates = _build_catalog_candidates()  # Nutzt search_catalog_thin()
else:
    # → Vector Index (wenn retriever vorhanden)
    # → LangChain Chain mit Retriever für Context-Erweiterung

# 2. API /api/catalog/search
if ctx.retriever is None:
    # → Hybrid Search (thin.py) als Fallback
    results = search_catalog_thin()
else:
    # → Vector Index (index_manager)
    docs = ctx.retriever.get_relevant_documents(query)

# 3. LLM2 Angebotsgenerierung
if ctx.retriever is not None:
    # → Vector Index für semantische Context-Erweiterung
    ctx_lines = find_exact_catalog_lines()  # Nutzt retriever
    ranked = rank_main()  # Nutzt retriever für Business-Scoring
```

**Konfiguration**:
- `LLM1_THIN_RETRIEVAL=1` → Hybrid Search für LLM1 Chat-Vorschläge
- `LLM1_THIN_RETRIEVAL=0` → Vector Index für LLM1 Context (wenn verfügbar)
- Vector Index wird **immer** für LLM2 verwendet (wenn verfügbar)

**Empfehlung**:
- **Hybrid Search**: Für schnelle, deterministische Suchen, Tippfehlerkorrektur
- **Vector Index**: Für semantische Suche, unklare Begriffe, Context-Erweiterung
- **Kombination**: Beide können parallel verwendet werden für verschiedene Use-Cases

**Technische Details Vector Index**:
- **Embedding-Modell**: `sentence-transformers/all-MiniLM-L6-v2` (default)
- **Backend**: DocArray InMemoryExactNN (Cosine Similarity)
- **Company-scoped**: Jede Company hat eigenen Index
- **Auto-Rebuild**: Bei Produkt-Updates wird Index neu gebaut
- **Thread-Safety**: Lock-Mechanismus für Cache-Updates
- **Fallback**: Wenn DocArray nicht verfügbar → einfache Cosine-Similarity Implementation

---

#### **Zusammenfassung: Retriever-Verwendung**

| Use-Case | Retriever | Bedingung | Funktion |
|----------|-----------|-----------|----------|
| **LLM1 Chat - Katalog-Vorschläge** | Hybrid Search | `LLM1_THIN_RETRIEVAL=1` | `_build_catalog_candidates()` |
| **LLM1 Chat - Standard** | Kein Retriever | `LLM1_THIN_RETRIEVAL=0` (default) | `chain1.run()` (nur Memory) |
| **LLM2 Angebotsgenerierung** | Vector Index | `retriever` vorhanden | `find_exact_catalog_lines()` + `rank_main()` |
| **API `/api/catalog/search`** | Hybrid Search | `retriever == None` (Fallback) | `search_catalog()` |
| **API `/api/catalog/search`** | Hybrid + Vector | `COMBINE_HYBRID_VECTOR=1` + `retriever` vorhanden | `search_catalog()` |
| **Material-Validierung** | Hybrid Search | Immer | `_validate_materials()` |
| **Business-Scoring** | Vector Index | `retriever` vorhanden | `rank_main()` |
| **Company-Suche** | Vector Index | Immer | `_company_catalog_search()` |

**Wichtig: LLM1 vs LLM2**:
- **LLM1**: 
  - `LLM1_THIN_RETRIEVAL=0` (default) → Kein Retriever, nur Memory
  - `LLM1_THIN_RETRIEVAL=1` → Hybrid Search für Katalog-Vorschläge (wird in Antwort eingefügt)
  - Chain1 hat **keinen Retriever integriert** (nur LLMChain)
- **LLM2**: 
  - Vector Index wird **immer** verwendet (wenn `retriever` vorhanden)
  - Chain2 nutzt `ConversationalRetrievalChain` mit Vector Retriever
  - Für Context-Erweiterung und Business-Scoring

---

### 5. Datenbank-Layer (`store/catalog_store.py`)

**SQLModel ORM** (SQLAlchemy-basiert):

**Tabellen**:

**products**:
```python
- id (PK)
- company_id (Index)  # Multi-Tenant
- sku (Index, Unique mit company_id)
- name, description
- price_eur, unit, volume_l
- category, material_type, unit_package, tags
- is_active (Index)
- updated_at (Index)
```

**synonyms**:
```python
- id (PK)
- company_id (Index)
- canon, variant (Unique mit company_id)
- confidence
- updated_at
```

**Wichtigste Funktionen**:
- `create_product()` / `update_product()` / `delete_product()`
- `get_active_products(company_id)` - Filtert inactive + test products
- `upsert_synonym()` - Synonym-Verwaltung
- `init_db()` - Schema-Erstellung

**DB-URL**: 
- Default: `sqlite:///backend/var/kalkulai.db`
- Konfigurierbar via `DB_URL` oder `KALKULAI_DB_URL`

**Migration**: 
- SQLModel erstellt Tabellen automatisch beim ersten Start

---

### 6. PDF-Generierung (`app/pdf.py`)

**WeasyPrint + Jinja2**:

**Templates**:
- `offer.html` - Standard-Template
- `offer_modern.html` - Modernes Design
- `offer_premium.html` - Premium-Variante
- `offer_custom.html` - Customizable

**Workflow**:
1. Jinja2 Template laden
2. Context-Daten einfügen (positions[], customer_info, etc.)
3. WeasyPrint rendert HTML → PDF
4. PDF wird in `OUTPUT_DIR` gespeichert
5. URL wird zurückgegeben (`/outputs/{filename}.pdf`)

**Features**:
- Currency-Formatierung (Jinja2 Filter)
- Date-Formatierung
- Responsive Layout
- Logo-Integration

**Static Files**:
- FastAPI mountet `/outputs` für PDF-Downloads

---

### 7. API-Endpoints (`main.py`)

**Haupt-Endpoints**:

```
POST /api/chat              # LLM1 Chat-Turn
POST /api/offer             # LLM2 Angebotsgenerierung
POST /api/pdf               # PDF-Rendering
POST /api/session/reset     # Memory & Wizard Reset

GET  /api/catalog/search    # Produktsuche
GET  /api/catalog           # Catalog-Übersicht

POST /wizard/maler/next     # Wizard-Step
POST /wizard/maler/finalize # Wizard-Abschluss

POST /revenue-guard/check   # Margenprüfung
```

**Admin-Endpoints** (`admin_api.py`):
```
POST   /api/admin/products        # Produkt erstellen
PUT    /api/admin/products/{sku}   # Produkt aktualisieren
DELETE /api/admin/products/{sku}   # Produkt löschen
POST   /api/admin/products/rebuild # Index neu bauen
```

**Auth-Endpoints** (`auth_api.py`):
```
POST /api/auth/login        # JWT-Token generieren
POST /api/auth/register     # User-Registrierung
GET  /api/auth/me           # Current User
```

**CORS**:
- Konfigurierbar via `FRONTEND_ORIGINS`
- Default: `localhost:5173`, HuggingFace Spaces

---

### 8. MCP Server (`app/mcp/`)

**Model Context Protocol** - Externe LLM-Host-Integration:

**Architektur**:
```
LLM Host (Claude Desktop, etc.)
    ↓ JSON/stdio
MCP Server (server.py)
    ↓
MCP Tools (tools.py)
    ↓
Quote Service Layer
```

**Tools**:
- `reset_session` - Session zurücksetzen
- `chat_turn` - Chat-Interaktion
- `generate_offer_positions` - Angebot generieren
- `render_pdf` - PDF erstellen
- `wizard_next_step` - Wizard-Step
- `revenue_guard_check` - Margenprüfung

**Vorteil**: 
- Externe LLM-Hosts können Kalkulai-Funktionen direkt aufrufen
- Keine neuen HTTP-Endpoints nötig
- Type-Safe Tool-Definitionen

---

## 🔄 Datenfluss-Beispiele

### Beispiel 1: Chat → Angebot → PDF

```
1. User: "Ich brauche Angebot für 50m² Wand streichen"
   ↓
2. POST /api/chat
   → quote_service.chat_turn()
   → LLM1 verarbeitet Anfrage
   → Rückfragen oder Materialliste
   ↓
3. User: "Passt so"
   ↓
4. POST /api/offer
   → quote_service.generate_offer_positions()
   → LLM2 generiert JSON mit Positionen
   → Catalog-Suche für Preise
   → Einheiten-Harmonisierung
   ↓
5. POST /api/pdf
   → quote_service.render_offer_or_invoice_pdf()
   → Jinja2 Template + WeasyPrint
   → PDF gespeichert
   → URL zurückgegeben
```

### Beispiel 2: Produktsuche

```
1. User sucht "Dispersionsfarbe weiß"
   ↓
2. POST /api/catalog/search?q=dispersionsfarbe+weiß
   ↓
3. quote_service.search_catalog()
   → retriever.thin.search_catalog_thin()
   → Hybrid Search:
      - BM25: Keyword-Match
      - Lexical: Fuzzy-Match + Synonyme
      - RRF: Score-Fusion
   → Top-K Ergebnisse zurückgeben
```

### Beispiel 3: Produkt erstellen

```
1. POST /api/admin/products
   → admin_api.create_product()
   → catalog_store.create_product()
   → DB INSERT
   → index_manager.invalidate_index()
   → refresh_catalog_cache()
   → Index wird beim nächsten Search neu gebaut
```

---

## ⚙️ Konfiguration (Environment Variables)

**LLM**:
- `MODEL_PROVIDER` - `openai` | `ollama` | `huggingface`
- `MODEL_LLM1` - Modell für Chat (default: `gpt-4o-mini`)
- `MODEL_LLM2` - Modell für Angebot (default: `gpt-4o-mini`)
- `OPENAI_API_KEY` - API-Key für OpenAI
- `OLLAMA_BASE_URL` - URL für lokalen Ollama-Server

**Datenbank**:
- `DB_URL` / `KALKULAI_DB_URL` - Datenbank-URL
- `DATA_ROOT` - Root-Verzeichnis für Daten
- `CHROMA_DIR` - Verzeichnis für ChromaDB (Legacy)

**Search**:
- `CATALOG_TOP_K` - Anzahl Ergebnisse (default: 5)
- `CATALOG_CACHE_TTL` - Cache-TTL in Sekunden (default: 60)
- `CATALOG_QUERIES_PER_TURN` - Max. Suchqueries pro Chat-Turn (default: 2)
- `LLM1_THIN_RETRIEVAL` - **Wichtig**: 
  - `0` (default) → Vector Index für LLM1 Context-Erweiterung
  - `1` → Hybrid Search für LLM1 Katalog-Vorschläge (schneller, deterministisch)
- `COMBINE_HYBRID_VECTOR` - **Neu**: Kombiniert Hybrid Search + Vector Search
  - `0` (default) → Nur Hybrid Search (BM25 + Lexical)
  - `1` → Hybrid Search + Vector Search kombiniert via RRF (beste Ergebnisse, aber langsamer)

**Business-Logic**:
- `VAT_RATE` - Mehrwertsteuer (default: 0.19)
- `ADOPT_THRESHOLD` - Threshold für Produkt-Adoption (default: 0.82)
- `LLM1_MODE` - `assistive` | `autonomous` (default: `assistive`)
- `BUSINESS_SCORING` - Komma-separierte Flags: `margin,availability`

**Development**:
- `DEBUG` - Debug-Modus (default: 0)
- `SKIP_LLM_SETUP` - LLM-Setup überspringen (für Tests)
- `FORCE_RETRIEVER_BUILD` - Index immer neu bauen

**Security**:
- `ADMIN_API_KEY` - API-Key für Admin-Endpoints
- `FRONTEND_ORIGINS` - CORS-Origins (komma-separiert)

---

## 🧪 Testing

**Test-Struktur**:
```
backend/testing/
├── test_quote_service.py      # Service-Layer Tests
├── test_retriever_thin.py      # Search-Tests
├── test_store.py               # DB-Tests
├── test_admin_api.py           # API-Tests
└── test_smoke.py               # Smoke Tests
```

**Smoke Tests**:
- Können ohne LLM laufen (`SKIP_LLM_SETUP=1`)
- Prüfen grundlegende Funktionalität
- Schnelle CI/CD-Integration

---

## 🚀 Deployment

**Docker**:
- `Dockerfile` vorhanden
- Port: 7860 (konfigurierbar via `PORT`)
- HuggingFace Spaces kompatibel

**Start**:
```bash
python main.py
# oder
uvicorn main:app --host 0.0.0.0 --port 7860
```

**Initialisierung**:
- DB wird automatisch erstellt beim ersten Start
- Index wird beim ersten Search gebaut
- Demo-User wird erstellt (`admin@kalkulai.de` / `kalkulai2024`)

---

## 📊 Performance-Optimierungen

1. **Caching**:
   - Catalog-Cache (60s TTL)
   - Search-Cache (pro Query + Top-K)
   - Index-Cache (pro Company)

2. **Pre-Filtering**:
   - Test-Produkte werden früh ausgefiltert
   - Inactive Products werden ignoriert

3. **Hybrid Search**:
   - BM25 ist sehr schnell
   - Lexical Search ist deterministisch (keine LLM-Calls)
   - RRF kombiniert beide effizient

4. **Lazy Loading**:
   - Index wird erst beim ersten Search gebaut
   - Embeddings werden nur bei Bedarf generiert

---

## 🔍 Wichtige Design-Entscheidungen

1. **Service Layer Pattern**:
   - Alle Business-Logik in `quote_service.py`
   - FastAPI-Endpoints sind dünne Wrapper
   - MCP-Tools nutzen denselben Service-Layer

2. **Zwei-LLM-Architektur**:
   - LLM1: Kreativ, interaktiv (Chat)
   - LLM2: Deterministisch, strukturiert (Angebot)
   - Klare Trennung der Verantwortlichkeiten

3. **Hybrid Search**:
   - BM25 für Keyword-Matches
   - Lexical für Fuzzy-Matching
   - Keine Abhängigkeit von Vector-Embeddings für alle Suchen

4. **Multi-Tenant**:
   - Company-ID in allen DB-Queries
   - Separate Indizes pro Company
   - Isolation auf Datenbank-Ebene

5. **Stateful Sessions**:
   - Wizard-Sessions für mehrstufige Workflows
   - Memory wird zwischen Chat-Turns beibehalten
   - Reset-Endpoint für Session-Clearing

---

## 🐛 Bekannte Limitationen & Tech Debt

1. **Legacy ChromaDB**:
   - Wird noch für statische Produktdateien verwendet
   - Sollte langfristig durch `index_manager` ersetzt werden

2. **Statische Produktdateien**:
   - `.txt`-Dateien in `data/` werden noch unterstützt
   - Migration zu DB-basiertem System ist im Gange

3. **Memory-Management**:
   - ConversationBufferWindowMemory begrenzt auf letzte N Nachrichten
   - Keine persistente Session-Storage

4. **Error-Handling**:
   - ServiceError wird verwendet, aber nicht überall konsistent
   - Manche Fehler werden als HTTPException geworfen

---

## 📚 Weiterführende Dokumentation

- `docs/mcp-overview.md` - MCP-Architektur Details
- `PHASE1_IMPROVEMENTS.md` - Phase 1 Verbesserungen
- `PHASE2_MENGENBERECHNUNG.md` - Mengenberechnung-Logik
- `PHASE3_HYBRID_SEARCH.md` - Hybrid Search Implementation

---

## 💡 Quick Start für neue Entwickler

1. **Repository klonen & Dependencies installieren**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Environment-Variablen setzen**:
   ```bash
   export OPENAI_API_KEY="sk-..."
   export MODEL_PROVIDER="openai"
   
   # Retriever-Konfiguration (optional):
   export LLM1_THIN_RETRIEVAL=0  # 0=Vector Index, 1=Hybrid Search für LLM1
   ```

3. **Backend starten**:
   ```bash
   python main.py
   ```

4. **Erste Schritte**:
   - `main.py` lesen → Versteht App-Struktur
   - `app/services/quote_service.py` lesen → Versteht Business-Logik
   - `retriever/thin.py` lesen → Versteht Search-Logik
   - `store/catalog_store.py` lesen → Versteht DB-Layer

5. **Tests ausführen**:
   ```bash
   pytest testing/
   ```

---

## 🎓 Code-Stil & Best Practices

- **Type Hints**: Überall verwendet (`from __future__ import annotations`)
- **Docstrings**: Wichtige Funktionen haben Docstrings
- **Error-Handling**: ServiceError für strukturierte Fehler
- **Logging**: `logger.info()` für wichtige Events
- **Imports**: `from __future__ import annotations` am Anfang
- **Path-Handling**: `pathlib.Path` statt Strings

---

**Erstellt**: 2025-01-27  
**Version**: 1.0  
**Autor**: Backend-Team Kalkulai

