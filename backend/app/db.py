from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import re

try:
    from striprtf.striprtf import rtf_to_text  # type: ignore
except ImportError:  # pragma: no cover - optional dependency for smoke tests
    rtf_to_text = None  # type: ignore[assignment]

try:  # pragma: no cover - optional during smoke tests
    from langchain_core.documents import Document  # type: ignore
except ImportError:  # pragma: no cover - lightweight fallback for smoke tests
    @dataclass
    class Document:  # type: ignore[override]
        page_content: str
        metadata: Dict[str, object] | None = None  # type: ignore[assignment]


_SKU_SANITIZE_RE = re.compile(r"[^a-z0-9]+")

def _gen_sku(name: str) -> str:
    slug = _SKU_SANITIZE_RE.sub("-", name.lower()).strip("-")
    return slug or f"produkt-{abs(hash(name))}"


def _parse_menge_line(line: str) -> tuple[Optional[str], Optional[str]]:
    """
    Wandelt 'Menge: 1 Eimer (10 L)' in (unit, pack_sizes).
    """
    raw = line.replace("Menge:", "", 1).strip()
    if not raw:
        return None, None
    parts = raw.split()
    unit = parts[-1] if parts else None
    return unit, raw


def _ensure_rtf_support(debug: bool) -> None:
    if rtf_to_text is None:
        msg = "striprtf ist nicht installiert – RTF-Dateien können nicht konvertiert werden."
        if debug:
            print(f"[WARN] {msg} Fallback: RTF wird als Klartext behandelt.")

def _maybe_convert_rtf(raw: str, debug: bool) -> str:
    if rtf_to_text is None:
        _ensure_rtf_support(debug)
        return raw
    try:
        return rtf_to_text(raw)
    except Exception as exc:
        if debug:
            print(f"[WARN] RTF-Konvertierung fehlgeschlagen: {exc}")
        return raw


def load_products_file(file_path: Path, debug: bool = False) -> List[Document]:
    if not file_path.exists():
        raise FileNotFoundError(f"Produktdatei fehlt: {file_path}")

    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    if file_path.suffix.lower() == ".rtf":
        raw = _maybe_convert_rtf(raw, debug)

    docs: List[Document] = []
    for entry in raw.split("Produkt: "):
        entry = entry.strip()
        if entry:
            lines = entry.splitlines()
            name = lines[0].strip()

            desc = ""
            menge_line = ""
            brand = ""
            category = ""
            for line in lines[1:]:
                if line.startswith("Beschreibung:"):
                    desc = line.replace("Beschreibung:", "", 1).strip()
                elif line.startswith("Menge:"):
                    menge_line = line
                elif line.startswith("Marke:"):
                    brand = line.replace("Marke:", "", 1).strip()
                elif line.startswith("Kategorie:"):
                    category = line.replace("Kategorie:", "", 1).strip()

            unit, pack_sizes = _parse_menge_line(menge_line)

            metadata: Dict[str, Optional[str] | List[str]] = {
                "name": name,
                "description": desc or None,
                "unit": unit,
                "pack_sizes": pack_sizes,
                "sku": _gen_sku(name),
                "category": category or None,
                "brand": brand or None,
                "synonyms": [],
            }

            docs.append(
                Document(
                    page_content="Produkt: " + entry,
                    metadata=metadata,  # type: ignore[arg-type]
                )
            )

    if debug:
        print(f"[DEBUG] Geladene Produkt-Docs: {len(docs)}")
    return docs


def build_vector_db(documents: List[Document], chroma_dir: Path, debug: bool = False):
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore
        from langchain_community.vectorstores import DocArrayInMemorySearch  # type: ignore
    except ImportError as exc:  # pragma: no cover - only happens in smoke tests
        raise RuntimeError(
            "LangChain Vektor-DB Abhängigkeiten fehlen. Bitte installiere die regulären requirements.txt."
        ) from exc

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
