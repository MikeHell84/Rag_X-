"""Servicio de chat con el LLM.

- Cliente perezoso y cacheado según el proveedor (OpenAI, Anthropic, Google,
  Mistral, Groq, Ollama, OpenRouter o cualquier API compatible con OpenAI).
- Reintentos con exponential backoff sobre rate limits y timeouts (los errores
  4xx se propagan sin reintentar: son de configuración, no de degradación).
- Circuit breaker para no martillar la API durante degradaciones.
- Medición de tokens y costo estimado (settings.MODEL_PRICING_USD_PER_1M).
"""

import random
import time
from typing import List, Optional

from django.conf import settings

from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .providers import build_client, chat_call, is_client_error, is_transient_error, provider_api_key

MODEL_PRICING = getattr(settings, "MODEL_PRICING_USD_PER_1M", {})


class LLMService:
    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        base_url: str = "",
        use_breaker: bool = True,
    ):
        self.provider = provider or "openai"
        self.api_key = api_key if api_key is not None else provider_api_key(self.provider)
        self.base_url = base_url or ""
        self.use_breaker = use_breaker
        self._client = None
        self.breaker = CircuitBreaker(name=f"llm.{self.provider}")

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.provider, self.api_key, self.base_url)
        return self._client

    def chat_completion(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        retries: int = 5,
    ) -> dict:
        def call() -> dict:
            return chat_call(
                self.provider,
                self.client,
                model,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

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

    @staticmethod
    def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, model: str) -> float:
        price = MODEL_PRICING.get(model, 0.0)
        return (prompt_tokens + completion_tokens) / 1_000_000 * price


class FailoverLLMService:
    """Intenta varios LLMService en orden; si uno falla, pasa al siguiente.

    Cada servicio usa su propio model/api_key/temperature/max_tokens. En la
    cadena se hace 1 intento por agente (failover rápido); la resiliencia la
    aportan los respaldos. Devuelve la respuesta del primero que tenga éxito e
    incluye "model" para saber cuál respondió. Si todos fallan, propaga el
    último error.
    """

    def __init__(self, configs: List[dict]):
        self.configs = configs
        self.services = [
            LLMService(
                provider=cfg.get("provider", "openai"),
                api_key=cfg.get("api_key"),
                base_url=cfg.get("base_url", ""),
            )
            for cfg in configs
        ]

    def chat_completion(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict:
        last_exc: Optional[Exception] = None
        for index, (cfg, svc) in enumerate(zip(self.configs, self.services)):
            try:
                response = svc.chat_completion(
                    messages=messages,
                    model=model or cfg["model"],
                    temperature=cfg.get("temperature", temperature),
                    max_tokens=cfg.get("max_tokens", max_tokens),
                    retries=1 if len(self.services) > 1 else 5,
                )
                response["model"] = model or cfg["model"]
                return response
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc
