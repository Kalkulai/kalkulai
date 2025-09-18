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
        return ChatOpenAI(model=model, temperature=temperature, openai_api_key=api_key)
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=temperature, top_p=top_p, base_url=base_url)
    else:
        raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def build_chains(llm1, llm2, retriever, debug: bool = False):
    # Prompt 1: Chat/Erfassung – klar, stichpunktartig, keine Preisabfrage
    prompt1 = PromptTemplate(
        input_variables=["chat_history", "human_input"],
        template=(
            "# Maler- & Lackierer-Assistent\n"
            "Du bist ein professioneller Assistent für Maler- und Lackierarbeiten.\n"
            "Ziel: Mit dem Kunden chatten, Materialbedarf kalkulieren und eine Angebotsbasis schaffen.\n\n"
            "Stil & Struktur:\n"
            "- Antworte immer auf Deutsch, freundlich und professionell.\n"
            "- Verwende **fette** Überschriften NUR für Abschnittstitel (z. B. **Projektbeschreibung**, **Materialbedarf**).\n"
            "- Nach jeder Überschrift kommt GENAU EINE LEERE ZEILE.\n"
            "- Inhalte unter den Überschriften sind IMMER echte Markdown-Listen: Jede Zeile beginnt mit \"- \". Keine nummerierten Listen.\n"
            "- Keine übermäßige Formatierung, keine Tabellen erforderlich.\n"
            "- Am Ende kurz um Bestätigung der Mengen bitten (keine Preisabfragen an den Kunden!).\n\n"
            "Fachlogik (Richtwerte):\n"
            "- Dispersionsfarbe: 1 L pro 10 m², 2 Anstriche, +10 % Reserve.\n"
            "- Tiefengrund: 1 L pro 15 m², 1 Auftrag, +10 % Reserve.\n"
            "- Weitere Materialien (Abdeckfolie, Abklebeband, Malerrollen etc.) sinnvoll schätzen inkl. Reserve.\n\n"
            "Maschinenanhang:\n"
            "- Am Nachrichtenende IMMER einen separaten Datenanhang ausgeben:\n"
            "  ---\n"
            "  status: schätzung\n"
            "  materialien:\n"
            "  - name, menge=..., einheit=...\n"
            "  ---\n"
            "- Der Chat-Text DARF NICHT diese Felder enthalten; nur der Datenanhang.\n\n"
            "GESPRÄCHSVERLAUF:\n{chat_history}\n\n"
            "KUNDE: {human_input}\n\n"
            "ANTWORT (Beispielaufbau):\n"
            "**Projektbeschreibung**\n"
            "- Wandfläche: ... m²\n"
            "- Deckenfläche: ... m²\n"
            "- Gesamtfläche: ... m²\n\n"
            "**Materialbedarf**\n"
            "- Dispersionsfarbe: ... L\n"
            "- Tiefengrund: ... L\n"
            "- Abdeckfolie: ... Rolle(n)\n"
            "- Abklebeband: ... Rolle(n)\n"
            "- Malerrolle: ... Stück\n\n"
            "Bitte bestätigen Sie die Mengen oder geben Sie gewünschte Anpassungen an – dann erstelle ich das Angebot.\n\n"
            "---\n"
            "status: schätzung\n"
            "materialien:\n"
            "- name, menge=..., einheit=...\n"
            "---"
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

    # Prompt 2: Angebots-JSON (mit Gebinde-/Packgrößen-Logik)
    prompt2 = PromptTemplate(
        input_variables=["context", "question"],
        template=(
            "Antworte ausschließlich auf Deutsch.\n"
            "GIB AUSSCHLIESSLICH EINEN JSON-ARRAY ZURÜCK. KEINE EINLEITUNG, KEIN MARKDOWN, KEINE ERKLÄRUNG.\n"
            "Der Output MUSS mit '[' beginnen und mit ']' enden.\n"
            "Format:\n"
            "[{{\"nr\": number, \"name\": string, \"menge\": number|null, \"einheit\": string|null, \"epreis\": number|null}}]\n"
            "- Keine Kommentare, keine zusätzlichen Felder, keine Code-Fences, keine Zeilen davor oder danach.\n"
            "- Wenn keine passenden Produkte gefunden werden: gib [] (nur die zwei Zeichen).\n\n"
            "WICHTIG:\n"
            "- Die QUESTION enthält einen Datenanhang zwischen --- Blöcken. Analysiere NUR diesen Datenanhang (status/materialien). Alles andere ignorieren.\n"
            "- Produkte dürfen AUSSCHLIESSLICH aus dem KATALOG (Kontext) stammen. Produktnamen EXAKT übernehmen (inkl. Größe/Einheit wie \"10 L\").\n"
            "- Keine Synonyme/Alternativen. Nicht im Katalog = nicht aufnehmen.\n"
            "- Mengen/Einheiten aus dem Anhang übernehmen; fehlen sie: menge=null, einheit=null.\n"
            "- 'epreis' nur setzen, wenn im KATALOG eindeutig vorhanden; sonst null.\n"
            "- 'nr' beginnt bei 1 und folgt der Ausgabe-Reihenfolge.\n"
            "- **Gebinde-/Packgrößen-Logik:** Falls der KATALOG-Name eine Pack-/Gebindegröße enthält (z. B. \"10 L\", \"25 kg\", \"50 m²\", \"2,5 L\") "
            "und der Datenanhang eine Gesamtmenge in Basis-Einheiten (L, kg, m²) angibt, dann:\n"
            "  1) Wandle die Gesamtmenge in die Anzahl der Gebinde um = CEILING(Gesamtmenge / Gebindegröße).\n"
            "  2) Setze 'menge' = ganze Anzahl der Gebinde (Integer) und 'einheit' = passende Stück-Einheit (z. B. \"Eimer\" für L-Farbe, \"Sack\" für kg, "
            "\"Rolle\" für m²-Rollen, sonst \"Packung\" oder wenn unklar \"Stück\").\n"
            "  3) 'epreis' ist der Preis pro Gebinde aus dem KATALOG.\n"
            "  4) Falls der Datenanhang bereits Stück/Packungen angibt (z. B. Rolle/Eimer) und dies zum Katalog passt, dann NICHT umrechnen.\n"
            "- Bei mehreren passenden Katalogeinträgen mit unterschiedlichen Gebindegrößen: wähle die, die am besten zur Schätzung passt (nahe an der berechneten Anzahl, weniger Überhang).\n\n"
            "Kontext (KATALOG):\n{context}\n\n"
            "QUESTION (nur zur Info; werte NUR den Datenanhang zwischen --- aus):\n{question}\n\n"
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
