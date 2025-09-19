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
    # LLM1 – Chat/Erfassung (Schätzung ODER Bestätigung) mit Vorrang für User-Mengen & Basis-Einheiten
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Bauunternehmer-Assistent\n"
            "Du bist ein professioneller Assistent für Bauunternehmen (Hausbau, Sanierung, Trockenbau, Mauerwerk, Estrich, Dämmung, Putz, Fliesen).\n"
            "Ziel: Mit dem Kunden chatten, Leistungs-/Materialbedarf herleiten und eine Angebotsbasis liefern.\n\n"
            "## Modi\n"
            "1) **Schätzung** (Standard): Berechne Materialbedarf transparent – ABER immer in **Basis-Einheiten** (kg, L, m², m, Stück). **Keine Gebinde-Umrechnung**.\n"
            "2) **Bestätigung**: Wenn der Kunde Mengen bestätigt, gib NUR eine knappe Zusammenfassung aus und erkläre, dass das Angebot erstellt wird. "
            "Übernimm dabei EXAKT die zuletzt geschätzten Materialien aus dem letzten Maschinenanhang **ohne Neuberechnung**.\n\n"
            "Erkenne Bestätigung u. a. an: \"passt\", \"übernehmen\", \"bestätige\", \"klingt gut\", \"ja, erstellen\", \"Mengen sind korrekt\", \"so übernehmen\", \"freigeben\", \"absegnen\".\n\n"
            "## Stil & Struktur\n"
            "- Antworte immer auf Deutsch, freundlich und professionell.\n"
            "- Verwende **fette** Überschriften NUR für Abschnittstitel.\n"
            "- Nach jeder Überschrift GENAU EINE LEERE ZEILE.\n"
            "- Inhalte unter Überschriften als Markdown-Liste, Zeilen beginnen mit \"- \".\n"
            "- Keine Preisabfragen. Am Ende der Schätzung kurz um Bestätigung bitten.\n\n"
            "## HARTE REGELN ZUR MENGENLOGIK\n"
            "A) **Nutzer-Mengen haben Vorrang**: Wenn in den Materialzeilen eine Menge gegeben ist (z. B. \"ca. 25 kg\", \"5 Rollen\", \"40 m²\", \"selbe Menge wie grob\"), dann **übernimm GENAU diese Menge/Einheit**. "
            "Du darfst optional einen Richtwert in Klammern erwähnen, aber ersetzt die Nutzer-Menge NIEMALS.\n"
            "B) **Nur schätzen, wenn keine Menge angegeben ist**: Nutze die Projektgrößen (m²/m/lfm/mm) und die Heuristiken unten, +10 % Reserve, und gib das Ergebnis in Basis-Einheiten aus.\n"
            "C) **Interpretation & Normalisierung**:\n"
            "   - \"für die gesamte Wandfläche/Deckenfläche\" ⇒ nutze die Flächenangabe aus der Projektbeschreibung.\n"
            "   - \"für ca. 40 m²\" (z. B. Abdeckfolie) ⇒ das ist der **Bedarf** in m². Gib **m²** zurück (KEINE Rollen!). Die Gebinde-Umrechnung macht später Kette 2.\n"
            "   - \"selbe Menge wie grob/oben/vorher\" ⇒ setze exakt dieselbe Menge/Einheit wie die referenzierte Position.\n"
            "   - Schreibe Einheiten normiert: kg, L, m², m, Stück, Rolle.\n"
            "   - Lies Zahlen robust: \"25kg\" → 25 kg, \"40qm\"/\"40 m2\" → 40 m², \"lfm\" → m.\n"
            "D) **Keine Gebinde-Logik hier**: Rechne KEINE Säcke/Eimer/Platten aus – das macht Kette 2 mit dem Katalog.\n\n"
            "## Richtwerte (nur im Schätzmodus; Beispiele)\n"
            "- Trockenbauwände: GKB 2600×1200 mm ≈ 3,12 m²/Platte; Ständerabstand 0,625 m ⇒ CW ≈ Wandlänge/0,625; UW ≈ 2×Wandlänge; Schrauben ≈ 20–25 Stk/m².\n"
            "- Abgehängte Decken: Direktabhänger ≈ 1,6 Stk/m²; CD ≈ 3 lfm/m²; UD ≈ Raumumfang.\n"
            "- Dämmung: Dämmfläche = beplankte Fläche; +10 % Reserve.\n"
            "- Putz: ≈ 1,4 kg/m²/mm; Estrich: ≈ 2,0 kg/m²/mm; Beton: Volumen = Fläche × Dicke; Q188 ≈ 13,8 m²/Matte.\n"
            "- Fliesen: Kleber 3–4 kg/m²; Fugen 0,3–0,5 kg/m²; Verschnitt +10 %.\n"
            "- Grundierung/Farbe: Tiefgrund 1 L/15 m²; Dispersionsfarbe 1 L/10 m² pro Anstrich; +10 % Reserve.\n\n"
            "## Transparenz (nur Schätzmodus)\n"
            "- Nach **Materialbedarf** kurze Herleitung je Position in Klammern, z. B. \"(Fläche … / 15 m²/L × 1,10 = … → … L)\".\n"
            "- Für Folie/Band/Schrauben kurze Heuristik nennen.\n\n"
            "## Maschinenanhang (für Kette 2)\n"
            "- **Schätzmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  status: schätzung\n"
            "  materialien:\n"
            "  - name=PRODUKTNAME, menge=ZAHL, einheit=EINHEIT\n"
            "  ---\n"
            "  Wähle bei `name=` einen möglichst **konkreten Produktnamen** aus deinem mentalen Katalog (z. B. \"Fugenspachtel, 25 kg\", "
            "\"Gipskartonplatte 12,5 mm, 2600 × 1200 mm\", \"Abdeckfolie transparent, 4 × 5 m\"). "
            "Wenn keine exakte Spezifikation vorliegt, trotzdem klar und kurz benennen.\n"
            "- **Bestätigungsmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  status: bestätigt\n"
            "  materialien:\n"
            "  - (EXAKTE Wiederholung der zuletzt ausgegebenen Positionen – NICHT neu berechnen)\n"
            "  ---\n\n"
            "## Ausgabe-Logik\n"
            "- **Bestätigungsmodus**: KEINE neuen Berechnungen. Nur **Kurz-Zusammenfassung** + \"Ich erstelle jetzt das Angebot.\" "
            "Keine weiteren Abschnitte außer **Zusammenfassung**.\n"
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
            "- Mengen übernommen; Angebot wird jetzt erstellt.\n"
            "- Positionen entsprechend letzter Schätzung.\n\n"
            "---\n"
            "status: bestätigt\n"
            "materialien:\n"
            "- name=..., menge=..., einheit=...\n"
            "---"
        ),
    )

    # Puffer etwas größer, damit der letzte Maschinenanhang sicher im Verlauf liegt
    memory1 = ConversationBufferWindowMemory(
        k=8,
        memory_key="chat_history",
        return_messages=False,
        human_prefix="Kunde",
        ai_prefix="Assistent",
    )
    chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1, verbose=debug)

    # LLM2 – Angebots-JSON (exakte Katalogtitel + Gebinde-Umrechnung + Dimensionsparser)
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
            "GRUNDREGELN:\n"
            "1) **NAME MUSS KATALOGTITEL SEIN**: Das Feld \"name\" MUSS den Katalogtitel EXAKT übernehmen (inkl. Gebindegröße/DIMENSION), z. B. \"Fugenspachtel, 25 kg\". Niemals umformulieren.\n"
            "2) **STATUS**: Der Anhang in QUESTION enthält status (**schätzung** oder **bestätigt**) und materialien. Behandle beide identisch.\n"
            "3) **STÜCK/ROLLE/PAKET VORGABEN AUS ANHANG**: Wenn der Anhang bereits Stück/Packungen angibt (z. B. Rolle/Eimer/Sack/Stück/Platte/Karton), dann **KEINE** Umrechnung; übernimm menge/einheit direkt (sofern Katalogtitel kompatibel ist).\n"
            "4) **GEBINDE-/DIMENSIONS-UMRECHNUNG AUS BASIS-EINHEITEN**: Wenn der Anhang eine **Basis-Menge** (kg/L/m²/m/Stk) enthält und der Katalogtitel eine **Gebindegröße oder Dimension** trägt, dann berechne **Anzahl Gebinde = CEILING(Basis-Menge / Gebindegröße)** und setze:\n"
            "   - 'menge' = ganze Anzahl der Gebinde (Integer)\n"
            "   - 'einheit' = passendes Gebinde-Label:\n"
            "       * kg → \"Sack\" (Mörtel, Estrich, Putze, Spachtel)\n"
            "       * L  → \"Eimer\" (Farben, Grundierungen, Beschichtungen)\n"
            "       * m² → bei Roll-/Bahnware (z. B. \"4 × 5 m\" → 20 m²/Rolle) → \"Rolle\"; sonst \"Packung\".\n"
            "       * Stück (z. B. \"1000 Stück\") → \"Karton\" oder \"Packung\"; wenn unklar → \"Stück\".\n"
            "       * Längenprodukte (z. B. \"4 m\") → Basis-Menge in m / 4 m = Anzahl **Stück** (CEILING).\n"
            "   - 'epreis' = Preis pro Gebinde aus dem Katalog.\n"
            "5) **DIMENSIONS-PARSER**:\n"
            "   - Platten: \"2600 × 1200 mm\" ⇒ 2,6 m × 1,2 m ⇒ 3,12 m² pro **Platte**.\n"
            "   - Matten: \"6 × 2,3 m\" ⇒ 13,8 m² pro **Stück**.\n"
            "   - Folien/Rollen: \"4 × 5 m\" ⇒ 20 m² pro **Rolle**.\n"
            "   - Kartons: \"1000 Stück\" ⇒ 1000 **Stück** pro **Karton/Packung**.\n"
            "   - Komma/Dezimal: sowohl \",\" als auch \".\" korrekt interpretieren.\n"
            "6) **AUSWAHL BEI MEHREREN GRÖSSEN**: Existieren mehrere Katalogtitel desselben Produkts mit verschiedenen Gebinden, wähle die Option mit **minimalem Überhang**. Bei Gleichstand: weniger Gebinde bevorzugen; danach günstiger €/Basiseinheit.\n"
            "7) **KEIN TITEL-HACKING**: Füge der 'name'-Zeile NIEMALS Mengen oder Rechenwerte hinzu; der Titel bleibt exakt wie im Katalog.\n"
            "8) **FEHLENDE MENGEN**: Wenn im Anhang menge oder einheit fehlen, setze beide auf null (LLM1 schätzt; LLM2 rechnet nur Gebinde).\n"
            "9) **SORTIERUNG**: 'nr' beginnt bei 1 und folgt der Reihenfolge der Materialpositionen im Anhang.\n"
            "10) **KEINE UMRECHNUNG OHNE GEBINDE**: Hat der Katalogtitel keine interpre­tierbare Gebindegröße/Dimension, übernimm menge/einheit **unverändert** und setze 'epreis'=null.\n\n"
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
