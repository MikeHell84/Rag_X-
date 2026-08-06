"""Abstracción de proveedores LLM/embeddings.

Cada proveedor expone un cliente y llamadas normalizadas (`chat_call` y
`embed_call`) que devuelven la misma estructura interna, para que el pipeline
y el failover no dependan del SDK concreto. Los SDKs se importan de forma
perezosa para no romper el arranque si falta una dependencia.
"""

import os
from typing import List, Optional, Tuple

PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "google": "Google (Gemini)",
    "mistral": "Mistral",
    "groq": "Groq",
    "ollama": "Ollama (local)",
    "openrouter": "OpenRouter",
    "custom": "OpenAI-compatible (base_url)",
}

OPENAI_COMPATIBLE_BASE_URLS = {
    "mistral": "https://api.mistral.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://host.docker.internal:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

ENV_KEY_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "ollama": None,
    "openrouter": "OPENROUTER_API_KEY",
    "custom": "CUSTOM_API_KEY",
}

CHAT_PROVIDERS = set(PROVIDER_LABELS)
EMBEDDING_PROVIDERS = {"openai", "google", "mistral", "ollama", "custom"}
KEYLESS_PROVIDERS = {"ollama"}


class ProviderConfigError(Exception):
    """Error de configuración del agente (falta API key, proveedor sin soporte).

    Es de la aplicación, no del proveedor: no se reintenta ni abre el circuit breaker.
    """


def provider_api_key(provider: str, agent_key: str = "") -> str:
    if agent_key:
        return agent_key
    env_name = ENV_KEY_BY_PROVIDER.get(provider or "openai")
    return os.environ.get(env_name, "") if env_name else ""


def resolve_base_url(provider: str, base_url: str = "") -> str:
    return base_url or OPENAI_COMPATIBLE_BASE_URLS.get(provider or "openai", "")


def build_client(provider: str, api_key: str = "", base_url: str = ""):
    provider = provider or "openai"
    if provider == "anthropic":
        if not api_key:
            raise ProviderConfigError(
                "Falta la API key del proveedor Anthropic (configúrala en el agente)."
            )
        import anthropic

        return anthropic.Anthropic(api_key=api_key)
    if provider == "google":
        if not api_key:
            raise ProviderConfigError(
                "Falta la API key del proveedor Google (configúrala en el agente)."
            )
        from google import genai

        return genai.Client(api_key=api_key)
    import openai

    if not api_key and provider != "ollama":
        raise ProviderConfigError(
            f"Falta la API key del proveedor «{PROVIDER_LABELS.get(provider, provider)}». "
            "Cada agente usa su propia clave (campo «API Key»)."
        )
    return openai.OpenAI(
        api_key=api_key or "dummy",
        base_url=resolve_base_url(provider, base_url) or None,
    )


def _split_messages(messages: List[dict]) -> Tuple[str, List[dict]]:
    system_parts: List[str] = []
    rest: List[dict] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant") and content:
            rest.append({"role": role, "content": content})
    return "\n".join(system_parts).strip(), rest


def chat_call(
    provider: str,
    client,
    model: str,
    messages: List[dict],
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> dict:
    provider = provider or "openai"
    if provider == "anthropic":
        system, msgs = _split_messages(messages)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or None,
            messages=msgs,
        )
        content = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        usage = getattr(response, "usage", None)
        return {
            "content": content,
            "prompt_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        }
    if provider == "google":
        from google import genai

        system, msgs = _split_messages(messages)
        contents = msgs[-1]["content"] if msgs else ""
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=genai.types.GenerateContentConfig(
                system_instruction=system or None,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        return {
            "content": getattr(response, "text", "") or "",
            "prompt_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
            "completion_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
        }
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return {
        "content": response.choices[0].message.content or "",
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
    }


def embed_call(
    provider: str, client, model: str, texts: List[str], dim: Optional[int] = None
) -> List[List[float]]:
    provider = provider or "openai"
    if provider == "google":
        if dim is not None:
            from google import genai

            response = client.models.embed_content(
                model=model,
                contents=list(texts),
                config=genai.types.EmbedContentConfig(output_dimensionality=dim),
            )
        else:
            response = client.models.embed_content(model=model, contents=list(texts))
        embeddings = getattr(response, "embeddings", None) or []
        if embeddings and hasattr(embeddings[0], "values"):
            return [[float(v) for v in item.values] for item in embeddings]
        return [list(item) for item in embeddings]
    response = client.embeddings.create(model=model, input=list(texts))
    return [item.embedding for item in response.data]


# Estados gRPC equivalentes a errores HTTP 4xx (usados por google-genai).
# Son de configuración/cliente: NO se reintentan ni abren el circuit breaker.
_GRPC_CLIENT_ERROR_STATUSES = {
    "INVALID_ARGUMENT",
    "NOT_FOUND",
    "ALREADY_EXISTS",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "FAILED_PRECONDITION",
    "OUT_OF_RANGE",
}

# Estados gRPC transitorios: quota, rate limit, caídas parciales del proveedor.
# SÍ se reintentan con backoff; si persisten, abren el breaker (para no martillar).
_GRPC_TRANSIENT_STATUSES = {
    "RESOURCE_EXHAUSTED",
    "RATE_LIMITED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
    "ABORTED",
    "UNKNOWN",
    "CANCELLED",
    "DATA_LOSS",
}


def is_client_error(exc: Exception) -> bool:
    """Errores 4xx o de configuración del agente: no se reintentan ni abren el breaker."""
    if isinstance(exc, ProviderConfigError):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500 and status != 408 and status != 429:
        return True
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.upper() in _GRPC_CLIENT_ERROR_STATUSES:
        return True
    return False


def is_transient_error(exc: Exception) -> bool:
    """Errores transitorios (quota, rate limit, 5xx, timeout, red): reintentables.

    El usuario ve "degradado" si persisten; no es un error de configuración.
    """
    if isinstance(exc, ProviderConfigError):
        return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in (408, 429) or 500 <= status < 600
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.upper() in _GRPC_TRANSIENT_STATUSES:
        return True
    import openai

    return isinstance(
        exc,
        (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.InternalServerError,
        ),
    )
