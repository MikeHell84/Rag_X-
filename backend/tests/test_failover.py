from unittest.mock import MagicMock

import pytest

from core.embeddings import FailoverEmbeddingService
from core.llm import FailoverLLMService, LLMService


def _svc(model, fail=False, ok=None):
    service = MagicMock()
    service.model = model
    if fail:
        service.chat_completion.side_effect = RuntimeError("fallo")
    else:
        service.chat_completion.return_value = {"content": f"respuesta {model}"}
    if ok is not None:
        service.chat_completion.return_value = ok
    return service


def test_failover_llm_uses_fallback_when_primary_fails():
    primary = _svc("a", fail=True)
    backup = _svc("b")
    fover = FailoverLLMService([{"model": "a"}, {"model": "b"}])
    fover.services = [primary, backup]

    result = fover.chat_completion(messages=[{"role": "user", "content": "hola"}])

    assert result["content"] == "respuesta b"
    assert result["model"] == "b"
    primary.chat_completion.assert_called_once()
    backup.chat_completion.assert_called_once()


def test_failover_llm_uses_primary_when_it_succeeds():
    primary = _svc("a")
    backup = _svc("b")
    fover = FailoverLLMService([{"model": "a"}, {"model": "b"}])
    fover.services = [primary, backup]

    result = fover.chat_completion(messages=[{"role": "user", "content": "hola"}])

    assert result["model"] == "a"
    backup.chat_completion.assert_not_called()


def test_failover_llm_raises_when_all_fail():
    primary = _svc("a", fail=True)
    backup = _svc("b", fail=True)
    fover = FailoverLLMService([{"model": "a"}, {"model": "b"}])
    fover.services = [primary, backup]

    with pytest.raises(RuntimeError):
        fover.chat_completion(messages=[])


def test_failover_embedding_uses_fallback():
    primary = MagicMock()
    primary.embed_texts.side_effect = RuntimeError("proveedor caído")
    backup = MagicMock()
    backup.embed_texts.return_value = [[0.1, 0.2]]

    fover = FailoverEmbeddingService([primary, backup])
    result = fover.embed_texts(["texto"])

    assert result == [[0.1, 0.2]]
    primary.embed_texts.assert_called_once()
    backup.embed_texts.assert_called_once()
    assert fover.model == primary.model


def test_llm_bypasses_breaker_when_use_breaker_false():
    service = LLMService(provider="openai", api_key="sk-x", use_breaker=False)
    service.breaker._state = service.breaker.OPEN

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))],
        usage=MagicMock(prompt_tokens=1, completion_tokens=1),
    )
    service._client = fake_client

    result = service.chat_completion(messages=[{"role": "user", "content": "hola"}], model="m", retries=1)

    assert result["content"] == "ok"
    fake_client.chat.completions.create.assert_called_once()
