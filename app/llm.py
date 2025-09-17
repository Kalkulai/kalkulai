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
    # Prompt 1: Chat/Erfassung (dein alter Prompt)
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Fliesenleger-Assistent\n"
            "Du bist Fliesenleger-Assistent. Sammle Produktdaten und berechne Fliesenmengen.\n"
            "Regeln: kompakt, Deutsch, 10% Verschnitt addieren (aufgerundet).\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\nKUNDE: {human_input}\n\nANTWORT:"
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

    # Prompt 2: Angebots-JSON (nur Template ersetzt)
    prompt2 = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "Beantworte ausschließlich auf Deutsch.\n"
            "AUSGABEFORMAT (strikt): Ein JSON-Array von Objekten mit Feldern\n"
            "[{\"nr\": number, \"name\": string, \"menge\": number|null, \"einheit\": string|null, \"epreis\": number|null}]\n"
            "- Keine Kommentare, kein Markdown, keine zusätzlichen Felder, keine Texte außerhalb des JSON.\n"
            "- Wenn nichts passt: gib [].\n\n"
            "KATALOGREGELN (sehr streng):\n"
            "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen.\n"
            "- Gib die Produktnamen GENAU so zurück, wie sie im KATALOG stehen (inkl. Größen/Einheiten wie \"10 L\", \"750 ml\", \"4x5 m\").\n"
            "- Case-insensitive Matching erlaubt, aber die AUSGABE MUSS exakt dem Katalognamen entsprechen.\n"
            "- KEINE Synonyme, KEINE Alternativen, KEINE Halluzinationen.\n"
            "- Wenn ein in der Frage genannter Artikel NICHT im KATALOG vorkommt: NICHT ersetzen, einfach weglassen.\n\n"
            "VERHALTEN BEI NUTZERLISTE:\n"
            "- Wenn die Frage unter 'Materialien:' eine Liste enthält, versuche, jeden Eintrag streng gegen den KATALOG zu matchen und gib NUR die gematchten zurück.\n"
            "- Reihenfolge beibehalten wie in der Nutzerliste.\n"
            "- Keine automatischen Ergänzungen.\n\n"
            "VERHALTEN OHNE NUTZERLISTE:\n"
            "- Wenn keine explizite Materialliste genannt ist, wähle bis zu 5 Katalogprodukte, die am besten zur Frage passen.\n\n"
            "MENGEN & PREISE:\n"
            "- Wenn der Nutzer eine Menge/Einheit nennt, übernimm sie; sonst setze menge=null und einheit=null (NICHT schätzen).\n"
            "- 'epreis' NUR aus dem KATALOG übernehmen, falls im Kontext eindeutig angegeben; ansonsten epreis=null.\n"
            "- Nummerierung 'nr' beginnt bei 1 und zählt hoch.\n\n"
            "Kontext (KATALOG – ein Produkt pro Zeile):\n"
            "{context}\n\n"
            "Frage:\n"
            "{question}\n\n"
            "Antwort:"
        )
    )

    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug
    )

    return chain1, chain2, memory1, prompt2