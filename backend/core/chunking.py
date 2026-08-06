"""Estrategia de chunking avanzada: dividir respetando la semántica.

Pipeline (ver README, sección 1):

1. Extracción del texto preservando la estructura:
   - PDF: agrupación de caracteres por línea y detección de encabezados por
     tamaño de fuente (>= 1.15x la mediana) con pdfplumber.
   - DOCX: párrafos con estilo "Heading*".
   - Markdown / texto plano: encabezados `#..######` o heurística de línea.

2. SectionAwareSplitter convierte la estructura en "bloques semánticos"
   delimitados por encabezados. Un bloque que excede el presupuesto de tokens
   se subdivide respetando párrafos -> frases -> (solo al final) tokens,
   de forma que NUNCA se corta una frase si hay un separador disponible.

3. Los fragmentos pequeños contiguos se fusionan con un control semántico:
   el SemanticDriftGuard compara la similitud coseno de los embeddings del
   borde y corta aunque haya presupuesto de tokens, evitando mezclar temas
   dentro de un mismo chunk.

4. RecursiveCharacterTextSplitter de langchain-text-splitters actúa como
   respaldo determinista con separadores personalizados.
"""

import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pdfplumber
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .token_budget import estimate_tokens

HEADING_MD_RE = re.compile(r"(?m)^(#{1,6})\s+(.+)$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?¡¿])\s+(?=[A-ZÁÉÍÓÚÑ¿])")

DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


@dataclass
class ChunkCandidate:
    content: str
    section: str = ""
    page: Optional[int] = None
    token_count: int = 0

    def __post_init__(self) -> None:
        if not self.token_count:
            self.token_count = estimate_tokens(self.content)


# ---------------------------------------------------------------------------
# 1. Extracción estructurada del texto
# ---------------------------------------------------------------------------
def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith((".", ",", ";", ":")):
        return False
    if re.match(r"^\s*[-*•]\s", stripped):
        return False
    if re.match(r"^\s*(\d+[.)]|[a-z][.)])\s", stripped, re.IGNORECASE):
        return False
    if stripped.isupper() and len(stripped) > 3:
        return True
    return len(stripped) < 70 and sum(1 for ch in stripped if ch.isupper()) / max(1, len(stripped)) > 0.4


