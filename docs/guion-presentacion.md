# Guion de presentación — Asistente RAG Empresarial

Guion completo para presentar el proyecto ante un reclutador o en una entrevista técnica.

---

## 1. Gancho inicial (10 segundos)

> «He construido un sistema RAG (Retrieval-Augmented Generation) empresarial: un asistente conversacional que permite a una empresa subir su documentación y hacerle preguntas en lenguaje natural, obteniendo respuestas con citas, control de costos y métricas reales, listo para producción.»

---

## 2. El problema que resuelve (por qué importa)

- Un modelo general no conoce la documentación privada de una empresa.
- Necesitas que las respuestas estén **fundamentadas** en esa documentación, sin alucinaciones y con **trazabilidad** (citas a la fuente).
- El objetivo: convertir la documentación corporativa en un activo consultable de forma segura.

---

## 3. Arquitectura (demuestra el diseño)

Separé la ejecución en capas para que cada componente escale de forma independiente:

- **Web / API (Gunicorn + Django REST Framework):** solo encola la tarea y responde `202 Accepted`; nunca se bloquea ante tráfico concurrente.
- **Tareas asíncronas (Celery 5 + Redis)**: colas dedicadas por etapa (`ingestion`, `embeddings`, `llm`).
- **Base de datos vectorial (PostgreSQL 16 + pgvector)**: índice HNSW para búsqueda por similitud (ANN), con transacciones ACID y backups unificados.
- **Búsqueda léxica (Whoosh BM25)**: relevancia por coincidencia de términos.
- **Frontend**: panel de administración en React/Vite servido con nginx.

---

## 4. La parte técnica de mayor valor

### a) Chunking semántico (`backend/core/chunking.py`)

> «No fragmento por cortes ciegos de caracteres; respeto la estructura interna del documento.»

1. **Extracción estructurada**: detecta encabezados (por tamaño de fuente en PDF, estilos `Heading*` en DOCX, regex en Markdown/TXT).
2. **`SectionAwareSplitter`**: agrupa por sección; subdivide párrafo → frase → *RecursiveCharacterTextSplitter* sin cortar nunca una frase a la mitad.
3. **`SemanticDriftGuard`**: al fusionar fragmentos pequeños adyacentes compara la similitud coseno del borde; si baja de un umbral, corta aunque quede presupuesto (evita mezclar temas).
4. **`HybridChunker`**: orquesta las etapas anteriores. Parámetros por defecto: `chunk_size=800`, `overlap=80`, `min_chunk=120`.

### b) Búsqueda híbrida con RRF (`backend/core/search.py`)

> «Combino dos mundos: relevancia semántica y coincidencia exacta.»

- Fusiona resultados **vectoriales** (pgvector) y **léxicos** (BM25) mediante **RRF (Reciprocal Rank Fusion)** con K=60.
- Aplica **MMR** para diversificar los resultados y evitar redundancia.

### c) Re-ranking con LLM (`backend/core/rerank.py`)

- Después de obtener los candidatos, una segunda pasada los reordena por relevancia real.
- Trunca cada candidato a 1200 caracteres y calcula el presupuesto de contexto de forma dinámica para controlar costo.

### d) Robustez (`backend/core/circuit_breaker.py`, `backend/core/providers.py`)

- **Circuit breaker** sobre llamadas a proveedores externos.
- **Failover** entre proveedores (OpenAI, Anthropic, Gemini, Mistral, Groq, Ollama, OpenRouter) con `fallback_order` y `is_fallback`.
- **Reintentos con exponential backoff** y `acks_late`.

---

## 5. Seguridad y control de costos (diferenciador corporativo)

> «En un entorno empresarial, costo y seguridad son tan importantes como un buena respuesta.»

- **Telemetría por consulta**: tokens y costo real en USD (`QueryLog`, `MODEL_PRICING_USD_PER_1M`).
- **Caché de embeddings** (`lru_cache`) para no regenerar ni facturar embeddings repetidos.
- **Presupuesto de contexto** (`max_context_tokens`) antes de llamar al LLM.
- **Credenciales por variables de entorno** (`.env` excluido del repositorio, sin claves en el código).
- **Aislamiento por temas** (`Topic`): cada área consulta solo su documentación.

---

## 6. Aspecto de un proyecto serio (no un demo)

- Ingesta asíncrona con DAG Celery (`chord`) que fragmenta y emprime los chunks en paralelo.
- **Pruebas**: `test_chunking`, `test_circuit_breaker`, `test_failover`, `test_providers`, `test_rerank`, `test_search`, `test_token_budget`, `test_documents`.
- **Despliegue con Docker Compose** de 7 servicios (db, redis, migrate, web, worker, beat, flower, admin).
- **Energía de errores**: `acks_late`, reintentos, backoff, degradación elegante.
- Documentación operativa en `docs/manual-operaciones.md`.

---

## 7. Cierre con invitación al diálogo

> «Este proyecto no es un demo: tiene tolerancia a fallos, control de presupuesto, aislamiento por temas y pruebas automatizadas. Me encantaría contarles cómo lo adaptaría a las necesidades de su equipo y cómo elegiría el modelo en función de costo y calidad.»

---

## Tips para la entrevista

- **Descuesta en vivo**: prepara una pregunta sobre la documentación cargada para que se vea la cita de la fuente, el costo y la latencia.
- **Tener el respedor abierto** con URL visible.
- Antes de la entrevista, revisa `git log` y asegura inclusive comandantes claros (`feat:`, `docs:`, `fix:`).
- Transmite mentalidad de *producto + ingeniería*: enfatiza cómo el diseño resuelve costo, robustez y aislamiento.

---

## Versión corta (elevator pitch, 60 segundos)

> «Construí un sistema RAG empresarial para consultar documentación interna con lenguaje natural. Combino búsqueda vectorial (pgvector) y léxica (BM25) con re-ranking mediante LLM, sobre una arquitectura de Celery + Redis que nunca bloquea el servidor. Incluye circuit breakers, failover entre varios proveedores de IA, cache de embeddings y telemetría de costo por consulta, con aislamiento por temas y pruebas automatizadas. Es una solución de producción, no una demostración: es robusta, controlable y escalable.»