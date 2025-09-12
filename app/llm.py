import os
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory

def create_chat_llm(provider: str, model: str, temperature: float, top_p: float, api_key: str=None, base_url: str=None):
    provider = provider.lower()
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature, top_p=top_p, base_url=base_url)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")

def build_chains(llm1, llm2, retriever, debug=False):
    # Prompt 1
    prompt1 = PromptTemplate(
        input_variables=["chat_history","human_input"],
        template=(
            "# Fliesenleger-Assistent\n"
            "Du bist Fliesenleger-Assistent. Sammle Produktdaten und berechne Fliesenmengen.\n"
            "Regeln: kompakt, Deutsch, 10% Verschnitt addieren (aufgerundet).\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\nKUNDE: {human_input}\n\nANTWORT:"
        )
    )
    memory1 = ConversationBufferWindowMemory(k=4, memory_key="chat_history", return_messages=False, human_prefix="Kunde", ai_prefix="Assistent")
    chain1 = LLMChain(llm=llm1, prompt=prompt1, memory=memory1, verbose=debug)

    # Prompt 2
    prompt2 = PromptTemplate(
        input_variables=["context","question"],
        template=(
            "Beantworte ausschließlich auf Deutsch.\n"
            "Regeln: Nur Kontext, Produkte als JSON-Array mit Feldern \"nr\",\"name\",\"menge\",\"einheit\",\"epreis\".\n"
            "Keine Kommentare/Markdown. Wenn nichts passt: []\n\n"
            "Kontext:\n{context}\n\nFrage:\n{question}\n\nAntwort:"
        )
    )
    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug
    )

    return chain1, chain2, memory1
