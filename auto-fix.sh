#!/bin/bash
# KALKULAI AUTO-FIX SCRIPT
# Macht alle 3 Fixes automatisch

set -e  # Stop on error

echo "🔧 Kalkulai Auto-Fix Script"
echo "============================"
echo ""

# Check if we're in the right directory
if [ ! -f "backend/app/llm.py" ]; then
    echo "❌ Error: Bitte im kalkulai Root-Verzeichnis ausführen!"
    exit 1
fi

echo "✅ Repository gefunden"
echo ""

# Backup original files
echo "📦 Erstelle Backups..."
cp backend/app/llm.py backend/app/llm.py.backup
cp backend/app/services/quote_service.py backend/app/services/quote_service.py.backup
cp backend/requirements.txt backend/requirements.txt.backup
echo "✅ Backups erstellt (.backup files)"
echo ""

# FIX 1: Update imports in llm.py
echo "🔧 Fix 1: Aktualisiere LangChain imports..."
sed -i.tmp 's/from langchain\.prompts import PromptTemplate/from langchain_core.prompts import PromptTemplate/' backend/app/llm.py
sed -i.tmp 's/from langchain\.chains import LLMChain, ConversationalRetrievalChain/from langchain.chains import LLMChain/' backend/app/llm.py
rm backend/app/llm.py.tmp
echo "✅ Imports aktualisiert"

# FIX 2: Add material specification rule in llm.py
echo "🔧 Fix 2: Füge Materialien-Spezifikation hinzu..."
# This is complex, so we'll use a Python script
python3 << 'PYTHON_SCRIPT'
import re

with open('backend/app/llm.py', 'r') as f:
    content = f.read()

# Find the section with rules E, F, G, H
old_text = """E) Keine Gebinde-Logik: Nur Basis-Einheiten (kg, L, m², m, Stück) ausgeben.
F) Transparenz & Rückfragen: Bei Unsicherheiten (Deckkraft, Schichtdicke, Flächenangabe) kurze Einschätzung + gezielte Klärungsfrage statt Annahmen/Neuberechnung.
G) Sicherheitsreserve Hauptmaterialien: Farbe/Spachtel/Grundierung/Lack mit ~5–15 % Reserve, praxisgerecht runden und Reserve kurz begründen.
H) Hilfs-/Verbrauchsmaterial: 10–30 % Aufschlag je nach Größe/Komplexität, sinnvoll runden und begründen."""

new_text = """E) Keine Gebinde-Logik: Nur Basis-Einheiten (kg, L, m², m, Stück) ausgeben.
F) **MATERIALIEN-SPEZIFIKATION (KRITISCH):**
   - Verwende IMMER vollständige, spezifische Produktnamen mit ALLEN vom Kunden genannten Eigenschaften
   - Inkludiere Produkttyp + Eigenschaften (Farbe, Anwendung, etc.)
   - Beispiele RICHTIG: "Dispersionsfarbe weiß", "Tiefgrund Innen", "Kreppband 19mm", "Acryllack weiß hochglänzend"
   - Beispiele FALSCH: "Farbe", "Grundierung", "Klebeband", "Lack"
   - Bei generischen User-Angaben ("weiße Farbe"): Interpretiere als "Dispersionsfarbe weiß" (Standard für Innenanstrich)
   - Bei unklarem Produkttyp: Kurze Rückfrage statt generischem Begriff
G) Transparenz & Rückfragen: Bei Unsicherheiten (Deckkraft, Schichtdicke, Flächenangabe) kurze Einschätzung + gezielte Klärungsfrage statt Annahmen/Neuberechnung.
H) Sicherheitsreserve Hauptmaterialien: Farbe/Spachtel/Grundierung/Lack mit ~5–15 % Reserve, praxisgerecht runden und Reserve kurz begründen.
I) Hilfs-/Verbrauchsmaterial: 10–30 % Aufschlag je nach Größe/Komplexität, sinnvoll runden und begründen."""

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('backend/app/llm.py', 'w') as f:
        f.write(content)
    print("✅ Material-Regel eingefügt")
else:
    print("⚠️  Konnte Materialien-Regel nicht automatisch einfügen (manuell nötig)")
PYTHON_SCRIPT

# FIX 3: Lower threshold in quote_service.py
echo "🔧 Fix 3: Senke Matching-Threshold..."
sed -i.tmp 's/CATALOG_STRONG_MATCH_THRESHOLD = 0\.6/CATALOG_STRONG_MATCH_THRESHOLD = 0.5  # Lowered from 0.6 for better fuzzy matching with dynamic catalogs/' backend/app/services/quote_service.py
rm backend/app/services/quote_service.py.tmp
echo "✅ Threshold gesenkt (0.6 → 0.5)"

# FIX 4: Support einzelpreis in PDF rendering
echo "🔧 Fix 4: Fixe PDF-Preisberechnung..."
python3 << 'PYTHON_SCRIPT'
with open('backend/app/services/quote_service.py', 'r') as f:
    content = f.read()

# Find and replace the epreis line
old_line = '            epreis_val = float(p.get("epreis", 0))'
new_lines = '''            # Support both "epreis" and "einzelpreis"
            epreis_val = float(p.get("epreis") or p.get("einzelpreis", 0))'''

if old_line in content:
    content = content.replace(old_line, new_lines)
    with open('backend/app/services/quote_service.py', 'w') as f:
        f.write(content)
    print("✅ PDF-Preisberechnung gefixt")
else:
    print("⚠️  Konnte PDF-Fix nicht automatisch anwenden (manuell nötig)")
PYTHON_SCRIPT

# FIX 5: Clean up requirements.txt (optional)
echo "🔧 Fix 5: Bereinige requirements.txt..."
python3 << 'PYTHON_SCRIPT'
with open('backend/requirements.txt', 'r') as f:
    lines = f.readlines()

# Find and replace the langchain section
new_lines = []
skip_until_openai = False

for line in lines:
    # Skip ollama and huggingface lines
    if 'langchain-ollama' in line or 'langchain-huggingface' in line:
        continue
    
    # Comment out sentence-transformers
    if line.strip().startswith('sentence-transformers'):
        new_lines.append('# sentence-transformers>=3.0.1,<4.0  # Kommentiert: Nur für lokale Embeddings nötig\n')
        continue
    
    # Add langchain core if missing
    if 'langchain-community' in line and not any('langchain>=' in l for l in new_lines[-3:]):
        new_lines.append('langchain>=0.3.0,<0.4\n')
    
    new_lines.append(line)

with open('backend/requirements.txt', 'w') as f:
    f.writelines(new_lines)

print("✅ Requirements bereinigt")
PYTHON_SCRIPT

echo ""
echo "✅ ALLE FIXES ANGEWENDET!"
echo ""
echo "📋 Nächste Schritte:"
echo "  1. git status                    # Prüfe Änderungen"
echo "  2. git diff                      # Siehe was geändert wurde"
echo "  3. git add .                     # Stage alle Änderungen"
echo "  4. git commit -m 'Fix: LLM material matching'"
echo "  5. git push origin fix/llm-material-matching"
echo ""
echo "💾 Backups wurden erstellt (.backup files)"
echo "   Falls etwas schiefgeht: cp *.backup <original>"
