<div align="center">

# Asistente RAG Empresarial

**Un sistema de *Retrieval-Augmented Generation* corporativo con arquitectura robusta, escalable y lista para producción.**

RAG + búsqueda híbrida + chunking semántico + re-ranking con LLM, sobre PostgreSQL/pgvector y tareas asíncronas con Celery.

</div>

---

## Índice

- [Título y Descripción](#título-y-descripción)
- [Stack Tecnológico](#stack-tecnológico)
- [Arquitectura del Sistema](#arquitectura-del-sistema)
- [Estrategia de Chunking Avanzada](#estrategia-de-chunking-avanzada)
- [Búsqueda Híbrida y Re-ranking](#búsqueda-híbrida-y-re-ranking)
- [Gestión de Concurrencia y Errores](#gestión-de-concurrencia-y-errores)
- [Despliegue con Docker](#despliegue-con-docker)
- [Casos de Uso y Ejemplo de Flujo](#casos-de-uso-y-ejemplo-de-flujo)
- [Optimización de Costos y Tokens](#optimización-de-costos-y-tokens)
- [Conclusión](#conclusión)

---

## Título y Descripción

**Asistente RAG Empresarial** es un asistente conversacional de *Retrieval-Augmented Generation* (RAG) diseñado para entornos corporativos. Permite subir documentación (PDF, DOCX, Markdown, texto e ingestión por URL), organizarla en **temas aislados** y consultarla mediante lenguaje natural con respuestas fundamentadas en las fuentes, incluyendo citas, métricas de costo y latencia reales.

Propósito y diferenciación:

- **Arquitectura escalable**: separación estricta entre servidor web, workers, base de datos vectorial y broker de mensajes.
- **Precisión**: chunking semántico que respeta la estructura del documento, búsqueda híbrida (vectorial + léxica) y re-ranking con LLM para reducir alucinaciones.
- **Robustez**: *circuit breakers*, *failover* entre agentes de IA, reintentos con *exponential backoff*, y degradación elegante ante fallos.
- **Control de costos**: telemetría por consulta (tokens y costo real en USD), caché de embeddings y presupuestos de contexto.

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| **Web / API** | Python 3.12 · Django 5 · Django REST Framework |
| **Base de datos** | PostgreSQL 16 con extensión **pgvector** |
| **IA / LLM** | OpenAI, Anthropic, Google Gemini, Mistral, Groq, Ollama, OpenRouter (llamadas directas a APIs) |
| **Búsqueda léxica** | Whoosh (índice BM25) |
| **Tareas asíncronas** | Celery 5 + Redis (broker y backend) |
| **Extracción de texto** | pdfplumber, python-docx, trafilatura, ocr con Tesseract (español) |
| **Chunking** | `langchain-text-splitters` as respaldo + lógica semántica propia |
| **Despliegue** | Docker · Docker Compose · gunicorn · nginx |

**Dependencias clave** (`backend/requirements.txt`):

```
Django>=5.0,<6.0
djangorestframework>=3.15
celery[redis]>=5.4
psycopg[binary]>=3.2          # pgvector
openai>=1.40
anthropic>=0.40
google-genai>=1.0
whoosh>=2.7.4
langchain-text-splitters>=0.2
gunicorn>=22.0
trafilatura>=1.8.0            # ingestión por URL
```

---

## Arquitectura del Sistema

El sistema está diseñado con **separación de responsabilidades** para escalar de forma independiente cada componente.

```
                     +------------------------------+
                     |       Frontend Admin         |  nginx :3000
                     +--------------+---------------+
                                    | API REST (Django REST Framework)
+---------------+   enqueue  +-----v------------------+
|  WEB  gunicorn +---------->+       Redis            +   broker :6379
| :8000 (3 wk)   |           |  (colas + cache)       |
+-------+--------+           +-----+------------------+
        | GET/POST                 | Celery worker
        | sync                     | +---------------------------------+
+-------v----------------------+   | |  worker (concurrency=4)        |
|  PostgreSQL 16 + pgvector    |<--+-|  colas: ingestion, embeddings  |
|  (chunk_embeddings, HNSW)    |   | |  y llm                         |
+------------------------------+   | |  + beat (tareas programadas)   |
                                  | +---------------------------------+
                                  |          Flower :5555 (monitor)
                                  +-----------------------------------+
```

### Justificación de diseño

- **Servidor web liviano**: el endpoint de consulta *solo encola* la tarea y responde `202 Accepted`; el cómputo pesado (búsqueda, re-rank, LLM) corre en el worker. El servidor nunca se bloquea ante tráfico concurrente.
- **Colas dedicadas**: rutas Celery separan la ingesta, el embedding y la generación de LLM, permitiendo escalar cada etapa de forma horizontal.
- **Base de datos vectorial**: pgvector sobre PostgreSQL evita un vector DB separado, manteniendo transacciones ACID y backups unificados con el índice HNSW para ANN.
- **Resiliencia**: *acks_late*, reintentos con backoff, *circuit breaker* y *failover* entre agentes garantizan alta disponibilidad ante fallos de proveedores externos.

---

## Estrategia de Chunking Avanzada

Los documentos se fragmentan **respetando la semántica** y la estructura interna, no por cortes ciegos de caracteres. El pipeline (`backend/core/chunking.py`) tiene 4 etapas:

1. **Extracción estructurada** con detección de encabezados (nivel de heading por tamaño de fuente en PDF, estilos `Heading*` en DOCX, regex de encabezados en Markdown/TXT).
2. **`SectionAwareSplitter`**: agrupa contenido por sección; subdivide por párrafos, luego frases, y por último *RecursiveCharacterTextSplitter* sin cortar nunca una frase a la mitad.
3. **`SemanticDriftGuard`**: al fusionar fragmentos pequeños adyacentes, compara la **similitud coseno** del borde: si baja de un umbral (`threshold`, drift semántico), corta aunque quede presupuesto.
4. **`HybridChunker`** orquesta `. Los parámetros por defecto: `chunk_size=800` tokens, `chunk_overlap=80`, `min_chunk=120`.

```python
# backend/core/chunking.py (extracto del orquestador)
class HybridChunker:
    def __init__(self, embed_fn=None, chunk_size=800, chunk_overlap=80, min_chunk=120):
        self.section_splitter = SectionAwareSplitter(chunk_size, chunk_overlap, min_chunk)
        self.guard = SemanticDriftGuard(embed_fn) if embed_fn else None
        self.fallback = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=estimate_tokens,
        )

    def chunk(self, text: str, headings=None):
        structure = Headings(chapters)...
        for block in structure:
            parts = self.section_splitter.split(self, block) or self.fallback.split_text(block)
            yield from parts
```

**Firma del guarda semántico** (con degradación elegante: si el proveedor de embeddings falla, se desactiva y el chunking estructural continúa):

```python
class SemanticDriftGuard:
    def __init__(self, embed_fn, threshold: float = 0.70,
                 min_distance_tokens: int = 60, lookback: int = 3):
        if embed_fn is None:
            self.disabled = True
            return
        # Si el embedding lanza excepción, se desactiva sin abortar la ingesta.
```

> **Lógica personalizada** en `core/chunking.py` evitando depender de heurísticas genéricas; el respaldo con `langchain-text-splitters` solo se usa cuando no hay una subdivisión estructural disponible. Nunca se corta una frase cuando existe un separador.

---

## Búsqueda Híbrida y Re-ranking

El pipeline de consulta combina **búsqueda vectorial** (semántica) y **búsqueda léxica** (BM25), funde los rankings por **RRF** y aplica **re-ranking con LLM** para afinar la relevancia.

### 1. Marcado vectorial de Ada

Usa pgvector con índice **HNSW** y similitud cosénica sobre embeddings de 1536 dimensiones:

```python
# core/vector_store.py (extracto)
SQL = """
    SELECT e.chunk_id, 1 - (e.embedding <=> %s::vector) AS similarity
    FROM chunk_embeddings e
    ORDER BY e.embedding <=> %s::vector ASC
    LIMIT %s
"""
```

### 2. Búsqueda léxica (BM25) de la mañana

Índice Whoosh en disco (`/app/storage/whoosh`) con `MultifieldParser(["content"])`.

### 3. Fusión RRF + MMR

```python
# core/search.py (extracto)
RRF_K = 60

def rrf_fusion(rankings: list[dict[int, float]]):
    scores = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores
```

También se soporta **MMR** (`lambda_ = 0.7`) para diversificar resultados y penalizar fragmentos redundantes, más *boosting* de recencia configurable.

### 4. Re-ranking con LLM

`LLMReranker` pide al modelo puntuar cada candidato 1–10 en una sola llamada (parsea JSON). Presupuesto de contexto recortado dinámicamente:

```python
# core/rerank.py (idea)
scores_json = llm.complete(f"Puntúa cada fragmento 1-10:\n{fragmentos}")
scores = parse_json_block(scores_json)["scores"]
```

> **Cómo reduce alucinaciones**: al recuperar por múltiples vías (semántica + léxica) y fundir con RRF, se aumenta la cobertura; el re-ranking con LLM selecciona solo los `top_k` (por defecto 5) fragmentos más relevantes; y el *system prompt* en español **exige responder usando exclusivamente el contenido recuperado**, con citas `[i]`. Menos ruido en el contexto = repuestas más alineadas y verificables.

---

## Gestión de Concurrencia y Errores

El servidor web **nunca ejecuta cómputo pesado**. La consulta se encola y el worker la procesa de forma asíncrona, con reintentos inteligentes y degradación elegante.

```python
# backend/query/tasks.py
@shared_task(bind=True, max_retries=3, acks_late=True)
def generate_answer(self, question, top_k=None, model=None, document_ids=None, history=None, agent_id=None):
    task_id = self.request.id
    try:
        result = run_rag_pipeline(question, top_k=top_k, document_ids=document_ids,
                                  history=history, agent_id=agent_id,
                                  on_stage=lambda s: publish_stage(task_id, "stage", {"stage": s}))
        publish_stage(task_id, "done", result)
        return result
    except Exception as exc:
        if is_transient_error(exc):                      # 408, 429, 5xx: reintentable
            if self.request.retries >= self.max_retries:
                return _degraded_response(question, exc) # respuesta degradada final
            raise self.retry(exc=exc, countdown=exponential_backoff(self.request.retries))
        return _degraded_response(question, exc)

def exponential_backoff(retries, base=2.0, cap=120.0):
    return min(base ** (retries + 1), cap) + random.uniform(0, 0.5)
```

### Puntos clave

- **`acks_late=True`** y `REJECT_ON_WORKER_LOST=True`: si el worker cae, la tarea se repone, no se pierde.
- **Reintentos solo a errores transitarios** (`is_transient_error`: 408/429/5xx) para no repetir errores de cliente.
- **Circuit breaker** en `core/llm.py` (umbral de fallos + cooldown) que abre/corre/cierra ante un proveedor no saludable.
- **Failover entre agentes**: `FailoverLLMService` intenta el primario y los respaldos aislados por tipo.
- **Progreso en tiempo real** vía Redis pub/sub (`rag:query:<id>`): eventos `stage`/`done`/`error` para streaming SSE.

---

## Despliegue con Docker

### `docker-compose.yml` (7 servicios)

```yaml
name: rag-empresarial

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-rag}
      POSTGRES_USER: ${POSTGRES_USER:-rag}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-rag}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-rag} -d ${POSTGRES_DB:-rag}"]

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru --appendonly yes

  migrate:   # one-shot: DB + estáticos
    build: ./backend
    command: sh -c "python manage.py migrate --noinput && python manage.py collectstatic --noinput"

  web:       # API + frontend en :8000
    build: ./backend
    command: sh -c "`python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --threads 4 --timeout 120""
    ports: ["8000:8000"]

  worker:    # cómputo pesado
    build: ./backend
    command: celery -A config worker --queues=embeddings,llm,ingestion --concurrency=4 --max-tasks-per-child=50

  beat:      # tareas programadas (purga del diario de consultas)
    build: ./backend
    command: celery -A config beat --schedule=/app/storage/celerybeat-schedule

  flower:    # monitor WebUI de colas :5555
    build: ./backend
    command: celery -A config flower --port=5555 --basic-auth=admin:${FLOWER_PASSWORD:-admin}
    ports: ["5555:5555"]

  admin:     # Frontend de gestión :3000
    build: ./frontend
    ports: ["3000:80"]

volumes:
  pgdata:
  redisdata:
  rag_storage:
  rag_media:
```

### Instalación y ejecución

```bash
# 1. Variables de entorno (LLM/embeddings, credenciales DB, etc.)
cp .env.example .env

# 2. Construir y levantar todo
docker compose build
docker compose up -d

# 3. Crear el superusuario de administración (si hace falta)
docker compose exec web python manage.py createsuperuser

# 4. Monitor de colas
open http://localhost:5555        # Flower
open http://localhost:8000        # Asistente Web
open http://localhost:3000        # Panel de gestión
```

> Nota: la ingestion de imágenes/PDF escaneados requiere Tesseract (instalado en la imagen con `tesseract-ocr-spa`) y `poppler-utils` para PDF a imagen.

---

## Casos de Uso y Ejemplo de Flujo

### 1. El usuario sube/documents o un enlace

```bash
# Subir un PDF asignado a un tema
curl -X POST http://localhost:8000/api/documents/upload/ \
  -H "X-Tenant-Id: 1" \
  -F "file=@informe.pdf" -F "topic=Finanzas"

# Ingestion por URL (descarga + conversión a Markdown)
curl -X POST http://localhost:8000/api/documents/from-url/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.datacamp.com/es/blog/how-to-become-computer-programmer", "topic": "Tecnologia"}'
```

La ingesta se encola (`DocumentUploadView` hacia la tarea `ingest_document`): un DAG Celery con `chord` fragmenta y embebe los chunks en paralelo, actualiza pgvector **y** Whoosh, y marca el documento `READY` o `FAILED`.

### 2. Búsqueda híbrida

```bash
curl -X POST http://localhost:8000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué habilidades se necesitan para ser programador?",
       "topic": "Tecnologia",
       "history": []}'
```

El endpoint responde `202` con un `task_id`; el worker ejeEC búsqueda híbrida (vectorial + BM25), la fusión RRF, el re-ranking LLM y la generación. El frontend consume la evolución por SSE/pub-sub.

### 3. Respuesta generada (con citas, tokens y costo)

```json
{
  "answer": "Según la documentación adjunta, para ser programador se necesitan "
            "fundamentos de lógica, un lenguaje de programación y práctica "
            "constante con proyectos reales [1][3].",
  "sources": [
    {"document": "como_ser_programador.md", "section": "Introducción", "score": 4.2},
    {"document": "rutas_aprendizaje.md", "page": 2, "score": 3.8}
  ],
  "tokens_prompt": 4210,
  "tokens_completion": 340,
  "cost_usd": 0.0021,
  "latency_ms": 3400,
  "model": "anthropic/claude-3-5-sonnet"
}
```

---

## Optimización de Costos y Tokens

| Estrategia | Implementación |
|---|---|
| **Caché de embeddings** | `@lru_cache(maxsize=2048)` por hash de texto en `EmbeddingService.embed`: no se re-generan embeddings repetidos. |
| **Presupuesto de contexto** | `_build_messages` recorta iterativamente el contexto al presupuesto (`max_context_tokens`) antes de llamar al LLM. |
| **Re-ranking con presupuesto** | `LLMReranker` trunca candidatos a 1200 caracteres y calcula el contexto disponible dinámicamente. |
| **Telemetría de costo** | `MODEL_PRICING_USD_PER_1M` calcula el costo real por tokens y lo registra en `QueryLog`. |
| **Embeddings persistentes** | Los vectores viven en pgvector (no se regeneran entre consultas) y se upsertan por `content_hash` (deduplicación). |
| **Reintentos con backoff** | evita re-intencións costosas en hora pico y múltiples llamadas redundantes por rate limit. |
| **Elección de modelos** | Defaults económicos (`text-embedding-3-small`, `gpt-4o-mini`), configurables por entorno. |

---

## Conclusión

Este proyecto demuestra experiencia real en **IA aplicada a producción**, no una implementación básica de RAG:

- **Suma de componentes de producción**: chunking semántico, búsqueda híbrida con fusión RRF, re-ranking LLM, *circuit breakers*, *failover*, reintentos y *auditing*.
- **Escala real**: separación en servicios, coleras dedicadas, auto-obtención de tareas asíncronas y bedirecta con Celery + Redis.
- **Control de costos y telemetría**: los `QueryLog` registran cada consulta con tokens y costo usados — audificable.
- **Seguridad**: cifrado (Fernet/AES) de API keys por agente, cifrado de credenciales, y control de visibilidad de conversaciones y temas.
- **Aislamiento por tema**: cada **tema aísla** su propia documentación, sesiones y consultas — no se mezclan conocimientos entre dominios.

La diferencia frente a *implementaciones básicas de RAG* (naive split + cosine sólo) queda en evidencia en cada etapa del pipeline: producción de calidad de la ingesta, multi-vía retrieval, afinamiento con LLM, resiliencia ante fallos externos y control de costos medible — todo contenedorizado y operativamente desplegable.

---

## Licencia

Proyecto interno del equipo. Uso restringido a los términos establecidos por la organización.