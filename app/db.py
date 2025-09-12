from pathlib import Path
from typing import List
from striprtf.striprtf import rtf_to_text
from langchain.schema import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

def load_products_file(file_path: Path, debug: bool=False) -> List[Document]:
    if not file_path.exists():
        raise FileNotFoundError(f"Produktdatei fehlt: {file_path}")
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    if file_path.suffix.lower() == ".rtf":
        try:
            raw = rtf_to_text(raw)
        except Exception as e:
            if debug: print("[WARN] RTF-Konvertierung:", e)
    docs=[]
    for entry in raw.split("Produkt: "):
        entry=entry.strip()
        if entry:
            docs.append(Document(page_content="Produkt: " + entry))
    if debug: print(f"[DEBUG] Geladene Produkt-Docs: {len(docs)}")
    return docs

def build_vector_db(documents: List[Document], chroma_dir: Path, debug: bool=False):
    chroma_dir.mkdir(exist_ok=True)
    embedding = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    db = Chroma(persist_directory=str(chroma_dir), embedding_function=embedding)
    try: count = db._collection.count()
    except Exception: count = 0
    if count == 0 and documents:
        db = Chroma.from_documents(documents=documents, embedding=embedding, persist_directory=str(chroma_dir))
        if debug: print(f"[DEBUG] Chroma neu aufgebaut mit {len(documents)} Docs")
    else:
        if debug: print(f"[DEBUG] Chroma geladen (count={count})")
    retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 10})
    return db, retriever
