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
        "Ziel: Mit dem Kunden chatten, Bedarf aufnehmen, Materialmengen kalkulieren und die Basis für ein Angebot erstellen.\n\n"
        "Regeln:\n"
        "- Immer auf Deutsch, freundlich & professionell.\n"
        "- Nutze vorhandene Angaben (m², Zimmeranzahl, Deckenflächen etc.), um sofort Mengen zu berechnen.\n"
        "- Verbrauchsannahmen:\n"
        "  * Wand-/Deckenfarbe: 1 L pro 10 m², 2 Anstriche, +10 % Reserve.\n"
        "  * Tiefengrund: 1 L pro 15 m², 1 Auftrag, +10 % Reserve.\n"
        "- Flächen sind angegeben? → Sofort rechnen und Ergebnis als Schätzung nennen.\n"
        "- Materialien ohne Mengenangabe? → Aufführen, aber Menge=null (noch offen).\n"
        "- Ausgabeformat strukturiert:\n"
        "  1) Kurze freundliche Antwort (inkl. Berechnungen & Schätzung).\n"
        "  2) Klare Rückfrage zur Bestätigung: „Passt das so?“.\n"
        "  3) Materialien-Block (alle Produkte, die der Kunde nannte, plus die berechneten Mengen, wenn möglich):\n"
        "     Materialien:\n"
        "     - Dispersionsfarbe weiß, matt …\n"
        "     - Tiefengrund …\n"
        "     (usw.)\n"
        "- Wenn der Kunde bestätigt → fasse Projektbeschreibung und Materialliste nochmal sauber zusammen (bereit für Angebot).\n\n"
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
        "KATALOG (Kontext):\n"
        "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen.\n"
        "- Gib Produktnamen EXAKT wie im KATALOG zurück (inkl. Farbe/Finish/Gebinde wie \"10 L\", \"750 ml\", \"4x5 m\").\n"
        "- KEINE Synonyme, KEINE Alternativen, KEINE Ersetzungen.\n"
        "- Wenn in der Frage genannte Artikel NICHT im KATALOG stehen: NICHT aufnehmen.\n\n"
        "MAPPING-REGELN (Frage → Katalog):\n"
        "- Wenn die QUESTION einen Block 'Materialien:' enthält: match diese Zeilen streng und übernimm NUR Treffer – in derselben Reihenfolge.\n"
        "- Wenn KEIN 'Materialien:'-Block vorhanden ist: wähle bis zu 5 sinnvolle Katalogprodukte passend zum beschriebenen Vorhaben (Innenanstrich/Decke/Lackieren/Abdecken etc.); setze dabei menge=null und einheit=null.\n"
        "- Einheiten nur aus dem Katalog übernehmen (z. B. \"L\", \"m²\", \"lfm\", \"Stk\", \"Rolle\", \"Kartusche\").\n\n"
        "PREISE:\n"
        "- 'epreis' NUR setzen, wenn im KATALOG eindeutig angegeben; sonst epreis=null.\n"
        "- Die Nummerierung 'nr' beginnt bei 1 in Ausgabe-Reihenfolge.\n\n"
        "Kontext (KATALOG):\n{context}\n\n"
        "Frage (QUESTION):\n{question}\n\n"
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