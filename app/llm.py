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
                "Regeln:\n"
                "- Antworte NUR als JSON-Array mit Feldern \"nr\",\"name\",\"menge\",\"einheit\",\"epreis\" (Zahlen ohne Währungssymbol).\n"
                "- Wenn mehrere passende Varianten im Kontext stehen, wähle die am BESTEN passende.\n"
                "- Falls Menge nicht explizit im Frage-Text steht, nutze sinnvolle Standardmengen aus dem Kontext (z. B. 1 Gebinde, 1 Sack, 1 m² etc.).\n"
                "- Preise (epreis) IMMER aus dem Kontext übernehmen (ohne Euro-Zeichen).\n"
                "- Keine Kommentare, kein Markdown. Wenn wirklich nichts passt: []\n\n"
                "Kontext:\n{context}\n\n"
                "Frage:\n{question}\n\n"
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