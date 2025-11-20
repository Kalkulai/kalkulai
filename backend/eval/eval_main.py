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
os.environ.setdefault("FORCE_RETRIEVER_BUILD", "0")

try:
    import backend.main as backend_main
except Exception as exc:  # pragma: no cover - defensive
    print(f"Failed to import backend.main: {exc}", file=sys.stderr)
    raise

from backend.retriever.main import rank_main


@dataclass
class MainEvalResult:
    precision_at_1: float
    latencies_ms: List[float]
    hits: List[bool]

    @property
    def median_latency(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0


def load_goldset(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def evaluate_main(cases: List[Dict[str, Any]], top_k: int) -> MainEvalResult:
    business_cfg: Dict[str, Dict[str, Any]] = {"availability": {}, "price": {}, "margin": {}, "brand_boost": {}}
    latencies: List[float] = []
    hits: List[bool] = []
    retriever = backend_main.RETRIEVER

    for case in cases:
        query = (case.get("query") or "").strip()
        ideal_sku = (case.get("ideal_sku") or "").strip()
        if not query or not ideal_sku:
            continue

        started = time.perf_counter()
        results = rank_main(query, retriever, top_k=top_k, business_cfg=business_cfg)
        latency_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(latency_ms)

        top = results[0] if results else {}
        hit = bool(top) and (top.get("sku") == ideal_sku)
        hits.append(hit)

        status = "✅" if hit else "❌"
        sku_info = top.get("sku") if top else "-"
        print(f"{status} {query:<30} expected={ideal_sku:<15} got={sku_info:<15} latency_ms={latency_ms:6.1f}")

    precision = (sum(hits) / len(hits)) if hits else 1.0
    print(f"\nPrecision@1: {precision:.3f}  |  Median latency: {statistics.median(latencies) if latencies else 0.0:.1f} ms")
    return MainEvalResult(precision_at_1=precision, latencies_ms=latencies, hits=hits)


def main() -> int:
    parser = argparse.ArgumentParser(description="Main retriever offline evaluation")
    parser.add_argument("--gold", required=True, type=Path, help="Path to YAML goldset")
    parser.add_argument("--k", default=5, type=int, help="Top-K candidates pulled from retriever")
    args = parser.parse_args()

    gold_data = load_goldset(args.gold)
    cases = gold_data.get("main", [])
    if not cases:
        print("No main cases found in goldset.")
        return 0

    result = evaluate_main(cases, args.k)
    threshold = 0.85
    exit_code = 0 if result.precision_at_1 >= threshold else 1
    if exit_code == 0:
        print(f"\n✅ Precision threshold met ({result.precision_at_1:.3f} ≥ {threshold})")
    else:
        print(f"\n❌ Precision threshold missed ({result.precision_at_1:.3f} < {threshold})")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
