from unittest.mock import MagicMock

from core.rerank import LLMReranker


def _chunks(n):
    return [{"id": i, "content": f"fragmento {i}"} for i in range(1, n + 1)]


def test_rerank_falls_back_to_rrf_order_on_failure():
    llm = MagicMock()
    llm.chat_completion.side_effect = RuntimeError("proveedor caído")
    reranker = LLMReranker(model="m", llm=llm)
    chunks = _chunks(6)
    result = reranker.rerank("pregunta", chunks, top_n=3)
    assert result == chunks[:3]


def test_rerank_falls_back_on_malformed_json():
    llm = MagicMock()
    llm.chat_completion.return_value = {"content": "no es json"}
    reranker = LLMReranker(model="m", llm=llm)
    result = reranker.rerank("pregunta", _chunks(4), top_n=2)
    assert len(result) == 2


def test_rerank_reorders_by_scores():
    llm = MagicMock()
    llm.chat_completion.return_value = {"content": '{"scores": [1, 9, 5]}'}
    reranker = LLMReranker(model="m", llm=llm)
    chunks = [
        {"id": 1, "content": "x"},
        {"id": 2, "content": "y"},
        {"id": 3, "content": "z"},
    ]
    result = reranker.rerank("q", chunks, top_n=2)
    assert result[0]["id"] == 2


def test_rerank_empty_input():
    reranker = LLMReranker(model="m")
    assert reranker.rerank("q", [], top_n=5) == []
