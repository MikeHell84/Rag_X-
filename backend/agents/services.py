"""Acceso a la configuración operativa de agentes IA.

El pipeline RAG lee aquí qué agente está activo por tipo (chat / embeddings /
re-ranking) y los parámetros globales de recuperación. Si no hay agente
configurado, se degrada a los valores por defecto de settings.RAG.
"""

from typing import Optional

from .models import Agent, AgentType, PlatformConfig

PLATFORM_DEFAULTS = {
    "chunk_size": 800,
    "chunk_overlap": 80,
    "hybrid_top_k": 20,
    "rerank_top_k": 5,
    "embed_batch_size": 16,
    "max_context_tokens": 32000,
    "use_semantic_guard": False,
}

PLATFORM_CONFIG_KEY = "default"


def get_active_agent(agent_type) -> Optional[Agent]:
    return Agent.objects.filter(agent_type=agent_type, is_active=True).first()


def get_active_agents(agent_type) -> list:
    """Agentes de un tipo ordenados para failover: primario (is_active) + respaldos.

    El primario va primero; los respaldos (`is_fallback=True`) después, ordenados
    por `fallback_order` ascendente. Si el primario no existe, se usan los respaldos.
    """
    agents = list(Agent.objects.filter(agent_type=agent_type, is_active=True))
    agents += list(
        Agent.objects.filter(agent_type=agent_type, is_fallback=True).order_by("fallback_order", "id")
    )
    seen: dict = {}
    for agent in agents:
        seen.setdefault(agent.pk, agent)
    return list(seen.values())


def get_chat_agent() -> Optional[Agent]:
    return get_active_agent(AgentType.CHAT)


def get_chat_agent_chain() -> list:
    return get_active_agents(AgentType.CHAT)


def get_embedding_agent() -> Optional[Agent]:
    return get_active_agent(AgentType.EMBEDDING)


def get_embedding_agent_chain() -> list:
    return get_active_agents(AgentType.EMBEDDING)


def get_reranker_agent() -> Optional[Agent]:
    return get_active_agent(AgentType.RERANKER)


def get_reranker_agent_chain() -> list:
    return get_active_agents(AgentType.RERANKER)


def get_platform_config() -> dict:
    config = PlatformConfig.objects.filter(key=PLATFORM_CONFIG_KEY).first()
    data = config.data if config else {}
    return {**PLATFORM_DEFAULTS, **data}


def save_platform_config(data: dict) -> dict:
    config, _ = PlatformConfig.objects.get_or_create(key=PLATFORM_CONFIG_KEY)
    config.data = data
    config.save(update_fields=["data", "updated_at"])
    return {**PLATFORM_DEFAULTS, **config.data}
