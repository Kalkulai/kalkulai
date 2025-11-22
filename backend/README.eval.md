# Offline Retrieval Evaluation

| Mode | Metric        | Threshold | Command |
|------|---------------|-----------|---------|
| Thin | Recall@K      | ≥ 0.92    | `python -m backend.eval.eval_thin --gold backend/eval/goldset.sample.yaml --k 5` |
| Main | Precision@1   | ≥ 0.85    | `python -m backend.eval.eval_main --gold backend/eval/goldset.sample.yaml --k 5` |

Die Skripte laden automatisch den bestehenden Katalog/Retriever, evaluieren gegen das Goldset (anpassbar) und liefern Median-Latenz plus Schwellen-Check (Exit-Code ≠ 0 bei Verfehlung). Ergebnisse können in CI oder lokal ausgeführt werden; Goldsets liegen unter `backend/eval/`.
