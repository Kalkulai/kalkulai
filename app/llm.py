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
    # Prompt 1: Chat/Erfassung (unverändert)
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            '''
            Du bist ein Maler- & Lackierer-Assistent.  
            Aufgabe: Kundenbedarf aufnehmen, Flächen berechnen, Materialbedarf schätzen.  

            Regeln:
            - Antworte auf Deutsch, freundlich & kompakt.  
            - Stelle nur die wichtigsten Rückfragen (max. 3).  
            - Addiere ca. 10 % Reserve.  
            - Runde auf marktübliche Gebinde (Farbe 2.5/5/10 L, Klebeband 50 m, Folie 20 m², Dichtstoff 310 ml).  

            Ausgabe:
            1) **Kurze Chat-Antwort** für den Kunden.  
            2) **Striktes JSON** mit den wichtigsten Infos:  

            {
            "raeume": [
                {
                "name": string,
                "wandflaeche_m2": number|null,
                "deckenflaeche_m2": number|null,
                "oeffnungen": {"tueren": number, "fenster": number}
                }
            ],
            "leistungen": [
                {
                "art": "Innenanstrich"|"Fassade"|"Lackieren"|"Spachteln",
                "farbe": string|null,
                "finish": "matt"|"seidenglanz"|"glanz"|null,
                "anstriche": number
                }
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
            '''
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

    # Prompt 2: Angebots-/Material-Generator (NUR dieses Template geändert)
    prompt2 = PromptTemplate(
        input_variables=["context", "question"],
        template="""
Du wandelst die Nutzereingabe (QUESTION) in ein Angebotsobjekt um.

WICHTIG:
- Produkte dürfen ausschließlich aus dem KATALOG (CONTEXT) stammen.
- Wenn der Nutzer unter 'Materialien:' eine Liste nennt, verwende GENAU diese Produkte (keine Alternativen).
- Gibt es zu einem genannten Produkt keinen Treffer im KATALOG, nimm es NICHT ins Angebot auf, sondern liste es in 'unmatched' – NICHT ersetzen.

Strenge Matching-Regeln (der Reihe nach prüfen):
1) Exakt gleicher Name (case-insensitive) inkl. identischer Gebinde-/Größenangabe (z. B. "10 L", "750 ml", "4x5 m").
2) Exakter Name, ignorierte Groß-/Kleinschreibung und überflüssige Leerzeichen.
3) Falls mehrere Katalogeinträge passen, wähle den mit identischer Größe/Einheit.
4) Wenn kein Treffer: -> 'unmatched'. KEINE Halluzinationen, KEINE Synonyme.

Preissteuerung:
- Standard: Erzeuge vollständiges Angebots-JSON (inkl. Preise), falls Preise im CONTEXT vorhanden sind.
- Wenn in QUESTION irgendwo das Wort 'KEINE_PREISE' steht, gib NUR Material-Linien OHNE Preise aus.

Ausgabe-Varianten:
A) Standard (mit Preisen), wenn 'KEINE_PREISE' NICHT in QUESTION vorkommt:
{
  "line_items": [
    {"position": "<Katalogname exakt>", "kategorie": "Material", "menge": null, "einheit": null,
     "einzelpreis_netto": null, "gesamt_netto": null}
    // Hinweis: Preise NUR ausgeben, wenn sie im CONTEXT eindeutig vorhanden sind; sonst null lassen.
    // Lohnpositionen NUR, wenn eindeutig aus QUESTION ableitbar.
  ],
  "summen": {
    "material_netto": null,
    "lohn_netto": null,
    "netto": null,
    "steuer": null,
    "brutto": null
  },
  "unmatched": ["<genannter, aber nicht gefundener Artikel>", ...]
}

B) Materialien-Only (ohne Preise), wenn QUESTION 'KEINE_PREISE' enthält:
{
  "materialien": [
    {"position": "<Katalogname exakt>"}
  ],
  "unmatched": ["<genannter, aber nicht gefundener Artikel>", ...]
}

Vorgehen:
1) Parse aus QUESTION:
   - Projektbeschreibung (frei),
   - optionale Liste unter der Überschrift 'Materialien:' (eine Zeile pro Produkt).
2) Interpretiere CONTEXT als KATALOG: jede Zeile ist genau EIN zulässiger Produktname (inkl. Einheit/Größe).
3) Wenn eine Nutzer-Materialliste existiert: versuche, jeden Eintrag streng zu matchen (siehe Regeln). Übernimm NUR gematchte.
   - Keine Ersetzungen/„ähnliche“ Produkte vorschlagen.
4) Wenn KEINE Nutzer-Materialliste existiert: wähle bis zu 5 passende Produkte aus dem KATALOG, die zur Projektbeschreibung passen.
5) Mengen NICHT schätzen, es sei denn, sie sind explizit im QUESTION genannt. Sonst keine Mengen ausgeben.
6) Preise nur ausgeben, wenn im CONTEXT vorhanden; sonst Preisfelder auf null belassen.

CONTEXT (KATALOG):
{context}

QUESTION:
{question}

ANTWORT (NUR JSON, kein Fließtext):
"""
    )

    chain2 = ConversationalRetrievalChain.from_llm(
        llm=llm2,
        retriever=retriever,
        combine_docs_chain_kwargs={"prompt": prompt2},
        verbose=debug
    )

    return chain1, chain2, memory1, prompt2
