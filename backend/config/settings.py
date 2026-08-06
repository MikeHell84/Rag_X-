"""Configuración central del proyecto RAG Empresarial.

Toda la configuración sensible se lee desde variables de entorno.
Los valores por defecto están pensados para docker-compose.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RUNNING_TESTS = "pytest" in " ".join(sys.argv) or os.environ.get("DJANGO_TESTING") == "1"


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0") == "1"


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-cambiar-en-produccion")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core.apps.CoreConfig",
    "documents.apps.DocumentsConfig",
    "query.apps.QueryConfig",
    "api.apps.ApiConfig",
    "agents.apps.AgentsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "rag"),
        "USER": os.environ.get("POSTGRES_USER", "rag"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "rag"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
    }
}

if RUNNING_TESTS:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": False,
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.CsrfExemptSessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "300/min"),
        "user": os.environ.get("THROTTLE_USER", "600/min"),
        "query": os.environ.get("THROTTLE_QUERY", "60/min"),
        "upload": os.environ.get("THROTTLE_UPLOAD", "20/min"),
    },
}

# ---------------------------------------------------------------------------
# Configuración del pipeline RAG
# ---------------------------------------------------------------------------
RAG = {
    "EMBEDDING_MODEL": os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "EMBEDDING_DIM": int(os.environ.get("EMBEDDING_DIM", "1536")),
    "LLM_MODEL": os.environ.get("OPENAI_LLM_MODEL", "gpt-4o-mini"),
    "RERANK_MODEL": os.environ.get("OPENAI_RERANK_MODEL", "gpt-4o-mini"),
    "RERANK_STRATEGY": os.environ.get("RERANK_STRATEGY", "llm"),
    "CROSS_ENCODER_MODEL": os.environ.get("CROSS_ENCODER_MODEL", "BAAI/bge-reranker-base"),
    "HYBRID_TOP_K": int(os.environ.get("HYBRID_TOP_K", "20")),
    "RERANK_TOP_K": int(os.environ.get("RERANK_TOP_K", "5")),
    "CHUNK_SIZE": int(os.environ.get("CHUNK_SIZE", "800")),
    "CHUNK_OVERLAP": int(os.environ.get("CHUNK_OVERLAP", "80")),
    "EMBED_BATCH_SIZE": int(os.environ.get("EMBED_BATCH_SIZE", "16")),
    "USE_SEMANTIC_GUARD": env_bool("USE_SEMANTIC_GUARD", False),
    "LLM_TIMEOUT": float(os.environ.get("LLM_TIMEOUT", "60.0")),
    "MAX_CONTEXT_TOKENS": int(os.environ.get("MAX_CONTEXT_TOKENS", "32000")),
    "WHOOSH_INDEX_DIR": os.environ.get("WHOOSH_INDEX_DIR", str(BASE_DIR / "storage" / "whoosh")),
    "MAX_UPLOAD_MB": int(os.environ.get("MAX_UPLOAD_MB", "50")),
    "RRF_K": int(os.environ.get("RRF_K", "60")),
    "VECTOR_EF_SEARCH": int(os.environ.get("VECTOR_EF_SEARCH", "40")),
    "MMR_LAMBDA": float(os.environ.get("MMR_LAMBDA", "0.7")),
    "RECENCY_WINDOW_DAYS": int(os.environ.get("RECENCY_WINDOW_DAYS", "0")),
    "RECENCY_BOOST": float(os.environ.get("RECENCY_BOOST", "0.0")),
    "ENABLE_OCR": env_bool("ENABLE_OCR", False),
}

MODEL_PRICING_USD_PER_1M = {
    "text-embedding-3-small": 0.02,
    "gpt-4o-mini": 0.15,
    "gpt-4o": 2.50,
    "claude-3-5-haiku-20241022": 0.80,
    "claude-3-5-sonnet-20241022": 3.00,
    "claude-3-7-sonnet-20250219": 3.00,
    "claude-sonnet-4-20250514": 3.00,
    "gemini-2.0-flash": 0.10,
    "gemini-2.0-flash-lite": 0.08,
    "gemini-1.5-pro": 1.25,
    "gemini-1.5-flash": 0.08,
    "gemini-2.5-flash": 0.30,
    "gemini-2.5-pro": 1.25,
    "gemini-embedding-001": 0.00,
    "text-embedding-004": 0.00,
    "mistral-large-latest": 2.00,
    "mistral-medium-latest": 2.70,
    "mistral-small-latest": 0.20,
    "mistral-embed": 0.10,
    "llama-3.1-8b-instant": 0.00,
    "llama-3.3-70b-versatile": 0.00,
}

# ---------------------------------------------------------------------------
# Celery: concurrencia, colas y política de reintentos
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}

CELERY_TASK_ROUTES = {
    "documents.tasks.ingest_document": {"queue": "ingestion"},
    "documents.tasks.embed_chunks_batch": {"queue": "embeddings"},
    "documents.tasks.finalize_ingestion": {"queue": "ingestion"},
    "query.tasks.generate_answer": {"queue": "llm"},
}

CELERY_BEAT_SCHEDULE = {
    "purge_old_query_logs": {
        "task": "query.tasks.purge_old_query_logs",
        "schedule": 3600,
    },
}
