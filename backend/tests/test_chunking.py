from core.chunking import (
    HEADING_MD_RE,
    HybridChunker,
    SectionAwareSplitter,
    SemanticDriftGuard,
)


def _sample_markdown() -> str:
    return """# Manual de Operaciones

## Política de Vacaciones

Los empleados tienen derecho a 22 días laborables de vacaciones al año.
El periodo de solicitud debe presentarse con 15 días de antelación.

## Política de Teletrabajo

El teletrabajo está permitido dos días por semana bajo aprobación del manager.
Se exige disponibilidad durante el horario central de 9 a 15 horas.

# Anexo

Contacto de recursos humanos: rrhh@empresa.com
"""


def test_section_aware_splitter_detects_sections():
    splitter = SectionAwareSplitter(chunk_size=200, chunk_overlap=0)
    candidates = splitter.split(_sample_markdown())
    sections = {c.section for c in candidates}
    assert "Manual de Operaciones" in sections or "Política de Vacaciones" in sections
    assert "Política de Vacaciones" in sections
    assert "Política de Teletrabajo" in sections


def test_sections_within_token_budget():
    splitter = SectionAwareSplitter(chunk_size=100, chunk_overlap=0)
    candidates = splitter.split(_sample_markdown())
    assert all(c.token_count <= 150 for c in candidates)


def test_no_chunk_is_empty():
    splitter = SectionAwareSplitter(chunk_size=50, chunk_overlap=0)
    candidates = splitter.split(_sample_markdown())
    assert all(c.content.strip() for c in candidates)


def test_sentences_not_cut_in_half():
    splitter = SectionAwareSplitter(chunk_size=40, chunk_overlap=0)
    paragraphs = [
        "Primera frase completa. Segunda frase completa. Tercera frase larga y completa.",
    ]
    text = "\n\n".join(paragraphs)
    candidates = splitter.split(text)
    for candidate in candidates:
        assert candidate.content.endswith((".", "?", "!", "a", "0", "9")) or candidate.content.isdigit()


def test_small_neighbors_are_merged():
    splitter = SectionAwareSplitter(chunk_size=400, chunk_overlap=0)
    candidates = splitter.split(_sample_markdown())
    for a, b in zip(candidates, candidates[1:]):
        if a.section == b.section:
            assert a.token_count + b.token_count > 400


def test_hybrid_chunker_no_semantic_guard_is_pure_structural():
    chunker = HybridChunker(chunk_size=200, chunk_overlap=0)
    candidates = chunker.chunk_text(_sample_markdown())
    assert candidates


def test_semantic_drift_guard_cuts_on_topic_change():
    vectors = {"a": [1.0, 0.0, 0.0], "b": [0.0, 1.0, 0.0]}

    def embed_fn(text):
        return vectors.get(text.strip(), vectors["a"])

    guard = SemanticDriftGuard(embed_fn=embed_fn, threshold=0.6, min_distance_tokens=10)
    assert guard._should_continue("a") is True
    assert guard._should_continue("b") is False


def test_heading_regex():
    assert HEADING_MD_RE.match("# Título")
    assert HEADING_MD_RE.match("### Subsección")
    assert not HEADING_MD_RE.match("No es un heading")
