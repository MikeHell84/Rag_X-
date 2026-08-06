"""Re-ranking de los candidatos recuperados.

Dos estrategias intercambiables (RAG["RERANK_STRATEGY"]):

- "llm": el propio modelo de lenguaje puntúa cada candidato (1-10) respecto
  a la pregunta en una sola llamada, devolviendo un JSON {scores: [...]}.
- "cross-encoder": stub de punto de extensión para un cross-encoder local
  (p. ej. BAAI/bge-reranker-base) con sentence-transformers.

Ambas degradan con elegancia: si el proveedor falla, se conserva el orden
de la fusión RRF en lugar de devolver un error.
"""

import json
import re
from typing import List, Optional

from django.conf import settings

from .llm import LLMService
from .token_budget import estimate_tokens, truncate_to_budget

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

RERANK_PROMPT = """Eres un re-ranker de búsqueda. Dada una pregunta y una lista de fragmentos
numerados, puntúa CADA fragmento del 1 al 10 según su relevancia para responder la pregunta
(10 = imprescindible, 1 = irrelevante). Sé estricto y discriminante.

Pregunta: {question}

Fragmentos:
{numbered_chunks}

Devuelve ÚNICAMENTE un JSON válido con la forma: {{"scores": [9, 3, 7, ...]}} donde la
posición i corresponde al fragmento i."""


class LLMReranker:
    def __init__(self, model: Optional[str] = None, llm: Optional[LLMService] = None, max_candidates: int = 30):
        self.model = model or settings.RAG["RERANK_MODEL"]
        self.llm = llm or LLMService()
        self.max_candidates = max_candidates

    def rerank(self, question: str, chunks: List[dict], top_n: int = 5) -> List[dict]:
        if not chunks:
            return []
        candidates = chunks[: self.max_candidates]
        max_content_chars = 1200
        numbered = "\n".join(
            f"[{i}] {self._short(c['content'], max_content_chars)}" for i, c in enumerate(candidates, start=1)
        )
        budget = settings.RAG["MAX_CONTEXT_TOKENS"] - estimate_tokens(question) - 512
        prompt = truncate_to_budget(RERANK_PROMPT.format(question=question, numbered_chunks=numbered), budget)

        try:
            response = self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": "Devolver siempre JSON válido, sin texto adicional."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                temperature=0.0,
            )
            scores = self._parse_scores(response["content"])
        except Exception:
            return candidates[:top_n]

        scored = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
        return [chunk for chunk, _score in scored[:top_n]]

    @staticmethod
    def _short(content: str, max_chars: int) -> str:
        return content if len(content) <= max_chars else content[:max_chars] + "…"

    @staticmethod
    def _parse_scores(raw: str) -> List[float]:
        match = JSON_BLOCK_RE.search(raw or "")
        if not match:
            raise ValueError("no se encontró JSON en la respuesta del re-ranker")
        data = json.loads(match.group(0))
        return [float(value) for value in data["scores"]]
