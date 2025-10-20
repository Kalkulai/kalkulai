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


def build_chains(llm1, llm2, retriever, debug: bool = False, existing_memory: ConversationBufferWindowMemory | None = None):
    """
    Baut Kette 1 (Chat/Erfassung mit Memory) und Kette 2 (Retrieval + PromptTemplate für Angebots-JSON).
    - existing_memory: Wenn übergeben, wird diese Memory weiterverwendet (Session-Fall).
                       Wenn None (z. B. nach /api/session/reset), wird eine frische Memory erzeugt.
    Rückgabe: chain1, chain2, memory1, prompt2
    """

    # ---------- LLM1 – Chat/Erfassung ----------
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
            "## Kontextschutz & Eingabeprüfung\n"
            "- Arbeite ausschließlich mit Informationen aus dem `GESPRÄCHSVERLAUF` und dem aktuellen `KUNDE`-Beitrag. Nutze keine Annahmen aus Vorwissen oder Standardfällen.\n"
            "- Prüfe vor jeder Antwort, ob bereits technische oder projektbezogene Angaben vorliegen (z. B. Gewerke, Leistungen, Flächen, Mengen, Materialien, Besonderheiten).\n"
            "- Falls noch keine verwertbaren Angaben vorliegen und der Kunde ein Angebot oder eine Schätzung wünscht, antworte klar: \"Es liegen noch keine Angebotsdaten vor. Bitte beschreiben Sie zuerst das Projekt (Leistung, Fläche, Material, Besonderheiten).\"\n"
            "- Falls die Eingabe keinen Bezug zu Bauleistungen oder Angebotsinhalten hat (Smalltalk, irrelevante Fragen), erkläre freundlich, dass nur projektbezogene Angaben verarbeitet werden können, und fordere zur Beschreibung des Vorhabens auf.\n"
            "- Führe keine Berechnungen oder Materiallisten aus, solange keine relevanten Angaben erfasst wurden.\n\n"
            "## HARTE REGELN ZUR MENGENLOGIK\n"
            "A) **Nutzer-Mengen haben Vorrang** …\n"
            "E) **Keine Gebinde-Logik in LLM1** …\n\n"
            "## Richtwerte …\n\n"
            "## Transparenz …\n\n"
            "## Maschinenanhang (für Kette 2)\n"
            "- **Schätzmodus** …\n"
            "- **Bestätigungsmodus** …\n\n"
            "## Ausgabe-Logik …\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\n"
            "KUNDE: {human_input}\n\n"
            "ANTWORT – verwende je nach Modus diese Struktur:\n\n"
            "### Schätzung (Beispiel)\n"
            "**Projektbeschreibung**\n"
            "- …\n\n"
            "**Leistungsdaten**\n"
            "- …\n\n"
            "**Materialbedarf**\n"
            "- …\n\n"
            "Bitte bestätigen Sie die Mengen …\n\n"
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

    # Memory: bestehende wiederverwenden oder frische erzeugen (wichtig für Reset)
    memory1 = existing_memory or ConversationBufferWindowMemory(
        k=8,
        memory_key="chat_history",
        return_messages=False,
        human_prefix="Kunde",
        ai_prefix="Assistent",
    )

    chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1, verbose=debug)

    # ---------- LLM2 – Angebots-JSON (nur PromptTemplate + CRChain) ----------
    prompt2 = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "Antworte ausschließlich auf Deutsch.\n"
            "GIB AUSSCHLIESSLICH EINEN JSON-ARRAY ZURÜCK …\n"
            "Kontext (KATALOG):\n{context}\n\n"
            "QUESTION (nur den Datenanhang zwischen --- auswerten):\n{question}\n\n"
            "Antwort:"
        ),
    )

    # Wir bauen chain2 weiterhin, auch wenn du in main.py direkt format+invoke nutzt.
    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug,
    )

    return chain1, chain2, memory1, prompt2