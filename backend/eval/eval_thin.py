from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

os.environ.setdefault("SKIP_LLM_SETUP", "1")

try:
    import backend.main as backend_main
except Exception as exc:  # pragma: no cover - defensive
    print(f"Failed to import backend.main: {exc}", file=sys.stderr)
    raise

from backend.retriever.thin import search_catalog_thin


@dataclass
class ThinEvalResult:
    recall_at_k: float
    latencies_ms: List[float]
    hits: List[bool]

    @property
    def median_latency(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0


def load_goldset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def evaluate_thin(cases: List[Dict[str, Any]], top_k: int) -> ThinEvalResult:
    latencies: List[float] = []
    hits: List[bool] = []
    catalog_items = backend_main.CATALOG_ITEMS
    synonyms_path = getattr(backend_main, "SYNONYMS_PATH", None)

    for case in cases:
        query = case.get("query", "").strip()
        must_contain = (case.get("must_contain_name") or "").lower()
        if not query:
            continue

        started = time.perf_counter()
        results = search_catalog_thin(
            query=query,
            top_k=top_k,
            catalog_items=catalog_items,
            synonyms_path=str(synonyms_path) if synonyms_path else None,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(latency_ms)

        match = False
        for hit in results:
            name = (hit.get("name") or "").lower()
            if must_contain and must_contain in name:
                match = True
                break
        hits.append(match)

        status = "✅" if match else "❌"
        print(f"{status} {query:<30} hit={match!s:<5} latency_ms={latency_ms:6.1f}")

    recall = (sum(hits) / len(hits)) if hits else 1.0
    print(f"\nRecall@{top_k}: {recall:.3f}  |  Median latency: {statistics.median(latencies) if latencies else 0.0:.1f} ms")
    return ThinEvalResult(recall_at_k=recall, latencies_ms=latencies, hits=hits)


def main() -> int:
    parser = argparse.ArgumentParser(description="Thin retriever offline evaluation")
    parser.add_argument("--gold", required=True, type=Path, help="Path to YAML goldset")
    parser.add_argument("--k", default=5, type=int, help="Top-K to evaluate")
    args = parser.parse_args()

    gold_data = load_goldset(args.gold)
    cases = gold_data.get("thin", [])
    if not cases:
        print("No thin cases found in goldset.")
        return 0

    result = evaluate_thin(cases, args.k)
    threshold = 0.92
    exit_code = 0 if result.recall_at_k >= threshold else 1
    if exit_code == 0:
        print(f"\n✅ Recall threshold met ({result.recall_at_k:.3f} ≥ {threshold})")
    else:
        print(f"\n❌ Recall threshold missed ({result.recall_at_k:.3f} < {threshold})")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
