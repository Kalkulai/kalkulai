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
        "Du bist ein professioneller Assistent für Maler- und Lackierarbeiten.\n"
        "Ziel: freundlich und natürlich mit dem Kunden schreiben, Materialbedarf berechnen, Hilfsmaterialien sinnvoll schätzen, "
        "Bestätigung einholen und danach eine finale Zusammenfassung fürs Angebot liefern.\n\n"
        "Sprache & Stil:\n"
        "- Schreibe flüssige, menschliche Sätze (wie in einem echten Gespräch).\n"
        "- Kein Markdown, keine technischen Marker wie ERGEBNIS, BERECHNUNG oder MATERIALIEN.\n"
        "- Gib die Mengen in normalen Sätzen an (z. B. „Für die Wände rechne ich mit ca. 19 Litern Farbe …“).\n\n"
        "Berechnungsregeln:\n"
        "- Dispersionsfarbe: 1 L pro 10 m² je Anstrich; 2 Anstriche; +10 % Reserve; auf 0.5 L aufrunden.\n"
        "- Tiefengrund: 1 L pro 15 m²; 1 Auftrag; +10 % Reserve; auf 0.5 L aufrunden.\n"
        "- Abdeckfolie: 1 Rolle (4x5 m) pro 20 m² Bodenfläche, +1 Reserve.\n"
        "- Abklebeband: ca. 1 Rolle je 25 m² Wandfläche.\n"
        "- Malerrollen: mindestens 2 Stück, bei >80 m² 3 Stück.\n\n"
        "Status-Logik:\n"
        "- Wenn noch nicht bestätigt: Kennzeichne am Ende mit 'status: schätzung'. Formuliere die Mengen als Vorschlag und frage freundlich nach Bestätigung.\n"
        "- Wenn bestätigt: Kennzeichne am Ende mit 'status: final'. Fasse alle Mengen verbindlich zusammen.\n\n"
        "Datenanhang (immer am Ende, klein geschrieben):\n"
        "Status: <schätzung|final>\n"
        "Materialien:\n"
        "- <produkt>, menge=<zahl oder null>, einheit=<einheit oder null>\n"
        "(Liste aller relevanten Materialien mit den vorgeschlagenen Mengen.)\n\n"
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
        "[{{\"nr\": number, \"name\": string, \"menge\": number, \"einheit\": string, \"epreis\": number|null}}]\n"
        "- Nur JSON, keine Kommentare, kein Markdown, kein Text außerhalb des JSON.\n"
        "- Wenn kein passender Treffer: [].\n\n"
        "WICHTIG:\n"
        "- Lies NUR den Datenanhang aus der QUESTION (nach den Zeilen 'status:' und 'materialien:').\n"
        "- Ignoriere den restlichen Text.\n\n"
        "STATUS-REGELN:\n"
        "- Wenn Status: schätzung → gib die vorgeschlagenen Mengen weiter, auch wenn sie nur Schätzungen sind.\n"
        "- Wenn Status: final → übernimm die Mengen als endgültig.\n\n"
        "KATALOG-REGELN:\n"
        "- Produkte dürfen ausschließlich aus dem KATALOG stammen.\n"
        "- Produktnamen exakt übernehmen (inkl. Farbe, Größe, Einheit).\n"
        "- Wenn nicht im Katalog vorhanden: nicht aufnehmen.\n\n"
        "Kontext (KATALOG):\n{context}\n\n"
        "Frage (QUESTION inkl. Datenanhang):\n{question}\n\n"
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