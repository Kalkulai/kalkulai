from __future__ import annotations

"""
Utility script to (semi-)automatically generate domain synonyms (Variante B+).

Ziel:
- Ähnliche Produkt-/Begriffs-Namen per Embeddings finden
- Optional mit einem LLM („Büro-Checker“) filtern/bestätigen
- Ergebnis in einem YAML-Format ausgeben, das zu `shared/normalize/synonyms.yaml` passt

Verwendung (im Backend-Ordner ausführen):

    source .venv/bin/activate
    python -m tools.generate_synonyms \\
        --company-id demo \\
        --min-sim 0.65 \\
        --max-synonyms 5 \\
        --out-file /tmp/synonym_suggestions.yaml

Optionale LLM-Validierung (B+):
- Setze `OPENAI_API_KEY` (oder kompatibel, je nach deiner LLM-Config)
- Füge `--llm-validate` hinzu, dann werden Kandidaten mit einem kurzen Prompt
  geprüft (z. B. „Sind diese beiden Begriffe für Malerbedarf dasselbe Produkt-TYP-Level?“).

Wichtig:
- Das Script schreibt NICHT automatisch in `synonyms.yaml`,
  sondern erzeugt Vorschläge, die du prüfen und dann manuell/halbautomatisch mergen kannst.
"""

import argparse
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import yaml

from retriever.index_manager import _get_embedder  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class ProductName:
    id: int
    company_id: str
    sku: str
    name: str
    category: str | None
    material_type: str | None


def _load_product_names(company_id: str | None = None) -> List[ProductName]:
    """Load product names directly via sqlite3 (no SQLAlchemy needed)."""
    import sqlite3
    
    # Find the database
    db_paths = [
        Path("./var/kalkulai.db"),
        Path("./backend/var/kalkulai.db"),
    ]
    
    db_path = None
    for p in db_paths:
        if p.exists():
            db_path = p
            break
    
    if not db_path:
        raise FileNotFoundError("No kalkulai.db found")
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT id, company_id, sku, name, category, material_type FROM products WHERE is_active = 1"
    params = []
    
    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)
    
    result: List[ProductName] = []
    for row in cursor.execute(query, params):
        if not row["name"]:
            continue
        result.append(
            ProductName(
                id=row["id"],
                company_id=row["company_id"],
                sku=row["sku"],
                name=row["name"],
                category=row["category"],
                material_type=row["material_type"],
            )
        )
    
    conn.close()
    return result


def _embed_texts(texts: List[str]) -> np.ndarray:
    embedder = _get_embedder()
    # sentence-transformers Return-Type ist bereits ein numpy-Array oder list[list[float]]
    embs = embedder.encode(texts, normalize_embeddings=True, convert_to_numpy=True)  # type: ignore[attr-defined]
    return np.asarray(embs, dtype="float32")


def _cosine_sim_matrix(embs: np.ndarray) -> np.ndarray:
    # embeddings sind bereits normalisiert → Cosine = Dot-Product
    return embs @ embs.T


def _same_bucket(a: ProductName, b: ProductName) -> bool:
    """Nur Produkte im gleichen fachlichen „Bucket“ miteinander vergleichen."""
    if a.company_id != b.company_id:
        return False
    if a.category and b.category and a.category != b.category:
        return False
    if a.material_type and b.material_type and a.material_type != b.material_type:
        return False
    return True


def _generate_pairs(
    products: List[ProductName],
    sims: np.ndarray,
    min_sim: float,
) -> Dict[str, List[Tuple[str, float]]]:
    suggestions: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    n = len(products)
    for i in range(n):
        pi = products[i]
        for j in range(i + 1, n):
            pj = products[j]
            if not _same_bucket(pi, pj):
                continue
            sim = float(sims[i, j])
            if sim < min_sim:
                continue
            # Beide Richtungen vorschlagen (Name A ~ Name B und umgekehrt)
            if pi.name != pj.name:
                suggestions[pi.name].append((pj.name, sim))
                suggestions[pj.name].append((pi.name, sim))
    return suggestions


