from pathlib import Path
from typing import List
from striprtf.striprtf import rtf_to_text

# Neuere, nicht-deprecated Imports:
from langchain.schema import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import DocArrayInMemorySearch


def load_products_file(file_path: Path, debug: bool = False) -> List[Document]:
    if not file_path.exists():
        raise FileNotFoundError(f"Produktdatei fehlt: {file_path}")

    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    if file_path.suffix.lower() == ".rtf":
        try:
            raw = rtf_to_text(raw)
        except Exception as e:
            if debug:
                print("[WARN] RTF-Konvertierung:", e)

    docs: List[Document] = []
    for entry in raw.split("Produkt: "):
        entry = entry.strip()
        if entry:
            docs.append(Document(page_content="Produkt: " + entry))

    if debug:
        print(f"[DEBUG] Geladene Produkt-Docs: {len(docs)}")
    return docs


def build_vector_db(documents: List[Document], chroma_dir: Path, debug: bool = False):
    # WICHTIG: mit parents=True (bleibt für kompatible Logs, obwohl wir in-memory arbeiten)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    embedding = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    if documents:
        db = DocArrayInMemorySearch.from_documents(documents=documents, embedding=embedding)
        if debug:
            print(f"[DEBUG] DocArrayInMemorySearch aufgebaut mit {len(documents)} Docs")
    else:
        db = DocArrayInMemorySearch.from_texts(texts=[], embedding=embedding)
        if debug:
            print("[DEBUG] Keine Dokumente für den Vektor-Index gefunden")

    retriever = db.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 20, "fetch_k": 50, "lambda_mult": 0.5}
    )
    return db, retriever