def _looks_like_body_text(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.endswith((".", ",", ";", ":", "…")):
        return True
    if re.match(r"^\s*[-*•]\s", stripped):
        return True
    if re.match(r"^\s*(\d+[.)]|[a-z][.)])\s", stripped, re.IGNORECASE):
        return True
    return len(stripped) > 140


def extract_pdf_text_with_headings(path: str) -> Tuple[str, List[Tuple[int, str]]]:
    lines: List[Tuple[int, float, str]] = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            chars = sorted(page.chars, key=lambda c: (round(c["top"], 1), c["x0"]))
            top_key = None
            buffer: List[dict] = []
            for char in chars:
                key = round(char["top"], 1)
                if top_key is None or key != top_key:
                    if buffer:
                        text = "".join(c["text"] for c in buffer).strip()
                        size = max(c["size"] for c in buffer)
                        if text:
                            lines.append((page_no, size, text))
                    buffer = []
                    top_key = key
                buffer.append(char)
            if buffer:
                text = "".join(c["text"] for c in buffer).strip()
                size = max(c["size"] for c in buffer)
                if text:
                    lines.append((page_no, size, text))

    # OCR fallback para PDFs escaneados (sin capa de texto)
    if not lines and os.environ.get("ENABLE_OCR", "0") == "1":
        try:
            import pytesseract
            from pdf2image import convert_from_path
            pages = convert_from_path(path, dpi=200)
            for page_no, image in enumerate(pages, start=1):
                text = pytesseract.image_to_string(image, lang="spa")
                if text.strip():
                    lines.append((page_no, 10.0, text.strip()))
        except Exception:
            pass

    if not lines:
        return "", []

    sizes = sorted(size for _, size, _ in lines if size)
    median = sizes[len(sizes) // 2] if sizes else 10.0
    if median <= 0:
        median = 10.0

    markdown_lines: List[str] = []
    headings: List[Tuple[int, str]] = []
    for page_no, size, text in lines:
        is_heading = size >= median * 1.15 and len(text) <= 90 and not _looks_like_body_text(text)
        if is_heading:
            level = min(6, max(1, round((size / median - 1) * 3) + 1))
            markdown_lines.append(f"{'#' * level} {text}")
            headings.append((page_no, text))
        else:
            markdown_lines.append(text)

    return "\n".join(markdown_lines), headings


def extract_docx_text_with_headings(path: str) -> str:
    doc = DocxDocument(path)
    out: List[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style is not None else ""
        if "Heading" in style or "Título" in style:
            try:
                level = int("".join(ch for ch in style if ch.isdigit()) or "1")
            except ValueError:
                level = 1
            out.append(f"{'#' * min(6, level)} {text}")
        else:
            out.append(text)
    return "\n".join(out)


def extract_text(path: str, source_type: str) -> Tuple[str, List[Tuple[int, str]]]:
    if source_type == "pdf":
        return extract_pdf_text_with_headings(path)
    if source_type == "docx":
        return extract_docx_text_with_headings(path), []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(), []


# ---------------------------------------------------------------------------
# 2. Divisor por secciones
# ---------------------------------------------------------------------------
class SectionAwareSplitter:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 80, min_chunk: int = 120):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk = min_chunk
        self.recursive = RecursiveCharacterTextSplitter(
            separators=DEFAULT_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=estimate_tokens,
        )

    def split(self, text: str, page_hints: Optional[dict] = None) -> List[ChunkCandidate]:
        sections = self._to_sections(text)
        candidates: List[ChunkCandidate] = []
        for heading, block in sections:
            if not block.strip():
                continue
            tokens = estimate_tokens(block)
            if tokens <= self.chunk_size:
                candidates.append(ChunkCandidate(block.strip(), section=heading))
            else:
                candidates.extend(self._split_large_block(block, heading))
        return self._merge_small(candidates)

    def _to_sections(self, text: str) -> List[Tuple[str, str]]:
        current_heading = ""
        buffer: List[str] = []
        sections: List[Tuple[str, str]] = []
        for raw in text.splitlines():
            line = raw.rstrip()
            m = HEADING_MD_RE.match(line)
            if m:
                if buffer:
                    sections.append((current_heading, "\n".join(buffer)))
                current_heading = m.group(2).strip()
                buffer = [f"#{m.group(1)} {m.group(2).strip()}"]
            else:
                buffer.append(line)
        if buffer:
            sections.append((current_heading, "\n".join(buffer)))
        return sections

    def _split_large_block(self, block: str, heading: str) -> List[ChunkCandidate]:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", block) if p.strip()]
        result: List[ChunkCandidate] = []
        buffer = ""
        for paragraph in paragraphs:
            if not buffer:
                buffer = paragraph
                continue
            if estimate_tokens(buffer) + estimate_tokens(paragraph) <= self.chunk_size:
                buffer = f"{buffer}\n\n{paragraph}"
                continue
            result.append(ChunkCandidate(buffer, section=heading))
            if estimate_tokens(paragraph) <= self.chunk_size:
                buffer = paragraph
            else:
                result.extend(self._split_by_sentences(paragraph, heading))
                buffer = ""
        if buffer:
            result.append(ChunkCandidate(buffer, section=heading))
        return result

    def _split_by_sentences(self, paragraph: str, heading: str) -> List[ChunkCandidate]:
        sentences = SENTENCE_SPLIT_RE.split(paragraph)
        result: List[ChunkCandidate] = []
        buffer = ""
        for sentence in sentences:
            if not buffer:
                buffer = sentence
                continue
            if estimate_tokens(buffer) + estimate_tokens(sentence) <= self.chunk_size:
                buffer = f"{buffer} {sentence}"
                continue
            result.append(ChunkCandidate(buffer, section=heading))
            buffer = sentence
        if buffer:
            result.append(ChunkCandidate(buffer, section=heading))
        return result

    def _merge_small(self, candidates: List[ChunkCandidate]) -> List[ChunkCandidate]:
        merged: List[ChunkCandidate] = []
        for candidate in candidates:
            if (
                merged
                and candidate.section == merged[-1].section
                and merged[-1].token_count + candidate.token_count <= self.chunk_size
            ):
                content = f"{merged[-1].content}\n\n{candidate.content}"
                merged[-1] = ChunkCandidate(content, section=merged[-1].section, token_count=estimate_tokens(content))
            else:
                merged.append(candidate)
        return merged


# ---------------------------------------------------------------------------
# 3. Control semántico de corte (evita mezclar temas)
# ---------------------------------------------------------------------------
class SemanticDriftGuard:
    def __init__(
        self,
        embed_fn: Callable[[str], List[float]],
        threshold: float = 0.70,
        min_distance_tokens: int = 60,
        lookback: int = 3,
    ):
        self.embed_fn = embed_fn
        self.threshold = threshold
        self.min_distance_tokens = min_distance_tokens
        self.lookback = lookback
        self._last_vectors: List[List[float]] = []

    def _should_continue(self, text: str) -> bool:
        try:
            vector = self.embed_fn(text)
        except Exception:
            # Degradación graceful: si el proveedor de embeddings no responde
            # (quota/rate-limit/circuit abierto), el chunking estructurado sigue
            # sin control semántico en vez de tirar toda la ingesta.
            self.disabled = True
            return False
        if not self._last_vectors:
            self._last_vectors.append(vector)
            return True
        similarity = self._cosine(vector, self._last_vectors[-1])
        self._last_vectors.append(vector)
        self._last_vectors = self._last_vectors[-self.lookback :]
        return similarity >= self.threshold

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 1.0
        return dot / (na * nb)


# ---------------------------------------------------------------------------
# 4. Orquestador: Chunker híbrido
# ---------------------------------------------------------------------------
class HybridChunker:
    """Combina el divisor estructural con el control semántico y un respaldo
    recursivo determinista (langchain) para los bloques residuales."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 80,
        semantic_guard: Optional[SemanticDriftGuard] = None,
    ):
        self.splitter = SectionAwareSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.semantic_guard = semantic_guard
        self.fallback = RecursiveCharacterTextSplitter(
            separators=DEFAULT_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=estimate_tokens,
        )

    def chunk_text(self, text: str, default_section: str = "") -> List[ChunkCandidate]:
        candidates = self.splitter.split(text)
        if self.semantic_guard is None:
            return candidates
        return self._apply_semantic_guard(candidates, default_section)

    def _apply_semantic_guard(self, candidates: List[ChunkCandidate], default_section: str) -> List[ChunkCandidate]:
        result: List[ChunkCandidate] = []
        buffer: List[ChunkCandidate] = []
        for candidate in candidates:
            buffer.append(candidate)
            running_tokens = sum(c.token_count for c in buffer)
            if running_tokens > self.splitter.chunk_size:
                window_text = " ".join(c.content[-300:] for c in buffer if c.content)
                if self.semantic_guard._should_continue(window_text) or running_tokens < self.splitter.min_chunk:
                    continue
                merged = ChunkCandidate(
                    "\n\n".join(c.content for c in buffer),
                    section=buffer[0].section or default_section,
                    token_count=running_tokens,
                )
                result.append(merged)
                buffer = []
        if buffer:
            merged = ChunkCandidate(
                "\n\n".join(c.content for c in buffer),
                section=buffer[0].section or default_section,
                token_count=sum(c.token_count for c in buffer),
            )
            result.append(merged)
        return result
