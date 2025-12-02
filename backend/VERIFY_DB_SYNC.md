# Datenbank-Synchronisation Verifizierung

## ✅ Durchgeführte Änderungen

### 1. Statische Produktdatei entfernt
**Datei:** `backend/main.py` - Funktion `_get_dynamic_catalog_items()`

**Vorher:** System hat BEIDE Quellen geladen:
- Datenbank (51 aktive Produkte)
- Statische Datei `maler_lackierer_produkte.txt` (100 Produkte)
- **Total im Export: 151 Produkte** ❌

**Nachher:** System lädt NUR aus der Datenbank:
- Datenbank (51 aktive Produkte)
- **Total im Export: 51 Produkte** ✅

### 2. Doppelte Datenbank gelöscht
- Gelöscht: `backend/backend/var/kalkulai.db` (32 KB, alt/dupliziert)
- Aktiv: `backend/var/kalkulai.db` (76 KB, korrekt)

### 3. Admin API bereits korrekt konfiguriert
Die Admin API ruft automatisch `refresh_catalog_cache(force=True)` auf nach:
- Produkt erstellen/aktualisieren (`POST /api/admin/products`)
- Produkt löschen (`DELETE /api/admin/products/{sku}`)
- Index neu aufbauen (`POST /api/admin/index/rebuild`)
- CSV Import (Frontend ruft `rebuildIndex()` auf)

## 📊 Aktueller Datenbankstatus

```bash
# Produkte nach Status
sqlite3 backend/var/kalkulai.db "SELECT is_active, COUNT(*) FROM products WHERE company_id='demo' GROUP BY is_active;"
# Ergebnis:
# 0|7    (inaktiv)
# 1|51   (aktiv)
```

## ✅ Verifikation

### Schritt 1: Datenbank prüfen
```bash
cd /Users/felixmagiera/Desktop/kalkulai
sqlite3 backend/var/kalkulai.db "SELECT COUNT(*) FROM products WHERE company_id='demo' AND is_active=1;"
# Erwartetes Ergebnis: 51
```

### Schritt 2: Backend starten
```bash
cd backend
source venv/bin/activate  # oder: source ../venv/bin/activate
uvicorn main:app --reload --port 8000
```

### Schritt 3: Frontend testen
1. Öffne Frontend: http://localhost:5173
2. Gehe zu **Einstellungen > Datenbank**
3. Du solltest sehen: **"Gesamt: 58 Produkte, Aktiv: 51, Inaktiv: 7"**

### Schritt 4: Neues Produkt hinzufügen
1. Klicke auf **"+ Neu"**
2. Fülle aus:
   - SKU: `TEST-SYNC-001`
   - Name: `Test Synchronisation Produkt`
   - Beschreibung: `Test für DB-Sync`
   - Preis: `29.99`
   - Einheit: `l`
   - Volumen: `5`
   - Kategorie: `paint`
   - Aktiv: ✓
3. Klicke **"Speichern"**

### Schritt 5: Datenbank verifizieren
```bash
sqlite3 backend/var/kalkulai.db "SELECT sku, name, price_eur FROM products WHERE sku='TEST-SYNC-001';"
# Erwartetes Ergebnis: TEST-SYNC-001|Test Synchronisation Produkt|29.99
```

### Schritt 6: Excel-Export testen
1. Im Frontend: Klicke auf **"Export"** Button
2. CSV-Datei wird heruntergeladen
3. Öffne die CSV-Datei
4. **Erwartetes Ergebnis:** 
   - Anzahl Zeilen: 59 (58 alte + 1 neues Produkt)
   - Dein neues Produkt `TEST-SYNC-001` ist enthalten
   - **KEINE** Produkte aus der statischen Datei

### Schritt 7: CSV-Import testen
1. Erstelle eine Test-CSV:
```csv
sku,name,description,unit,volume_l,price_eur,active,category,material_type,unit_package,tags
TEST-CSV-001,CSV Import Test,Test für CSV Import,l,10,49.99,true,paint,test_paint,Eimer,test;import
```
2. Im Frontend: Gehe zum Tab **"Import"**
3. Füge die CSV-Daten ein
4. Klicke **"Importieren"**
5. Prüfe in der Datenbank:
```bash
sqlite3 backend/var/kalkulai.db "SELECT * FROM products WHERE sku='TEST-CSV-001';"
```

## 🎯 Erwartetes Verhalten

### ✅ Was jetzt funktioniert:
1. **Produkte hinzufügen** (Frontend) → Sofort in DB gespeichert
2. **Produkte bearbeiten** (Frontend) → Sofort in DB aktualisiert
3. **Produkte löschen** (Frontend) → Als inaktiv markiert in DB
4. **CSV Import** (Frontend) → Alle Produkte in DB importiert
5. **Excel Export** (Frontend) → Zeigt NUR DB-Produkte (nicht statische Datei)
6. **Katalog-Cache** → Wird automatisch nach jeder Änderung aktualisiert
7. **Suchindex** → Wird automatisch nach jeder Änderung neu aufgebaut

### ❌ Was NICHT mehr passiert:
1. Statische Datei wird NICHT mehr zum Katalog hinzugefügt
2. Export enthält KEINE doppelten Produkte mehr
3. Keine Diskrepanz zwischen DB und Export

## 🔧 Technische Details

### Katalog-Loading-Flow:
```
1. Frontend: Produkt hinzufügen/bearbeiten
   ↓
2. Admin API: POST /api/admin/products
   ↓
3. catalog_store.upsert_product() → Speichert in DB
   ↓
4. refresh_catalog_cache(force=True) → Lädt NUR aus DB
   ↓
5. index_manager.update_index() → Aktualisiert Suchindex
   ↓
6. Frontend: loadData() → Zeigt aktualisierte Liste
```

### Export-Flow:
```
1. Frontend: Export-Button klicken
   ↓
2. api.admin.listProducts(companyId, true, 10000)
   ↓
3. Backend: catalog_store.list_products()
   ↓
4. SQL: SELECT * FROM products WHERE company_id='demo'
   ↓
5. Frontend: CSV generieren mit DB-Daten
   ↓
6. Download: produkte_demo_YYYY-MM-DD.csv
```

## 📝 Zusammenfassung

**Problem gelöst:** ✅
- Katalog lädt jetzt NUR aus der Datenbank
- Excel-Export zeigt nur DB-Produkte (keine statischen Dateien)
- Alle Frontend-Operationen (hinzufügen, bearbeiten, löschen, CSV-Import) aktualisieren die DB sofort
- Katalog-Cache wird automatisch nach jeder Änderung aktualisiert

**Datenbank-Pfad:** `/Users/felixmagiera/Desktop/kalkulai/backend/var/kalkulai.db`

**Aktueller Stand:**
- 51 aktive Produkte
- 7 inaktive Produkte
- 58 Produkte gesamt