def _llm_filter_pairs(
    raw_suggestions: Dict[str, List[Tuple[str, float]]],
    model: str | None = None,
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Optional: Validierung über ein LLM.

    Erwartet, dass OPENAI_API_KEY (oder kompatibel) gesetzt ist und ein
    `openai`-kompatibler Client installiert ist. Läuft bewusst sehr simpel:
    - Für jedes (A,B) Paar: kurze Frage „Sind das im Maler-/Baubedarf
      praktisch dieselbe Produktart?“
    - Antwort „ja/nein“ auswerten.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_ALT")
    if not api_key:
        print("⚠️  LLM-Validierung übersprungen (kein OPENAI_API_KEY gesetzt).")
        return raw_suggestions

    try:
        import openai  # type: ignore
    except Exception:
        print("⚠️  openai-Paket nicht verfügbar, LLM-Validierung übersprungen.")
        return raw_suggestions

    openai.api_key = api_key
    model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def _ask_llm(a: str, b: str) -> bool:
        prompt = (
            "Du bist Experte für Maler- und Baubedarf.\n"
            "Frage: Bezeichnen die folgenden zwei Begriffe im Handwerker-Alltag "
            "im Wesentlichen DIESELBE Produktart (gleicher Produkttyp, nur andere Formulierung)?\n\n"
            f"A: {a}\n"
            f"B: {b}\n\n"
            "Antworte NUR mit 'ja' oder 'nein'."
        )
        try:
            resp = openai.ChatCompletion.create(  # type: ignore[attr-defined]
                model=model_name,
                messages=[
                    {"role": "system", "content": "Du bist ein präziser Assistent."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=2,
            )
            answer = (resp.choices[0].message["content"] or "").strip().lower()  # type: ignore[index]
            return answer.startswith("j")
        except Exception as exc:  # pragma: no cover - nur bei Laufzeitfehlern
            print(f"LLM-Check fehlgeschlagen für Paar ({a!r}, {b!r}): {exc}")
            return False

    filtered: Dict[str, List[Tuple[str, float]]] = {}
    for base, syns in raw_suggestions.items():
        accepted: List[Tuple[str, float]] = []
        for syn, sim in syns:
            if _ask_llm(base, syn):
                accepted.append((syn, sim))
        if accepted:
            filtered[base] = accepted
    return filtered


def _to_yaml(
    suggestions: Dict[str, List[Tuple[str, float]]],
    max_synonyms: int,
) -> str:
    """
    Konvertiert in ein YAML-Format, das zu `synonyms.yaml` passt:

    base_term:
      - synonym1
      - synonym2
    """
    out: Dict[str, List[str]] = {}
    for base, syns in suggestions.items():
        # Nach Ähnlichkeit sortieren, stärkste zuerst
        syns_sorted = sorted(syns, key=lambda x: x[1], reverse=True)[:max_synonyms]
        out[base] = [s for s, _ in syns_sorted]

    return yaml.safe_dump(out, sort_keys=True, allow_unicode=True)


def _normalize_key(name: str) -> str:
    """Normalize product name to synonym key."""
    return name.lower().strip()


def extract_searchterm_synonyms(products: List[ProductName]) -> Dict[str, List[str]]:
    """
    Extrahiert Suchbegriff-zu-Produktname Synonyme aus Produktnamen.
    
    Beispiele:
    - "Holzschutzfarbe" → generiert Synonym: "holzschutz" → ["holzschutzfarbe"]
    - "Tiefengrund" → generiert Synonym: "tiefen" → ["tiefengrund"], "grund" → ["tiefengrund"]
    - "Fassadenrolle" → generiert Synonym: "farbrolle" → ["fassadenrolle"]
    """
    from collections import defaultdict
    
    # Bekannte Wortbestandteile für deutschen Malerbedarf
    KNOWN_COMPOUNDS = {
        # Farben
        "farbe", "lack", "lasur", "grund", "schutz", "dispersion", "latex", "acryl",
        "fassade", "fassaden", "mineral", "silikat", "kalk", "holz", "rost", "tafel",
        "magnet", "bunt", "weiß", "weiss", "matt", "glänzend", "glaenzend", "deckend",
        # Werkzeuge
        "rolle", "pinsel", "spachtel", "bürste", "quirl", "stange", "leiter", "gerüst",
        # Materialien
        "band", "krepp", "folie", "papier", "vlies", "gewebe", "silikon", "acryl",
        # Größen/Einheiten
        "10l", "5l", "2l", "1l", "750ml", "400ml", "25cm", "50m", "25m",
    }
    
    # Manuelle Synonym-Mappings für häufige Suchbegriffe
    MANUAL_SEARCH_SYNONYMS = {
        "holzschutz": ["holzschutzfarbe", "holzlasur", "holzschutzlasur"],
        "farbrolle": ["fassadenrolle", "lackierrolle", "malerrolle", "schaumstoffrolle"],
        "rolle": ["farbrolle", "fassadenrolle", "lackierrolle"],
        "grund": ["tiefengrund", "haftgrund", "sperrgrund", "isoliergrund", "grundierung"],
        "grundierung": ["tiefengrund", "haftgrund", "sperrgrund", "isoliergrund"],
        "klebeband": ["malerkrepp", "kreppband", "abklebeband", "gewebeband"],
        "tape": ["malerkrepp", "klebeband", "gewebeband"],
        "spachtel": ["fertigspachtel", "reparaturspachtel", "holzspachtel", "gipskartonspachtel"],
        "spray": ["farbspray", "lackspray", "haftgrund spray"],
        "verdünnung": ["verdünner", "nitroverdünnung", "lösemittel"],
        "verduennung": ["verdünner", "nitroverdünnung", "lösemittel"],
        "handschuh": ["handschuhe", "nitrilhandschuhe", "einweghandschuhe"],
        "maske": ["staubmaske", "atemschutzmaske", "schutzmaske"],
        "anzug": ["maleranzug", "schutzanzug", "einweganzug"],
        "eimer": ["farbeimer", "eimer set"],
        "wanne": ["farbwanne"],
        "innen": ["innenfarbe", "dispersionsfarbe", "wandfarbe"],
        "außen": ["außenfarbe", "fassadenfarbe", "außen"],
        "aussen": ["außenfarbe", "fassadenfarbe", "außen"],
    }
    
    synonyms: Dict[str, List[str]] = defaultdict(list)
    
    # 1. Manuelle Synonyme hinzufügen
    for search_term, product_terms in MANUAL_SEARCH_SYNONYMS.items():
        synonyms[search_term].extend(product_terms)
    
    # 2. Automatische Präfix-Extraktion aus Produktnamen
    product_name_tokens = set()
    for prod in products:
        # Nur den Hauptnamen ohne Größenangaben
        name_lower = prod.name.lower()
        # Erstes Wort extrahieren (z.B. "Holzschutzfarbe" aus "Holzschutzfarbe deckend 2.5L")
        first_word = name_lower.split()[0] if name_lower.split() else ""
        if len(first_word) > 4:
            product_name_tokens.add(first_word)
    
    # 3. Für jedes Produkt-Token: Präfixe als Suchbegriffe generieren
    for token in product_name_tokens:
        # Versuche bekannte Compound-Teile zu finden
        for compound in KNOWN_COMPOUNDS:
            # Wenn Token mit Compound anfängt und länger ist
            if token.startswith(compound) and len(token) > len(compound) + 2:
                # z.B. "holzschutzfarbe" startswith "holzschutz" → füge "holzschutz" → "holzschutzfarbe" hinzu
                if compound not in synonyms or token not in synonyms[compound]:
                    synonyms[compound].append(token)
            
            # Wenn Token Compound enthält (z.B. "fassadenrolle" enthält "rolle")
            if compound in token and token != compound:
                # Generiere Präfix als Suchbegriff
                prefix = token.replace(compound, "").strip()
                if len(prefix) >= 3:
                    # z.B. "fassaden" aus "fassadenrolle" - aber "fassaden" → "fassadenrolle"
                    if prefix not in synonyms or token not in synonyms[prefix]:
                        synonyms[prefix].append(token)
    
    # 4. Deduplizieren und sortieren
    result = {}
    for key, values in synonyms.items():
        unique_values = list(dict.fromkeys(values))  # Deduplizieren, Reihenfolge beibehalten
        if unique_values:
            result[key] = unique_values
    
    return result


def _cosine_similarity(a, b) -> float:
    """Calculate cosine similarity between two vectors."""
    import numpy as np
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def generate_synonyms(
    company_id: str | None = None,
    min_similarity: float = 0.60,
    max_synonyms: int = 5,
    include_searchterm_synonyms: bool = True,
) -> Dict[str, List[str]]:
    """Generate synonyms programmatically (callable from other modules).
    
    Generates two types of synonyms:
    1. Product-to-Product: Similar products (via embeddings)
    2. Searchterm-to-Product: Search terms that should match products
    """
    products = _load_product_names(company_id=company_id)
    if not products:
        return {}
    
    synonyms: Dict[str, List[str]] = {}
    
    # 1. Suchbegriff-zu-Produkt Synonyme (regelbasiert)
    if include_searchterm_synonyms:
        searchterm_syns = extract_searchterm_synonyms(products)
        for key, values in searchterm_syns.items():
            synonyms[key] = values
    
    # 2. Produkt-zu-Produkt Synonyme (embedding-basiert)
    try:
        embedder = _get_embedder()
        names = [p.name for p in products]
        embeddings = embedder.encode(names, show_progress_bar=False)
        
        for i, prod in enumerate(products):
            similar = []
            for j, other in enumerate(products):
                if i == j:
                    continue
                # Same category filter
                if prod.category and other.category and prod.category != other.category:
                    continue
                
                sim = _cosine_similarity(embeddings[i], embeddings[j])
                if sim >= min_similarity:
                    similar.append((other.name, sim))
            
            similar.sort(key=lambda x: -x[1])
            if similar:
                key = _normalize_key(prod.name)
                synonyms[key] = [name for name, _ in similar[:max_synonyms]]
    except Exception as e:
        # Fallback: Nur Suchbegriff-Synonyme wenn Embeddings fehlschlagen
        logger.warning(f"Embedding-based synonyms failed: {e}")
    
    return synonyms


def merge_into_yaml(new_synonyms: Dict[str, List[str]], yaml_path: Path) -> None:
    """Merge new synonyms into existing YAML file."""
    import yaml
    
    existing = {}
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    
    # Merge: new entries override existing
    merged = {**existing, **new_synonyms}
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, allow_unicode=True, default_flow_style=False)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synonym suggestions from product catalog.")
    parser.add_argument("--company-id", default=None, help="Company ID (z. B. 'demo'); leer = alle.")
    parser.add_argument("--min-sim", type=float, default=0.65, help="Mindest-Cosine-Similarität für Kandidaten.")
    parser.add_argument("--max-synonyms", type=int, default=5, help="Max. Synonyme pro Basisbegriff.")
    parser.add_argument("--out-file", default="-", help="'-' = stdout, sonst Pfad zu einer YAML-Datei.")
    parser.add_argument("--llm-validate", action="store_true", help="Kandidaten zusätzlich per LLM prüfen (Variante B+).")
    parser.add_argument("--llm-model", default=None, help="Optionales LLM-Modell (z. B. gpt-4o-mini).")
    args = parser.parse_args(list(argv) if argv is not None else None)

    products = _load_product_names(company_id=args.company_id)
    if not products:
        print("Keine aktiven Produkte gefunden.")
        return

    # Kombiniere beide Typen: Suchbegriff-Synonyme und Produkt-Synonyme
    all_synonyms: Dict[str, List[str]] = {}
    
    # 1. Suchbegriff-zu-Produkt Synonyme (regelbasiert)
    print("Generiere Suchbegriff-Synonyme ...")
    searchterm_syns = extract_searchterm_synonyms(products)
    for key, values in searchterm_syns.items():
        all_synonyms[key] = values
    print(f"Suchbegriff-Synonyme: {len(searchterm_syns)} Einträge")
    
    # 2. Produkt-zu-Produkt Synonyme (embedding-basiert)
    print(f"Lade Embeddings für {len(products)} Produktnamen ...")
    embs = _embed_texts([p.name for p in products])
    sims = _cosine_sim_matrix(embs)

    print("Berechne Kandidatenpaare ...")
    raw = _generate_pairs(products, sims, min_sim=args.min_sim)
    print(f"Roh-Vorschläge: {sum(len(v) for v in raw.values())} Paare")

    if args.llm_validate:
        print("Starte LLM-Validierung (Variante B+) ...")
        checked = _llm_filter_pairs(raw, model=args.llm_model)
    else:
        checked = raw
    
    # Konvertiere Produkt-Synonyme in das gleiche Format
    product_synonyms: Dict[str, List[str]] = {}
    for base, syns in checked.items():
        syns_sorted = sorted(syns, key=lambda x: x[1], reverse=True)[:args.max_synonyms]
        product_synonyms[_normalize_key(base)] = [s for s, _ in syns_sorted]
    
    # Kombiniere beide Typen
    for key, values in product_synonyms.items():
        if key in all_synonyms:
            # Deduplizieren wenn bereits vorhanden
            existing = set(all_synonyms[key])
            new_values = [v for v in values if v not in existing]
            all_synonyms[key].extend(new_values)
        else:
            all_synonyms[key] = values
    
    # Konvertiere zu YAML
    yaml_text = yaml.safe_dump(all_synonyms, sort_keys=True, allow_unicode=True)

    if args.out_file == "-" or not args.out_file:
        print("\n# Synonym-Vorschläge")
        print(yaml_text)
    else:
        with open(args.out_file, "w", encoding="utf-8") as f:
            f.write(yaml_text)
        
        # Statistik ausgeben
        searchterm_count = len(searchterm_syns)
        product_count = len(product_synonyms)
        
        print(f"✅ Synonym-Vorschläge nach {args.out_file} geschrieben.")
        print(f"   - Suchbegriff-Synonyme: {searchterm_count}")
        print(f"   - Produkt-Synonyme: {product_count}")
        print(f"   - Gesamt: {len(all_synonyms)} Einträge")


if __name__ == "__main__":  # pragma: no cover - nur bei direktem Aufruf
    main()



