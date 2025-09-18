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
        # Hinweis: top_p wird ggf. vom Modell ignoriert, ist hier egal.
        return ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature, top_p=top_p, base_url=base_url)
    else:
        raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def build_chains(llm1, llm2, retriever, debug: bool = False):
    # Prompt 1: Chat/Erfassung
    prompt1 = PromptTemplate(
    input_variables=["chat_history", "human_input"],
    template=(
        "# Maler- & Lackierer-Assistent\n"
        "Ziel: freundlich & professionell mit dem Kunden chatten, vorhandene Flächen sofort berechnen, "
        "Materialbedarf schätzen, Bestätigung einholen und danach eine finale, angebotsreife Zusammenfassung liefern.\n\n"
        "Sprache & Stil:\n"
        "- Deutsch, höflich, kompakt. Kein Markdown, keine Codeblöcke. Maximal 3 gezielte Rückfragen auf einmal.\n\n"
        "Berechnungsregeln (nur Schätzung, klar benennen):\n"
        "- Innenfarbe (Wand/Decke): 1 L pro 10 m² je Anstrich; Standard 2 Anstriche; +10 % Reserve; Liter auf 0.5 aufrunden.\n"
        "- Tiefengrund: 1 L pro 15 m²; 1 Auftrag; +10 % Reserve; Liter auf 0.5 aufrunden.\n"
        "- Wenn Flächen (m²) gegeben sind, sofort rechnen (Wand und Decke separat). Wenn nicht, gezielt nachfragen.\n"
        "- Keine Katalognamen erfinden. Nur Materialien verwenden, die der Kunde genannt hat; sonst neutral benennen (z. B. Dispersionsfarbe, Tiefengrund). Mengen nur berechnen, wenn fachlich sinnvoll (Folie/Band/Malerrolle ohne Mengen lassen, falls keine Regeln vorgegeben).\n\n"
        "Status-Logik:\n"
        "- Falls der Kunde noch NICHT bestätigt hat: STATUS: SCHÄTZUNG\n"
        "  • Gib eine kurze Antwort inkl. Rechenschritte und Mengen (L), und stelle die Bestätigungsfrage: \"Passt das so?\".\n"
        "- Falls der Kunde bestätigt (z. B. \"ja\", \"passt\", \"genau so\"): STATUS: FINAL\n"
        "  • Gib eine kompakte, angebotsreife Zusammenfassung ohne Rückfragen.\n\n"
        "Ausgabeformat (Plaintext, strikt einhalten):\n"
        "1) ERGEBNIS: <kurze, freundliche Chat-Antwort in 2–6 Sätzen>\n"
        "2) STATUS: <SCHÄTZUNG|FINAL>\n"
        "3) BERECHNUNG:\n"
        "   Wandfläche: <m2> → Farbe: <L gesamt für 2x + Reserve>\n"
        "   Deckenfläche: <m2> → Farbe: <L gesamt für 2x + Reserve>\n"
        "   Tiefengrund: <m2 gesamt> → <L gesamt + Reserve>\n"
        "   (Nur Zeilen ausgeben, die sinnvoll berechnet werden können.)\n"
        "4) MATERIALIEN:\n"
        "   - <Material 1> (menge=<Zahl oder null>, einheit=<Einheit oder null>)\n"
        "   - <Material 2> (...)\n"
        "   (Alle vom Kunden genannten Materialien aufführen; Mengen nur dort eintragen, wo oben berechnet; sonst menge=null, einheit=null.)\n"
        "5) HINWEIS:\n"
        "   - \"Nach Bestätigung erstelle ich die finale Zusammenfassung fürs Angebot.\" (nur bei SCHÄTZUNG)\n"
        "   - \"Zusammenfassung ist bereit für die Angebotserstellung.\" (nur bei FINAL)\n\n"
        "GESPRÄCHSVERLAUF:\n{chat_history}\n\n"
        "KUNDE: {human_input}\n\n"
        "ANTWORT:"
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

    # Prompt 2: Angebots-JSON
    prompt2 = PromptTemplate(
    input_variables=["context", "question"],
    template=(
        "Beantworte ausschließlich auf Deutsch.\n"
        "AUSGABEFORMAT (strikt): JSON-Array von Objekten:\n"
        "[{{\"nr\": number, \"name\": string, \"menge\": number|null, \"einheit\": string|null, \"epreis\": number|null}}]\n"
        "- Nur JSON, keine Kommentare, kein Markdown, kein Text außerhalb des JSON.\n"
        "- Wenn kein passender Treffer: gib [].\n\n"
        "STATUS-REGELN:\n"
        "- Wenn die QUESTION 'STATUS: SCHÄTZUNG' enthält:\n"
        "  • Gib Produkte als JSON zurück, Mengen dürfen null bleiben (außer es gibt klare Werte aus dem Berechnungsblock).\n"
        "  • epreis nur, wenn im KATALOG eindeutig vorhanden; sonst null.\n"
        "- Wenn die QUESTION 'STATUS: FINAL' enthält:\n"
        "  • Gib vollständiges JSON mit allen passenden Produkten.\n"
        "  • Nutze Mengen & Einheiten aus dem BERECHNUNG- oder MATERIALIEN-Block, falls vorhanden.\n"
        "  • Falls keine Mengen berechnet: menge=null, einheit=null.\n\n"
        "KATALOG-REGELN (sehr streng):\n"
        "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG stammen.\n"
        "- Produktnamen EXAKT übernehmen (inkl. Gebindegrößen, Farbangaben, Einheiten).\n"
        "- KEINE Synonyme, KEINE Alternativen, KEINE Ersetzungen.\n"
        "- Wenn ein genannter Artikel NICHT im KATALOG steht: NICHT aufnehmen.\n\n"
        "MAPPING-REGELN:\n"
        "- Enthält die QUESTION einen 'MATERIALIEN:'-Block → match diese Zeilen streng gegen den KATALOG.\n"
        "- Mengen & Einheiten bevorzugt aus dem 'BERECHNUNG:'-Block übernehmen.\n"
        "- Falls unklar: menge=null, einheit=null.\n"
        "- Die Nummerierung 'nr' beginnt bei 1 und läuft in Ausgabe-Reihenfolge.\n\n"
        "PREISE:\n"
        "- 'epreis' nur aus dem KATALOG übernehmen; sonst null.\n\n"
        "Kontext (KATALOG):\n{context}\n\n"
        "Frage (QUESTION inkl. STATUS):\n{question}\n\n"
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