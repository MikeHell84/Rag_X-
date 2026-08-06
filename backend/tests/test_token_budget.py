from core.token_budget import estimate_tokens, truncate_to_budget


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_never_zero():
    assert estimate_tokens("x") == 1


def test_estimate_tokens_scales_with_length():
    short = estimate_tokens("hola mundo")
    long_ = estimate_tokens("hola mundo " * 100)
    assert long_ > short


def test_truncate_to_budget_within_budget():
    text = "corto"
    assert truncate_to_budget(text, 1000) == text


def test_truncate_to_budget_reduces():
    text = "palabra " * 500
    reduced = truncate_to_budget(text, 50)
    assert len(reduced) < len(text)
    assert estimate_tokens(reduced) <= 60
