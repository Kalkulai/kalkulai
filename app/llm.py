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

def build_chains(llm1, llm2, retriever, debug: bool = False, materials_only: bool = True):
    """
    materials_only=True  -> output only product names + quantities (no prices)
    materials_only=False -> full offer (materials + labor + prices)
    """

    # ---------- Prompt 1: Chat/Erfassung (unchanged, just kept tidy) ----------
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            """
            Du bist ein Maler- & Lackierer-Assistent.
            Aufgabe: Kundenbedarf aufnehmen, Flächen berechnen, Materialbedarf schätzen.

            Regeln:
            - Antworte auf Deutsch, freundlich & kompakt.
            - Stelle nur die wichtigsten Rückfragen (max. 3).
            - Addiere ca. 10 % Reserve.
            - Runde auf marktübliche Gebinde (Farbe 2.5/5/10 L, Klebeband 50 m, Folie 20 m², Dichtstoff 310 ml).

            Ausgabe:
            1) Kurze Chat-Antwort für den Kunden.
            2) Striktes JSON:

            {
              "raeume": [
                {"name": string, "wandflaeche_m2": number|null, "deckenflaeche_m2": number|null,
                 "oeffnungen": {"tueren": number, "fenster": number}}
              ],
              "leistungen": [
                {"art": "Innenanstrich"|"Fassade"|"Lackieren"|"Spachteln",
                 "farbe": string|null, "finish": "matt"|"seidenglanz"|"glanz"|null, "anstriche": number}
              ],
              "mengen": {
                "farbe_liter": number,
                "grundierung_liter": number,
                "lack_liter": number,
                "acryl_kartuschen": number,
                "folie_m2": number,
                "klebeband_rollen": number
              }
            }

            GESPRÄCHSVERLAUF:
            {chat_history}

            KUNDE:
            {human_input}

            ANTWORT:
            """
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

    # ---------- Prompt 2: Angebots-/Material-Generator ----------
    # IMPORTANT: include all variables you reference in the template
    prompt2 = PromptTemplate(
        input_variables=[
            "context",          # ConversationalRetrievalChain requirement
            "question",         # ConversationalRetrievalChain requirement
            "product_catalog",  # your full product list (string)
            "extraction_json",  # JSON from chain1
            "materials_only"    # "true"/"false" (string)
        ],
        template=(
            """
            Du erstellst aus den JSON-Daten (EXTRAKTION) eine strukturierte Ausgabe.
            Es gibt zwei Betriebsmodi, gesteuert von materials_only:

            1) materials_only == "true":
               - Wähle ausschließlich Produkte aus dem KATALOG.
               - Auswahl-Regeln:
                 * Exakte, KATALOG-treue Benennung (case-insensitive; gib exakt den KATALOG-Namen zurück).
                 * Maximal 5 Produkte, möglichst passend zur EXTRAKTION.
                 * Falls mehrere passen, bevorzuge Innenanstrich/Fassade/Lack gemäß EXTRAKTION.
                 * Wenn nichts passt, LAß ES WEG (nicht halluzinieren).
               - Output: STRIKTES JSON NUR mit Produktnamen (ohne Mengen, ohne Preise):

                 { "materialien": [ "Produktname 1", "Produktname 2", ... ] }

            2) materials_only == "false":
               - Erzeuge vollständiges Angebots-JSON (Material+Lohn+Preise).
               - Nutze ausschließlich Produkte aus dem KATALOG (exakter Name).
               - Materialpreise netto → Summen bilden.
               - Arbeitszeit-Richtwerte: Wände ~15 m²/h, Decken ~10 m²/h, Türen ~1.2 h/Stk.
               - Stundensatz 52 EUR/h, MwSt 19 %.
               - Output-JSON:

                 {
                   "line_items": [
                     {"position": string, "kategorie": "Material"|"Lohn",
                      "menge": number, "einheit": string,
                      "einzelpreis_netto": number, "gesamt_netto": number}
                   ],
                   "summen": {
                     "material_netto": number,
                     "lohn_netto": number,
                     "netto": number,
                     "steuer": number,
                     "brutto": number
                   }
                 }

            STRIKTHEIT:
            - Verwende AUSSCHLIESSLICH Produkte, die im KATALOG stehen. Keine Synonyme, keine neuen Produkte.
            - Gibt Namen GENAU wie im KATALOG zurück (einschließlich Einheiten/Größen wie "10 L", "750 ml", etc.).
            - Keine Erklärtexte, nur das geforderte JSON.

            EXTRAKTION:
            {extraction_json}

            KATALOG:
            {product_catalog}

            materials_only={materials_only}

            Frage/Nutzerkontext:
            {question}

            Kontextdokumente:
            {context}

            ANTWORT (NUR JSON):
            """
        )
    )

    # Wrap the retriever chain so we can pass extra vars
    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug
    )

    return chain1, chain2, memory1, prompt2
