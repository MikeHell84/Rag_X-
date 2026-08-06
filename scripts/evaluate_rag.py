#!/usr/bin/env python
"""
Harness de evaluación ligero para el pipeline RAG.

Calcula:
- MRR@k (Mean Reciprocal Rank) de retrieval
- F1-token overlap entre respuesta y fuentes (proxy de faithfulness)
- Recall@k de chunks relevantes (requiere ground truth)

Uso:
  python scripts/evaluate_rag.py --questions data/eval_questions.json --top-k 5

Formato data/eval_questions.json:
[
  {
    "question": "¿Cuántos días de vacaciones?",
    "relevant_chunk_ids": [17, 15],
    "expected_answer": "Los empleados tienen derecho a 22 días laborables..."
  },
  ...
]
"""

import argparse
import json
import sys
from pathlib import Path

import django

# Configurar Django
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from query.service import run_rag_pipeline
from core.search import search_from_settings
from core.token_budget import estimate_tokens


def token_f1(prediction: str, reference: str) -> float:
    """F1 token-level overlap."""
    pred_tokens = set(prediction.lower().split())
    ref_tokens = set(reference.lower().split())
    if not pred_tokens or not ref_tokens:
        return 0.0
    inter = pred_tokens & ref_tokens
    prec = len(inter) / len(pred_tokens)
    rec = len(inter) / len(ref_tokens)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def evaluate(questions_path: Path, top_k: int = 5):
    with open(questions_path, encoding="utf-8") as f:
        data = json.load(f)

    mrr_sum = 0.0
    f1_sum = 0.0
    recall_sum = 0.0
    valid = 0

    for item in data:
        question = item["question"]
        expected_chunks = set(item.get("relevant_chunk_ids", []))
        expected_answer = item.get("expected_answer", "")

        # 1. Retrieval MRR@k
        fused = search_from_settings(question, top_k=top_k)
        retrieved = [item["chunk_id"] for item in fused]

        mrr = 0.0
        for rank, cid in enumerate(retrieved, start=1):
            if cid in expected_chunks:
                mrr = 1.0 / rank
                break
        mrr_sum += mrr

        # 2. Recall@k
        if expected_chunks:
            recall = len([c for c in retrieved if c in expected_chunks]) / len(expected_chunks)
            recall_sum += recall

        # 3. Generación + F1
        result = run_rag_pipeline(question, top_k=top_k)
        if not result.get("degraded") and expected_answer:
            f1 = token_f1(result["answer"], expected_answer)
            f1_sum += f1

        valid += 1
        print(f"Q: {question[:60]}... | MRR={mrr:.3f} | Recall={recall:.3f} | F1={f1:.3f}")

    n = valid or 1
    print("\n--- Resumen ---")
    print(f"Preguntas evaluadas: {valid}")
    print(f"MRR@{top_k}:       {mrr_sum/n:.4f}")
    print(f"Recall@{top_k}:    {recall_sum/n:.4f}")
    print(f"F1-token overlap:  {f1_sum/n:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=Path("data/eval_questions.json"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    evaluate(args.questions, args.top_k)