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
        "Ziel: freundlich & professionell mit dem Kunden chatten, Bedarf klären, Maße/Umfang erfassen.\n"
        "Regeln:\n"
        "- Deutsch, kompakt, maximal 3 gezielte Rückfragen auf einmal.\n"
        "- KEIN Markdown, keine Codeblöcke.\n"
        "- Falls Maße fehlen: höflich nachfragen (z. B. Raumlänge/-breite/-höhe, Türen/Fenster, Decken ja/nein).\n"
        "- Rechen-Defaults nur nennen, nicht schätzen: Standardraumhöhe 2.60 m; 2 Anstriche Innen; Reserve ~10%.\n"
        "- KEINE Produktempfehlungen und KEINE Katalognamen erfinden.\n"
        "- Wenn der Kunde konkrete Produkte/Marken nennt, ZITIERE sie wörtlich.\n\n"
        "Ausgabeformat (Plaintext):\n"
        "1) Kurze Antwort an den Kunden (Zusammenfassung + nächste 1–3 Fragen).\n"
        "2) Falls der Kunde explizit Artikel nennt, hänge einen Block an:\n"
        "   Materialien:\n"
        "   <eine Zeile pro genannter Position, wörtlich zitiert, optional mit Menge/Einheit>\n"
        "   (Nur ausgeben, wenn der Kunde wirklich konkrete Positionen genannt hat!)\n\n"
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