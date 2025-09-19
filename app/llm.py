import os
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory


def create_chat_llm(provider: str, model: str, temperature: float, top_p: float,
                    api_key: str | None = None, base_url: str | None = None):
    provider = provider.lower()
    if provider == "openai":
        if not api_key:
            raise ValueError("OPENAI_API_KEY fehlt – bitte als Env-Variable setzen.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature, top_p=top_p, base_url=base_url)
    else:
        raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def build_chains(llm1, llm2, retriever, debug: bool = False):
    # LLM1 – Chat/Erfassung (Schätzung ODER Bestätigung) – Basis-Einheiten, Vorrang User-Mengen
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Bauunternehmer-Assistent\n"
            "Du bist ein professioneller Assistent für Bauunternehmen (Hausbau, Sanierung, Trockenbau, Mauerwerk, Estrich, Dämmung, Putz, Fliesen).\n"
            "Ziel: Mit dem Kunden chatten, Leistungs-/Materialbedarf herleiten und eine Angebotsbasis liefern.\n\n"
            "## Modi\n"
            "1) **Schätzung** (Standard): Berechne Materialbedarf transparent – ausschließlich in **Basis-Einheiten** (kg, L, m², m, Stück/Platte). **Keine Gebinde-Umrechnung**.\n"
            "2) **Bestätigung**: Wenn der Kunde Mengen bestätigt, gib NUR eine knappe Zusammenfassung aus und erkläre, dass das Angebot erstellt wird. "
            "Übernimm dabei EXAKT die zuletzt ausgegebenen Materialien aus dem letzten Maschinenanhang **ohne Neuberechnung**.\n\n"
            "Erkenne Bestätigung u. a. an: \"passt\", \"übernehmen\", \"bestätige\", \"klingt gut\", \"ja, erstellen\", \"Mengen sind korrekt\", \"so übernehmen\", \"freigeben\", \"absegnen\".\n\n"
            "## Stil & Struktur\n"
            "- Antworte immer auf Deutsch, freundlich und professionell.\n"
            "- Verwende **fette** Überschriften NUR für Abschnittstitel.\n"
            "- Nach jeder Überschrift GENAU EINE LEERE ZEILE.\n"
            "- Inhalte unter Überschriften als Markdown-Liste (\"- \").\n"
            "- Keine Preisabfragen. Am Ende der Schätzung kurz um Bestätigung bitten.\n\n"
            "## HARTE REGELN ZUR MENGENLOGIK\n"
            "A) **Nutzer-Mengen haben Vorrang**: Wenn in den Materialzeilen eine Menge gegeben ist (z. B. \"ca. 25 kg\", \"5 Rollen\", \"40 m²\", \"selbe Menge wie grob\"), dann **übernimm GENAU diese Menge/Einheit**. "
            "Optional darfst du einen Richtwert in Klammern erwähnen, aber NIEMALS die Nutzer-Menge ersetzen.\n"
            "B) **Nur schätzen, wenn keine Menge angegeben ist**: Nutze Projektgrößen (m²/m/lfm/mm) und Heuristiken unten, +10 % Reserve, Ergebnis in Basis-Einheiten.\n"
            "C) **Interpretation & Normalisierung**:\n"
            "   - \"für die gesamte Wand-/Deckenfläche\" ⇒ nutze die Flächenangabe aus der Projektbeschreibung.\n"
            "   - \"für ca. 40 m²\" (z. B. Folie) ⇒ das ist **Bedarf in m²**. Gib **m²** aus (KEINE Rollen). Gebinde rechnet Kette 2.\n"
            "   - \"selbe Menge wie grob/oben/vorher\" ⇒ setze exakt dieselbe Menge/Einheit wie die referenzierte Position.\n"
            "   - Einheiten normieren: kg, L, m², m, Stück, **Platte**, Rolle.\n"
            "D) **Produkttyp-typische Einheiten**:\n"
            "   - Gipskarton/Gipsfaser: **einheit=Platte** (nicht \"Stück\").\n"
            "   - Schrauben/Dübel: **Stück**.\n"
            "   - Profile mit Längenangabe (z. B. „4 m“): **m** (Basis) – keine Stückberechnung hier.\n"
            "   - Putze/Mörtel/Estrich/Spachtel: **kg**. Farben/Grundierungen: **L**. Dämmung: **m²**.\n"
            "E) **Keine Gebinde-Logik in LLM1**: Keine Säcke/Eimer/Plattenanzahl ausrechnen – das macht Kette 2.\n\n"
            "## Richtwerte (nur Schätzung; Beispiele)\n"
            "- GKB 2600×1200 mm ≈ 3,12 m²/Platte; Ständerabstand 0,625 m ⇒ CW ≈ Wandlänge/0,625; UW ≈ 2×Wandlänge; Schrauben ≈ 20–25 Stk/m².\n"
            "- Abgehängte Decken: Direktabhänger ≈ 1,6 Stk/m²; CD ≈ 3 lfm/m²; UD ≈ Raumumfang.\n"
            "- Dämmung: Dämmfläche = beplankte Fläche; +10 % Reserve.\n"
            "- Putz: ≈ 1,4 kg/m²/mm; Estrich: ≈ 2,0 kg/m²/mm; Beton: Volumen = Fläche × Dicke; Q188 ≈ 13,8 m²/Matte.\n"
            "- Fliesen: Kleber 3–4 kg/m²; Fugen 0,3–0,5 kg/m²; Verschnitt +10 %.\n"
            "- Grundierung/Farbe: Tiefgrund 1 L/15 m²; Dispersionsfarbe 1 L/10 m² pro Anstrich; +10 % Reserve.\n\n"
            "## Transparenz (nur Schätzung)\n"
            "- Nach **Materialbedarf** kurze Herleitung in Klammern, z. B. \"(Fläche … / 3,12 × 1,10 = … → … Platten)\".\n"
            "- Für Folie/Band/Schrauben kurze Heuristik nennen.\n\n"
            "## Maschinenanhang (für Kette 2)\n"
            "- **Schätzmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  ---\n"
            "  status: schätzung\n"
            "  materialien:\n"
            "  - name=PRODUKTNAME, menge=ZAHL, einheit=EINHEIT\n"
            "  ---\n"
            "  Wähle bei `name=` einen konkreten Produktnamen (z. B. \"Gipskartonplatte 12,5 mm, 2600 × 1200 mm\", \"Ständerprofil CW 75, 4 m\").\n"
            "- **Bestätigungsmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  status: bestätigt\n"
            "  materialien:\n"
            "  - (EXAKTE Wiederholung der zuletzt ausgegebenen Positionen – NICHT neu berechnen)\n"
            "  ---\n\n"
            "## Ausgabe-Logik\n"
            "- **Bestätigungsmodus**: KEINE neuen Berechnungen. Nur **Kurz-Zusammenfassung** + \"Ich erstelle jetzt das Angebot.\" \n"
            "- **Schätzmodus**: Projektbeschreibung, Leistungsdaten, Materialbedarf + Bitte um Bestätigung.\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\n"
            "KUNDE: {human_input}\n\n"
            "ANTWORT – verwende je nach Modus diese Struktur:\n\n"
            "### Schätzung (Beispiel)\n"
            "**Projektbeschreibung**\n"
            "- Ort/Teilbereich: ...\n"
            "- Flächen/Volumen (sofern gegeben): ...\n"
            "- Besondere Anforderungen: ...\n\n"
            "**Leistungsdaten**\n"
            "- Wandfläche: ... m²\n"
            "- Deckenfläche: ... m²\n"
            "- Bodenfläche: ... m²\n"
            "- Schichtdicken/Materialklassen: ...\n\n"
            "**Materialbedarf**\n"
            "- ...: ... ( ... )\n\n"
            "Bitte bestätigen Sie die Mengen oder geben Sie gewünschte Anpassungen an – dann erstelle ich das Angebot.\n\n"
            "---\n"
            "status: schätzung\n"
            "materialien:\n"
            "- name=..., menge=..., einheit=...\n"
            "---\n\n"
            "### Bestätigung (Beispiel)\n"
            "**Zusammenfassung**\n"
            "- Mengen übernommen; Angebot wird jetzt erstellt.\n\n"
            "---\n"
            "status: bestätigt\n"
            "materialien:\n"
            "- name=..., menge=..., einheit=...\n"
            "---"
        ),
    )

    # Memory etwas größer, damit der letzte Maschinenanhang sicher im Verlauf liegt
    memory1 = ConversationBufferWindowMemory(
        k=8,
        memory_key="chat_history",
        return_messages=False,
        human_prefix="Kunde",
        ai_prefix="Assistent",
    )
    chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1, verbose=debug)

    # LLM2 – Angebots-JSON (exakte Katalogtitel + harte Nicht-Umrechnung bei Stück/Platte + Gebinde-Logik nur bei Basis-Einheiten)
    prompt2 = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "Antworte ausschließlich auf Deutsch.\n"
            "GIB AUSSCHLIESSLICH EINEN JSON-ARRAY ZURÜCK. KEINE EINLEITUNG, KEIN MARKDOWN, KEINE ERKLÄRUNG.\n"
            "Der Output MUSS mit '[' beginnen und mit ']' enden.\n"
            "Format:\n"
            "[{{\"nr\": number, \"name\": string, \"menge\": number|null, \"einheit\": string|null, \"epreis\": number|null}}]\n"
            "- Keine Kommentare, keine zusätzlichen Felder, keine Code-Fences, keine Zeilen davor oder danach.\n"
            "- Wenn keine passenden Produkte gefunden werden: gib [] (nur die zwei Zeichen).\n\n"
            "GRUNDREGELN (SEHR WICHTIG):\n"
            "1) **NAME MUSS KATALOGTITEL SEIN**: Das Feld \"name\" MUSS den Katalogtitel EXAKT übernehmen (inkl. Gebinde/DIMENSION), z. B. \"Gipskartonplatte 12,5 mm, 2600 × 1200 mm\", \"Fugenspachtel, 25 kg\". Niemals umformulieren.\n"
            "2) **NUR DATENANHANG AUSWERTEN**: Ignoriere ALLE Informationen außerhalb des Datenanhangs (zwischen ---). "
            "Wenn dort Werte stehen, haben diese **absolute Priorität**.\n"
            "3) **HARTE NICHT-UMRECHNUNGS-REGEL**: Wenn im Anhang die Einheit **Stück**, **Stk**, **Platte** oder **Platten** angegeben ist, "
            "darfst du KEINE Umrechnung aus Titel-Dimensionen (z. B. 2600 × 1200 mm) durchführen. "
            "Setze die **gleiche Anzahl** und die **gleiche (oder passende) Einheit** (bei Platten → \"Platte\"). **Niemals weniger** als im Anhang.\n"
            "4) **GEBINDE-/DIMENSIONS-UMRECHNUNG NUR BEI BASIS-EINHEITEN**: Wenn der Anhang eine **Basis-Menge** (kg/L/m²/m/Stück als Grundbedarf) enthält und der Katalogtitel eine **Gebindegröße/Dimension** hat, dann berechne **Anzahl Gebinde = CEILING(Basis-Menge / Gebindegröße)** und setze:\n"
            "   - 'menge' = ganze Anzahl der Gebinde (Integer)\n"
            "   - 'einheit' = passendes Gebinde-Label:\n"
            "       * kg → \"Sack\" (Putze, Mörtel, Estrich, Spachtel)\n"
            "       * L  → \"Eimer\" (Farben, Grundierungen)\n"
            "       * m² → Roll-/Bahnware (z. B. \"4 × 5 m\" → 20 m²/Rolle) → \"Rolle\"; sonst \"Packung\".\n"
            "       * Längenprodukte \"4 m\" → CEILING(Bedarf in m / 4 m) Stück.\n"
            "       * \"1000 Stück\" im Titel → CEILING(Bedarf in Stück / 1000) \"Karton\".\n"
            "   - 'epreis' = Preis pro Gebinde aus dem Katalog.\n"
            "5) **DIMENSIONS-PARSER (Beispiele)**:\n"
            "   - Platten: \"2600 × 1200 mm\" ⇒ 2,6 m × 1,2 m ⇒ 3,12 m² **pro Platte**.\n"
            "   - Matten: \"6 × 2,3 m\" ⇒ 13,8 m² pro **Stück**.\n"
            "   - Folien/Rollen: \"4 × 5 m\" ⇒ 20 m² pro **Rolle**.\n"
            "   - Kartons: \"1000 Stück\" ⇒ 1000 **Stück** pro **Karton**.\n"
            "6) **AUSWAHL BEI MEHREREN GRÖSSEN**: Wähle die Variante mit minimalem Überhang; bei Gleichstand: weniger Gebinde, danach günstiger €/Basiseinheit.\n"
            "7) **FEHLENDE MENGEN**: Wenn im Anhang menge oder einheit fehlen, setze beide auf null.\n"
            "8) **SORTIERUNG**: 'nr' beginnt bei 1 in Reihenfolge des Anhangs.\n"
            "9) **INVARIANTEN (prüfe gedanklich):**\n"
            "   - Wenn Anhang \"Gipskartonplatte …, menge=10, einheit=Platte\" → Ausgabe MUSS **menge=10, einheit=\"Platte\"** sein (keine Neuberechnung aus 3,12 m²/Platte).\n"
            "   - Wenn Anhang \"Ständerprofil CW 75, 4 m, menge=20, einheit=m\" → Ausgabe MUSS **menge=CEILING(20/4)=5, einheit=\"Stück\"** sein.\n"
            "   - Wenn Anhang \"Schnellbauschrauben …, menge=1000, einheit=Stück\" und Katalog \"1000 Stück\"/Karton → **menge=CEILING(1000/1000)=1, einheit=\"Karton\"**.\n\n"
            "Kontext (KATALOG):\n{context}\n\n"
            "QUESTION (nur den Datenanhang zwischen --- auswerten):\n{question}\n\n"
            "Antwort:"
        ),
    )

    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug
    )

    return chain1, chain2, memory1, prompt2
