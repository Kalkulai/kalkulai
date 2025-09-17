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

    # Prompt 2: Angebots-JSON
    prompt2 = PromptTemplate(
    input_variables=["context","question"],
    template=(
        "Beantworte ausschließlich auf Deutsch.\n"
        "AUSGABEFORMAT (strikt): Ein JSON-Array von Objekten mit Feldern\n"
        "[{\"nr\": number, \"name\": string, \"menge\": number|null, \"einheit\": string|null, \"epreis\": number|null}]\n"
        "- Keine Kommentare, kein Markdown, keine zusätzlichen Felder, kein Text außerhalb des JSON.\n"
        "- Wenn nichts passt: gib [].\n\n"
        "KATALOGREGELN (sehr streng):\n"
        "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen.\n"
        "- Gib die Produktnamen GENAU so zurück, wie sie im KATALOG stehen (inkl. Größen/Einheiten wie \"10 L\", \"750 ml\", \"4x5 m\").\n"
        "- KEINE Synonyme, KEINE Alternativen, KEINE Ersetzungen.\n"
        "- Wenn ein in der Frage genannter Artikel NICHT im KATALOG vorkommt: NICHT ersetzen und NICHT aufnehmen.\n\n"
        "NUTZER-MATERIALIEN VORRANG:\n"
        "- Enthält die QUESTION unter 'Materialien:' eine Liste, dann match diese Einträge streng gegen den KATALOG und übernimm NUR die Treffer – in der Reihenfolge der Nutzerliste.\n"
        "- Falls in der QUESTION zusätzlich eine Mengen-Zusammenfassung (z. B. 'Zusammenfassung der benötigten Materialien') vorkommt, verwende diese Mengen für die gematchten Produkte.\n"
        "- Wenn für einen gematchten Artikel keine Menge eindeutig in der QUESTION steht, setze \"menge\": null und \"einheit\": null (nicht schätzen).\n\n"
        "OHNE NUTZERLISTE:\n"
        "- Wenn keine explizite Materialliste vorliegt, wähle bis zu 5 Katalogprodukte, die zur Frage passen; Mengen dann null/null.\n\n"
        "PREISE:\n"
        "- 'epreis' NUR aus dem KATALOG übernehmen, wenn im Kontext eindeutig vorhanden; sonst epreis=null.\n"
        "- Die Nummerierung 'nr' beginnt bei 1 und folgt der Ausgabe-Reihenfolge.\n\n"
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