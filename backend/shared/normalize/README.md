# Normalization helpers

Dieses Paket bündelt alle textuellen Vorverarbeitungsschritte, die wir sowohl
im Thin-Client als auch im Retrieval/Angebots-Backend benötigen. Fokus liegt auf
stabiler Normalisierung (ASCII, einfache Stemming-Regeln), heuristischen
Komposita-Splits und der Verwaltung von Synonym- sowie Regel-Dateien.

## Module

- `text.py` stellt reine Funktionen bereit:
  - `normalize_query(text)` – Whitespace/Case-Normalisierung inkl. Umlaute.
  - `tokenize(text)` – Token-Set + simple Stems + Kompositum-Bestandteile.
  - `lemmatize_decompound(text)` – heuristische Zerlegung gängiger Maler-Terme.
  - `load_synonyms(path)` – YAML → normalisierte `{canon: [synonyme]}` Mapping.
  - `apply_synonyms(tokens, synonyms)` – ergänzt Token-Sets um kanonische
    Bezeichnungen.

Alle Funktionen sind deterministisch, nutzen keine globale State und sind
zwischen Thin- und Main-Retrieval identisch einsetzbar.

## YAML-Schemata

`synonyms.yaml`
```
canon:
  - synonym 1
  - synonym 2
```

`rules.yaml`
```
hard_filters:
  <filter_name>:
    <category>:
      - wert
soft_rules:
  <rule_name>:
    attribute: merkmal
```

Die Regeln dienen aktuell nur als Platzhalter für spätere Filter-/Scoring-Logik.

## Integration

Die Funktionen und YAML-Dateien werden in Schritt 4 in `main.py` o. Ä. verdrahtet.
Bis dahin bleiben sämtliche Aufrufe auf Tests bzw. zukünftige Module beschränkt.
