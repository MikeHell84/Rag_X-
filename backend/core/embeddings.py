"""Servicio de embeddings con manejo robusto de la API.

- Cliente OpenAI perezoso (no rompe el import sin API key).
- Batch token-aware: divide la entrada para no superar el límite por request.
- Retry con exponential backoff + jitter sobre 429/timeouts/errores 5xx.
- Circuit breaker para no martillar la API cuando está degradada.
- Caché en memoria por hash del texto (evita re-embedding de duplicados).
"""

import hashlib
import random
import time
from functools import lru_cache
from typing import List, Optional

from django.conf import settings

from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .providers import (
    EMBEDDING_PROVIDERS,
    build_client,
    embed_call,
    is_client_error,
    provider_api_key,
)
from .token_budget import estimate_tokens

RAG = settings.RAG

MAX_TOKENS_PER_REQUEST = 8000


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingService:
    def __init__(
        self,
        model: str,
        batch_size: int = 16,
        provider: str = "openai",
        api_key: Optional[str] = None,
        base_url: str = "",
        use_breaker: bool = True,
        embedding_dim: Optional[int] = None,
    ):
        self.model = model
        self.batch_size = batch_size
        self.provider = provider or "openai"
        self.api_key = api_key if api_key is not None else provider_api_key(self.provider)
        self.base_url = base_url or ""
        self.use_breaker = use_breaker
        self.embedding_dim = embedding_dim
        self._client = None
        self.breaker = CircuitBreaker(name=f"embeddings.{self.provider}", cooldown_seconds=60.0)

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.provider, self.api_key, self.base_url)
        return self._client

    def embed_texts(self, texts: List[str], retries: int = 6) -> List[List[float]]:
        vectors: List[List[float]] = []
        batch: List[str] = []
        batch_tokens = 0
        for text in texts:
            tokens = estimate_tokens(text)
            if batch and (len(batch) >= self.batch_size or batch_tokens + tokens > MAX_TOKENS_PER_REQUEST):
                vectors.extend(self._embed_batch(batch, retries=retries))
                batch, batch_tokens = [], 0
            batch.append(text)
            batch_tokens += tokens
        if batch:
            vectors.extend(self._embed_batch(batch, retries=retries))
        return vectors

    def _embed_batch(self, texts: List[str], retries: int = 6) -> List[List[float]]:
        def call() -> List[List[float]]:
            return embed_call(self.provider, self.client, self.model, texts, dim=self.embedding_dim)

        delay = 1.0
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                if self.use_breaker:
                    return self.breaker.run(call, failure_predicate=lambda exc: not is_client_error(exc))
                return call()
            except CircuitOpenError:
                raise
            except Exception as exc:
                if is_client_error(exc):
                    raise
                last_exc = exc
                time.sleep(delay + random.uniform(0, 0.5))
            delay = min(delay * 2, 60)
        raise last_exc

    @lru_cache(maxsize=2048)
    def _embed_single_cached(self, text: str) -> List[float]:
        return self._embed_batch([text])[0]

    def embed(self, text: str) -> List[float]:
        return list(self._embed_single_cached(text))


def get_embedding_service() -> EmbeddingService:
    """Servicio de embeddings con failover sobre la cadena de agentes activa.

    Solo entran en la cadena los agentes cuyo proveedor soporte embeddings
    (OpenAI, Google, Mistral, Ollama y APIs compatibles).
    """
    services: List[EmbeddingService] = []
    try:
        from agents.services import get_embedding_agent_chain

        chain = get_embedding_agent_chain()
        if chain:
            batch = RAG["EMBED_BATCH_SIZE"]
            services = [
                EmbeddingService(
                    model=agent.model,
                    batch_size=batch,
                    provider=agent.provider,
                    api_key=agent.api_key_plain,
                    base_url=agent.base_url,
                    embedding_dim=agent.embedding_dim,
                )
                for agent in chain
                if agent.provider in EMBEDDING_PROVIDERS
            ]
    except Exception:
        pass
    if not services:
        services = [
            EmbeddingService(
                model=RAG["EMBEDDING_MODEL"],
                batch_size=RAG["EMBED_BATCH_SIZE"],
                embedding_dim=RAG["EMBEDDING_DIM"],
            )
        ]
    if len(services) == 1:
        return services[0]
    return FailoverEmbeddingService(services)


class FailoverEmbeddingService:
    """Intenta varios EmbeddingService en orden; ante fallo pasa al siguiente."""

    def __init__(self, services: List[EmbeddingService]):
        self.services = services
        self.model = services[0].model if services else None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        last_exc: Optional[Exception] = None
        for service in self.services:
            try:
                retries = 1 if len(self.services) > 1 else 6
                return service.embed_texts(texts, retries=retries)
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc

    def embed(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]
