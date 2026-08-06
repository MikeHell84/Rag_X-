import pytest

from core.providers import (
    ProviderConfigError,
    _split_messages,
    build_client,
    is_client_error,
    is_transient_error,
    provider_api_key,
    resolve_base_url,
)


class _FakeError(Exception):
    def __init__(self, status_code):
        super().__init__("error")
        self.status_code = status_code


def test_is_client_error_classifies_4xx_only():
    assert is_client_error(_FakeError(401)) is True
    assert is_client_error(_FakeError(403)) is True
    assert is_client_error(_FakeError(429)) is False
    assert is_client_error(_FakeError(408)) is False
    assert is_client_error(_FakeError(500)) is False
    assert is_client_error(_FakeError("unset")) is False
    assert is_client_error(RuntimeError("boom")) is False


class _GrpcError(Exception):
    def __init__(self, status):
        super().__init__("error")
        self.status = status


def test_is_client_error_recognizes_google_grpc_statuses():
    assert is_client_error(_GrpcError("PERMISSION_DENIED")) is True
    assert is_client_error(_GrpcError("UNAUTHENTICATED")) is True
    assert is_client_error(_GrpcError("RESOURCE_EXHAUSTED")) is False
    assert is_client_error(_GrpcError("UNAVAILABLE")) is False
    assert is_client_error(_GrpcError("DEADLINE_EXCEEDED")) is False


def test_is_transient_error_retries_quota_5xx_and_timeouts():
    assert is_transient_error(_FakeError(429)) is True
    assert is_transient_error(_FakeError(500)) is True
    assert is_transient_error(_FakeError(503)) is True
    assert is_transient_error(_FakeError(401)) is False
    assert is_transient_error(_GrpcError("RESOURCE_EXHAUSTED")) is True
    assert is_transient_error(_GrpcError("RATE_LIMITED")) is True
    assert is_transient_error(_GrpcError("PERMISSION_DENIED")) is False
    assert is_transient_error(ProviderConfigError("sin key")) is False
    assert is_transient_error(RuntimeError("boom")) is False


def test_split_messages_separa_system():
    system, rest = _split_messages(
        [
            {"role": "system", "content": "Eres un asistente"},
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¿Qué tal?"},
        ]
    )
    assert system == "Eres un asistente"
    assert rest == [{"role": "user", "content": "Hola"}, {"role": "assistant", "content": "¿Qué tal?"}]


def test_resolve_base_url_predefined_and_custom():
    assert resolve_base_url("mistral") == "https://api.mistral.ai/v1"
    assert resolve_base_url("ollama") == "http://host.docker.internal:11434/v1"
    assert resolve_base_url("openai") == ""
    assert resolve_base_url("custom", "https://mi.gateway/v1") == "https://mi.gateway/v1"


def test_provider_api_key_prefers_agent_key():
    assert provider_api_key("anthropic", "sk-agent") == "sk-agent"


def test_build_client_requires_key_for_anthropic():
    with pytest.raises(ProviderConfigError):
        build_client("anthropic", api_key="")


def test_build_client_openai_compatible_without_key():
    client = build_client("ollama", api_key="", base_url="")
    assert client is not None


def test_build_client_requires_key_for_openai_compatible():
    with pytest.raises(ProviderConfigError):
        build_client("openai", api_key="", base_url="")
    with pytest.raises(ProviderConfigError):
        build_client("custom", api_key="", base_url="https://mi.gateway/v1")


def test_config_error_is_client_error():
    assert is_client_error(ProviderConfigError("sin key")) is True


def test_build_client_google_requires_key():
    with pytest.raises(ProviderConfigError):
        build_client("google", api_key="")
