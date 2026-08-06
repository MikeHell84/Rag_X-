"""Presupuesto de tokens.

Estimador determinista (4 caracteres aprox. por token, ajuste simple para
ideogramas) para dimensionar chunking y recortar contextos SIN llamar a un
tokenizador externo. Intercambiable por tiktoken si se desea exactitud.
"""


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2FFF)
    total_chars = len(text)
    return max(1, round((total_chars - cjk) / 4 + cjk * 0.6))


def truncate_to_budget(text: str, budget: int) -> str:
    if estimate_tokens(text) <= budget:
        return text
    step = max(1, len(text) // max(1, estimate_tokens(text)))
    return text[: budget * step]
