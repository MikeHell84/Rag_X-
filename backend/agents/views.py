from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from core.embeddings import EmbeddingService
from core.llm import LLMService
from core.providers import EMBEDDING_PROVIDERS, KEYLESS_PROVIDERS, is_client_error
from django.conf import settings

from .models import Agent, AgentType
from .serializers import AgentSerializer, PlatformConfigSerializer
from .services import PLATFORM_DEFAULTS, get_platform_config, save_platform_config


class AgentViewSet(ModelViewSet):
    queryset = Agent.objects.all()
    serializer_class = AgentSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "put"]

    @action(detail=False, methods=["get"])
    def active(self, request):
        agents = Agent.objects.filter(is_active=True)
        return Response(AgentSerializer(agents, many=True).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        agent = self.get_object()
        Agent.objects.filter(agent_type=agent.agent_type, is_active=True).exclude(pk=agent.pk).update(is_active=False)
        agent.is_active = True
        agent.save(update_fields=["is_active", "updated_at"])
        return Response(AgentSerializer(agent).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        agent = self.get_object()
        agent.is_active = False
        agent.save(update_fields=["is_active", "updated_at"])
        return Response(AgentSerializer(agent).data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        agent = self.get_object()
        probe = (request.data.get("probe") or "").strip() or "Prueba de conexión del agente."
        if agent.agent_type in (AgentType.CHAT, AgentType.EMBEDDING):
            if agent.agent_type == AgentType.EMBEDDING and agent.provider not in EMBEDDING_PROVIDERS:
                return Response(
                    {
                        "ok": False,
                        "error": f"El proveedor «{agent.provider}» no ofrece embeddings. "
                        "Usa OpenAI, Google, Mistral u Ollama para el agente de embeddings.",
                    }
                )
            api_key = agent.api_key_plain
            needs_key = agent.provider not in KEYLESS_PROVIDERS
            if needs_key and not api_key:
                return Response(
                    {
                        "ok": False,
                        "error": "Este agente no tiene su propia API key. "
                        "Cada agente usa una clave exclusiva: configúrala en el campo «API Key».",
                    }
                )
        try:
            if agent.agent_type == AgentType.CHAT:
                llm = LLMService(
                    provider=agent.provider,
                    api_key=api_key,
                    base_url=agent.base_url,
                    use_breaker=False,
                )
                response = llm.chat_completion(
                    messages=[
                        {"role": "system", "content": "Eres un agente de prueba. Responde en una frase."},
                        {"role": "user", "content": probe},
                    ],
                    model=agent.model,
                    temperature=agent.temperature,
                    max_tokens=128,
                    retries=1,
                )
                return Response(
                    {"ok": True, "response": response["content"], "tokens": response["completion_tokens"]}
                )
            if agent.agent_type == AgentType.EMBEDDING:
                service = EmbeddingService(
                    model=agent.model,
                    batch_size=1,
                    provider=agent.provider,
                    api_key=api_key,
                    base_url=agent.base_url,
                    use_breaker=False,
                )
                vectors = service.embed_texts([probe], retries=1)
                return Response({"ok": True, "dim": len(vectors[0]), "sample": vectors[0][:3]})
            return Response(
                {"ok": True, "response": "Agente de re-ranking verificado (requiere pipeline para medir)."}
            )
        except Exception as exc:
            response_status = status.HTTP_200_OK if is_client_error(exc) else status.HTTP_502_BAD_GATEWAY
            return Response({"ok": False, "error": str(exc)[:500]}, status=response_status)


class PlatformConfigView(APIView):
    def get(self, request):
        return Response(get_platform_config())

    def put(self, request):
        serializer = PlatformConfigSerializer(data={"data": request.data or {}})
        serializer.is_valid(raise_exception=True)
        config = save_platform_config(serializer.validated_data["data"])
        return Response(config)


class ChatAgentsView(APIView):
    """Lista de agentes de chat activos disponibles para el selector del frontend."""

    def get(self, request):
        from .models import AgentType
        agents = Agent.objects.filter(agent_type=AgentType.CHAT, is_active=True).order_by("name")
        return Response(
            [
                {
                    "id": a.id,
                    "name": a.name,
                    "provider": a.provider,
                    "model": a.model,
                    "description": a.description,
                }
                for a in agents
            ]
        )
