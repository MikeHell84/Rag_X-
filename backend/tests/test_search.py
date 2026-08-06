from core.search import rrf_fusion


def test_rrf_rank_1_wins():
    vector_hits = [{"chunk_id": 1}, {"chunk_id": 2}, {"chunk_id": 3}]
    bm25_hits = [{"chunk_id": 1}, {"chunk_id": 4}]
    fused = rrf_fusion(vector_hits, bm25_hits)
    assert fused[0]["chunk_id"] == 1


def test_rrf_favors_present_in_both():
    vector_hits = [{"chunk_id": 7}, {"chunk_id": 6}]
    bm25_hits = [{"chunk_id": 7}, {"chunk_id": 5}]
    fused = rrf_fusion(vector_hits, bm25_hits)
    assert fused[0]["chunk_id"] == 7


def test_rrf_first_ranked_from_one_side_can_win():
    vector_hits = [{"chunk_id": 5}, {"chunk_id": 6}, {"chunk_id": 7}]
    bm25_hits = [{"chunk_id": 7}, {"chunk_id": 5}]
    fused = rrf_fusion(vector_hits, bm25_hits)
    assert fused[0]["chunk_id"] == 5


def test_rrf_scores_positive_and_sorted():
    vector_hits = [{"chunk_id": i} for i in range(1, 10)]
    bm25_hits = [{"chunk_id": i} for i in range(1, 10)]
    fused = rrf_fusion(vector_hits, bm25_hits)
    assert all(item["rrf"] > 0 for item in fused)
    scores = [item["rrf"] for item in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_no_duplicates():
    vector_hits = [{"chunk_id": 1}, {"chunk_id": 2}]
    bm25_hits = [{"chunk_id": 1}, {"chunk_id": 2}]
    fused = rrf_fusion(vector_hits, bm25_hits)
    ids = [item["chunk_id"] for item in fused]
    assert len(ids) == len(set(ids))
