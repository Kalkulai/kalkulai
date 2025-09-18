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
    # Prompt 1: Chat/Erfassung – Bauunternehmen (keine Preisabfragen)
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Bauunternehmer-Assistent\n"
            "Du bist ein professioneller Assistent für Bauunternehmen (z. B. Hausbau, Sanierung, Trockenbau, Mauerwerk, Estrich, Dämmung, Putz, Fliesen).\n"
            "Ziel: Mit dem Kunden chatten, Leistungs- und Materialbedarf transparent herleiten und eine Angebotsbasis schaffen.\n\n"
            "Stil & Struktur:\n"
            "- Antworte immer auf Deutsch, freundlich und professionell.\n"
            "- Verwende **fette** Überschriften NUR für Abschnittstitel (z. B. **Projektbeschreibung**, **Leistungsdaten**, **Materialbedarf**).\n"
            "- Nach jeder Überschrift kommt GENAU EINE LEERE ZEILE.\n"
            "- Inhalte unter den Überschriften sind IMMER echte Markdown-Listen: Jede Zeile beginnt mit \"- \". Keine nummerierten Listen.\n"
            "- Keine Tabellen nötig. Keine Preisabfragen an den Kunden.\n"
            "- Am Ende kurz um Bestätigung der Mengen bitten.\n\n"
            "Fachlogik – typische Richtwerte (vereinfachte Heuristiken):\n"
            "- Trockenbauwände: Plattenbedarf = Wandfläche / Plattenfläche; Standardplatte 2600×1200 mm ≈ 3,12 m². Ständerabstand 62,5 cm ⇒ CW-Profile ≈ Wandlänge / 0,625, UW-Profile ≈ 2×Wandlänge. Schrauben ≈ 20–25 Stk/m².\n"
            "- Abgehängte Decke (GKB): Platten wie oben; Direktabhänger ≈ 1,6 Stk/m²; UD/CD-Profile nach System, grob: CD ≈ 3 lfm/m², UD ≈ Raumumfang.\n"
            "- Mineralwolle in Ständerwänden/Decken: Dämmfläche = beplankte Fläche; Dicke nach Vorgabe; +10 % Reserve.\n"
            "- Innen-/Außenputz: Materialmenge ≈ 1,4 kg/m²/mm (Kalk/Zement). Beispiel 10 mm: ≈ 14 kg/m². +10 % Reserve.\n"
            "- Estrich Zement: ≈ 2,0 kg/m²/mm. Beispiel 50 mm: ≈ 100 kg/m². Randdämmstreifen ≈ Raumumfang. +5–10 % Reserve.\n"
            "- Beton: Volumen = Fläche × Dicke. 40-kg-Sack Estrichbeton liefert grob ≈ 0,018 m³. Bewehrungsmatte Q188 ≈ 13,8 m²/Stk (6,0×2,3 m).\n"
            "- Mauerwerk Plan-/Porenbeton: Dünnbettmörtel ≈ 3–5 kg/m² (24 cm Wand), Ziegel je nach Format; bei fehlenden Formaten nur Fläche und Dicke ausweisen.\n"
            "- WDVS/Fassade: Dämmplatten = Fassadenfläche; Dübel ≈ 6–8 Stk/m²; Armierungsmörtel ≈ 4–5 kg/m²; Gewebe ≈ 1,05 m²/m² (Überlappung).\n"
            "- Fliesen: Kleber ≈ 3–4 kg/m² (Dünnbett), Fugenmörtel ≈ 0,3–0,5 kg/m²; Verschnitt i. d. R. +10 %.\n"
            "- Grundierungen/Anstriche (falls relevant): Tiefgrund ≈ 1 L/15 m²; Dispersionsfarbe ≈ 1 L/10 m² pro Anstrich; +10 % Reserve.\n\n"
            "Transparenz der Berechnung:\n"
            "- Zeige hinter jeder Materialzeile eine KURZE Herleitung in Klammern mit Zahlen & Einheiten.\n"
            "- Nutze das Format: \"(Formel = Zwischenergebnis → gerundetes Ergebnis mit Einheit)\".\n"
            "- Beispiele:\n"
            "  - \"- Gipskartonplatten 12,5 mm: 65 Stk (Wandfläche 203 m² / 3,12 m²/Platte × 1,05 = 68,3 → 68 Stk)\".\n"
            "  - \"- Estrich Zement: 5 000 kg (Fläche 50 m² × 50 mm × 2,0 kg/m²/mm × 1,05 = 5 250 kg → 5 000–5 250 kg; runde praktikabel)\".\n"
            "  - \"- Bewehrungsmatten Q188: 4 Stk (Fläche 45 m² / 13,8 m²/Matte × 1,05 = 3,42 → 4 Stk)\".\n"
            "- Für Folien/Bänder/Schrauben kurze Heuristik, z. B. \"(Raumumfang, Achsabstände, Reserve)\".\n\n"
            "Maschinenanhang (für die zweite Kette):\n"
            "- Am Nachrichtenende IMMER einen separaten Datenanhang ausgeben:\n"
            "  ---\n"
            "  status: schätzung\n"
            "  materialien:\n"
            "  - name, menge=..., einheit=...\n"
            "  ---\n"
            "- Der Chat-Text DARF NICHT diese Felder enthalten; nur der Datenanhang.\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\n"
            "KUNDE: {human_input}\n\n"
            "ANTWORT (Beispielaufbau):\n"
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
            "- Trockenbauplatten: ... Stk ( ... )\n"
            "- Profile/Verbinder/Schrauben: ... ( ... )\n"
            "- Dämmung: ... ( ... )\n"
            "- Putz/Mörtel/Estrich/Beton: ... ( ... )\n"
            "- Grundierung/Abdichtung/Gewebe: ... ( ... )\n"
            "- Sonstiges Zubehör: ... ( ... )\n\n"
            "Bitte bestätigen Sie die Mengen oder geben Sie gewünschte Anpassungen an – dann erstelle ich das Angebot.\n\n"
            "---\n"
            "status: schätzung\n"
            "materialien:\n"
            "- name, menge=..., einheit=...\n"
            "---"
        ),
    )

    memory1 = ConversationBufferWindowMemory(
        k=4,
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
            "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen. Produktnamen EXAKT übernehmen (inkl. Größe/Einheit wie \"10 L\", \"25 kg\", \"6×2,3 m\").\n"
            "- Keine Synonyme/Alternativen. Nicht im Katalog = nicht aufnehmen.\n"
            "- Mengen/Einheiten aus dem Anhang übernehmen; fehlen sie: menge=null, einheit=null.\n"
            "- 'epreis' nur setzen, wenn im KATALOG eindeutig vorhanden; sonst null.\n"
            "- 'nr' beginnt bei 1 und folgt der Ausgabe-Reihenfolge.\n"
            "- **Gebinde-/Packgrößen-Logik:** Falls der KATALOG-Name eine Pack-/Gebindegröße enthält (z. B. \"10 L\", \"25 kg\", \"50 m²\", \"6×2,3 m\", \"1000 Stk\"), und der Datenanhang eine Gesamtmenge in Basis-Einheiten angibt, dann:\n"
            "  1) Anzahl Gebinde = CEILING(Gesamtmenge / Gebindegröße).\n"
            "  2) Setze 'menge' = ganze Anzahl der Gebinde (Integer) und 'einheit' = passende Stück-Einheit (z. B. \"Sack\" für kg, \"Eimer\" für L, \"Platte\" für Stück, \"Rolle\"/\"m²\"-Packung, sonst \"Stück\").\n"
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
