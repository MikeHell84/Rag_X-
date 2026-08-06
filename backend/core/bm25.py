"""Índice léxico BM25 con Whoosh.

Complementa la búsqueda vectorial: capta coincidencias exactas de términos,
siglas y números que los embeddings difuminan. El índice vive en disco
(volumen rag_storage) y se actualiza de forma incremental por chunk.
"""

import os
import threading
from typing import List

from whoosh import index, query as whoosh_q
from whoosh.fields import NUMERIC, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup

SCHEMA = Schema(
    chunk_id=NUMERIC(stored=True, unique=True, signed=False),
    document_id=NUMERIC(stored=True, signed=False),
    content=TEXT(stored=True),
)


class BM25Index:
    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self._lock = threading.Lock()
        self._ix = None

    @property
    def ix(self):
        if self._ix is None:
            os.makedirs(self.index_dir, exist_ok=True)
            if index.exists_in(self.index_dir):
                self._ix = index.open_dir(self.index_dir)
            else:
                self._ix = index.create_in(self.index_dir, SCHEMA)
        return self._ix

    def upsert_chunk(self, chunk_id: int, document_id: int, content: str) -> None:
        with self._lock:
            writer = self.ix.writer()
            writer.update_document(
                chunk_id=int(chunk_id),
                document_id=int(document_id),
                content=content,
            )
            writer.commit()

    def delete_chunk(self, chunk_id: int) -> None:
        with self._lock:
            writer = self.ix.writer()
            writer.delete_by_term("chunk_id", int(chunk_id))
            writer.commit()

    def delete_document(self, document_id: int) -> None:
        with self._lock:
            writer = self.ix.writer()
            writer.delete_by_term("document_id", int(document_id))
            writer.commit()

    def delete_all_documents(self) -> None:
        with self._lock:
            import shutil

            shutil.rmtree(self.index_dir, ignore_errors=True)
            self._ix = None
            # Force recreate
            _ = self.ix

    def search(self, query_text: str, limit: int = 20, document_ids: List[int] | None = None) -> List[dict]:
        if not query_text.strip():
            return []
        with self._lock, self.ix.searcher() as searcher:
            parser = MultifieldParser(["content"], schema=self.ix.schema, group=OrGroup)
            filters = None
            if document_ids:
                filters = whoosh_q.Or(
                    [whoosh_q.Term("document_id", int(did)) for did in document_ids]
                )
            hits = searcher.search(parser.parse(query_text), limit=limit, filter=filters)
            return [
                {"chunk_id": int(hit["chunk_id"]), "bm25": float(hit.score)}
                for hit in hits
            ]


_instance = None
_instance_lock = threading.Lock()


def get_bm25_index() -> BM25Index:
    global _instance
    if _instance is None:
        from django.conf import settings

        with _instance_lock:
            if _instance is None:
                _instance = BM25Index(settings.RAG["WHOOSH_INDEX_DIR"])
    return _instance
