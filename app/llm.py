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
    # Prompt 1: Chat/Erfassung – Bauunternehmen (Schätzung ODER Bestätigung)
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Bauunternehmer-Assistent\n"
            "Du bist ein professioneller Assistent für Bauunternehmen (Hausbau, Sanierung, Trockenbau, Mauerwerk, Estrich, Dämmung, Putz, Fliesen).\n"
            "Ziel: Mit dem Kunden chatten, Leistungs-/Materialbedarf herleiten und Angebotsbasis liefern.\n\n"
            "## Modi\n"
            "1) **Schätzung** (Standard): Berechne Materialbedarf transparent.\n"
            "2) **Bestätigung**: Wenn der Kunde Mengen bestätigt, gib NUR eine knappe Zusammenfassung aus und erkläre, dass das Angebot erstellt wird. "
            "Übernimm dabei EXAKT die zuletzt geschätzten Materialien aus dem letzten Maschinenanhang im Gesprächsverlauf **ohne Neuberechnung**.\n\n"
            "Erkenne **Bestätigung** u. a. an Formulierungen wie: \"passt\", \"bestätige\", \"Mengen übernehmen\", \"klingt gut\", "
            "\"ja, erstellen\", \"Mengen sind korrekt\", \"so übernehmen\", \"freigeben\", \"absegnen\".\n\n"
            "## Stil & Struktur\n"
            "- Antworte immer auf Deutsch, freundlich und professionell.\n"
            "- Verwende **fette** Überschriften NUR für Abschnittstitel.\n"
            "- Nach jeder Überschrift GENAU EINE LEERE ZEILE.\n"
            "- Inhalte unter Überschriften als Markdown-Liste: Zeilen beginnen mit \"- \".\n"
            "- Keine Preisabfragen. Am Ende der Schätzung kurz um Bestätigung bitten.\n\n"
            "## Richtwerte (Heuristiken, nur im Schätzmodus verwenden)\n"
            "- Trockenbauwände: Plattenbedarf = Wandfläche / 3,12 m²; Ständerabstand 0,625 m ⇒ CW ≈ Wandlänge/0,625; UW ≈ 2×Wandlänge; Schrauben ≈ 20–25 Stk/m².\n"
            "- Abgehängte Decken: Direktabhänger ≈ 1,6 Stk/m²; CD ≈ 3 lfm/m²; UD ≈ Raumumfang.\n"
            "- Dämmung: Dämmfläche = beplankte Fläche; +10 % Reserve.\n"
            "- Putz: ≈ 1,4 kg/m²/mm; Estrich: ≈ 2,0 kg/m²/mm; Beton: Volumen = Fläche × Dicke; Q188 ≈ 13,8 m²/Matte.\n"
            "- Fliesen: Kleber 3–4 kg/m²; Fugen 0,3–0,5 kg/m²; Verschnitt +10 %.\n"
            "- Grundierung/Farbe: Tiefgrund 1 L/15 m²; Dispersionsfarbe 1 L/10 m² pro Anstrich; +10 % Reserve.\n\n"
            "## Transparenz (nur Schätzmodus)\n"
            "- Nach **Materialbedarf** kurz die Herleitung je Position in Klammern, z. B. \"(Fläche … / 3,12 × 1,05 = … → …)\".\n"
            "- Für Folien/Bänder/Schrauben kurze Heuristik nennen.\n\n"
            "## Maschinenanhang (für Kette 2)\n"
            "- **Schätzmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  status: schätzung\n"
            "  materialien:\n"
            "  - name=PRODUKTNAME, menge=..., einheit=...\n"
            "  ---\n"
            "  **Wichtig:** Trage bei `name=` den **konkreten Produktnamen** ein, inkl. wesentlicher Spezifikation aus deiner Liste "
            "(z. B. \"Gipskartonplatte 12,5 mm, 2600 × 1200 mm\", \"Ständerprofil CW 75, 4 m\", \"Schnellbauschrauben, 1000 Stück, 3,5 × 35 mm\", "
            "\"Fugenspachtel, 25 kg\", \"Mineralwolle Klemmfilz 120 mm\").\n"
            "- **Bestätigungsmodus**: Am Ende IMMER:\n"
            "  ---\n"
            "  status: bestätigt\n"
            "  materialien:\n"
            "  - (EXAKTE Wiederholung der zuletzt geschätzten Positionen mit name=…, menge=…, einheit=… – NICHT neu berechnen)\n"
            "  ---\n\n"
            "## Ausgabe-Logik\n"
            "- **Wenn Bestätigungsmodus aktiv ist**: KEINE neuen Berechnungen. Gib nur **Kurz-Zusammenfassung** und Hinweis \"Ich erstelle jetzt das Angebot.\" "
            "Keine zusätzlichen Abschnitte außer einer kleinen **Zusammenfassung**.\n"
            "- **Sonst (Schätzung)**: Projektbeschreibung, Leistungsdaten, Materialbedarf + Bitte um Bestätigung.\n\n"
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
            "- Trockenbauplatten: ... ( ... )\n"
            "- Profile/Verbinder/Schrauben: ... ( ... )\n"
            "- Dämmung: ... ( ... )\n"
            "- Putz/Mörtel/Estrich/Beton: ... ( ... )\n"
            "- Grundierung/Abdichtung/Gewebe: ... ( ... )\n"
            "- Sonstiges Zubehör: ... ( ... )\n\n"
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

    # größerer Puffer, damit der letzte Maschinenanhang sicher im Verlauf liegt
    memory1 = ConversationBufferWindowMemory(
        k=8,
        memory_key="chat_history",
        return_messages=False,
        human_prefix="Kunde",
        ai_prefix="Assistent",
    )
    chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1, verbose=debug)

    # Prompt 2: Angebots-JSON (Katalogzwang + Gebinde-/Packgrößen-Logik)
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
            "WICHTIG:\n"
            "- Die QUESTION enthält einen Datenanhang zwischen --- Blöcken. Analysiere NUR diesen Datenanhang (status/materialien). Alles andere ignorieren.\n"
            "- Status kann **schätzung** ODER **bestätigt** sein; verarbeite beide identisch.\n"
            "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen. Produktnamen EXAKT übernehmen (inkl. Größe/Einheit wie \"10 L\", \"25 kg\", \"6×2,3 m\", \"1000 Stk\").\n"
            "- Keine Synonyme/Alternativen. Nicht im Katalog = nicht aufnehmen.\n"
            "- Mengen/Einheiten aus dem Anhang übernehmen; fehlen sie: menge=null, einheit=null.\n"
            "- 'epreis' nur setzen, wenn im KATALOG eindeutig vorhanden; sonst null.\n"
            "- 'nr' beginnt bei 1 und folgt der Ausgabe-Reihenfolge.\n"
            "- **Gebinde-/Packgrößen-Logik:** Falls der KATALOG-Name eine Pack-/Gebindegröße enthält (z. B. \"10 L\", \"25 kg\", \"50 m²\", \"6×2,3 m\", \"1000 Stk\"), und der Datenanhang eine Gesamtmenge in Basis-Einheiten angibt, dann:\n"
            "  1) Anzahl Gebinde = CEILING(Gesamtmenge / Gebindegröße).\n"
            "  2) Setze 'menge' = ganze Anzahl der Gebinde (Integer) und 'einheit' = passende Stück-Einheit (z. B. \"Sack\" für kg, \"Eimer\" für L, \"Platte\" für Stück, \"Rolle\"/\"Packung\" für m²-Rollen, sonst \"Stück\").\n"
            "  3) 'epreis' = Preis pro Gebinde aus dem KATALOG.\n"
            "  4) Wenn der Datenanhang bereits Stück/Packungen passend zum Katalog angibt, NICHT umrechnen.\n"
            "- Bei mehreren passenden Katalogeinträgen mit unterschiedlichen Gebindegrößen: wähle die, die am besten zur Schätzung passt (wenig Überhang).\n\n"
            "Kontext (KATALOG):\n{context}\n\n"
            "QUESTION (nur zur Info; werte NUR den Datenanhang zwischen --- aus):\n{question}\n\n"
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
