"""Acceso a pgvector con SQL directo.

La extensión pgvector y la tabla chunk_embeddings se crean en la migración
0001 (RunSQL). Aquí usamos psycopg a través del cursor de Django para:

- upsert de embeddings (ON CONFLICT).
- búsqueda ANN por similitud coseno con índice HNSW.
"""

from typing import List, Optional

from django.db import connection

from .embeddings import text_hash


def upsert_embedding(chunk_id: int, embedding: List[float], model: str) -> None:
    payload = text_hash(",".join(f"{v:.6f}" for v in embedding))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chunk_embeddings (chunk_id, embedding, embedding_model, content_hash, created_at)
            VALUES (%s, %s::vector, %s, %s, NOW())
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                content_hash = EXCLUDED.content_hash,
                created_at = NOW()
            """,
            [chunk_id, _to_vector_literal(embedding), model, payload],
        )


def delete_embeddings(chunk_ids: List[int]) -> None:
    if not chunk_ids:
        return
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM chunk_embeddings WHERE chunk_id = ANY(%s)", [chunk_ids])


def vector_search(
    query_embedding: List[float],
    top_k: int = 20,
    ef_search: int | None = None,
    document_ids: List[int] | None = None,
) -> List[dict]:
    where, params = "", []
    where = "\n            WHERE e.chunk_id IN (SELECT c.id FROM documents_chunk c WHERE c.document_id = ANY(%s))"
    if not document_ids:
        where = ""
    params.append(_to_vector_literal(query_embedding))
    if document_ids:
        params.append(document_ids)
    params.append(_to_vector_literal(query_embedding))
    params.append(top_k)
    with connection.cursor() as cursor:
        if ef_search:
            cursor.execute("SET hnsw.ef_search = %s", [int(ef_search)])
        cursor.execute(
            f"""
            SELECT e.chunk_id,
                   1 - (e.embedding <=> %s::vector) AS similarity
            FROM chunk_embeddings e
            {where}
            ORDER BY e.embedding <=> %s::vector ASC
            LIMIT %s
            """,
            params,
        )
        return [{"chunk_id": row[0], "similarity": float(row[1])} for row in cursor.fetchall()]


def vector_dim() -> int:
    """Dimensión de la columna `embedding` (pgvector) en Postgres."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'chunk_embeddings'::regclass AND attname = 'embedding'
            """
        )
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] and row[0] > 0 else 0


def get_embeddings(chunk_ids: List[int]) -> dict:
    """Devuelve {chunk_id: [float,...]} para los chunks indicados."""
    if not chunk_ids:
        return {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, regexp_split_to_array(trim(embedding::text, '[]'), ',')
            FROM chunk_embeddings
            WHERE chunk_id = ANY(%s)
            """,
            [chunk_ids],
        )
        return {row[0]: [float(v) for v in row[1]] for row in cursor.fetchall()}


def count_embeddings() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM chunk_embeddings")
        return int(cursor.fetchone()[0])


def _to_vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
