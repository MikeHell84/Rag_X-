"""Ingesta desde URLs.

- Baja el HTML de una URL (con timeout y User-Agent).
- Extrae el contenido principal limpio y lo convierte a **Markdown** con
  trafilatura (preservando encabezados `#`/`##`, listas y enlaces).
- Guarda el resultado como archivo .md en MEDIA_ROOT/ingest/ para que quede
  persistente y reusable por las sesiones/conversaciones.

El código del pipeline RAG descarga / scoring NO toca el servidor web: es un
módulo auxiliar llamado desde la vista de ingesta (que crea el archivo .md) y
dado que extract_text() ya lee archivos .md como texto plano, la tarea de
ingesta existente lo indexa sin cambios.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import trafilatura

# Se descargan páginas web normales; timeout defensivo para no colgar el worker.
# Se usan cabeceras de navegador real para evitar bloqueos 403/429 de CDNs (Cloudflare,
# DataCamp, Medium, etc.). Se intenta con varios User-Agent antes de rendirse.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]
DEFAULT_TIMEOUT = 30
MAX_BYTES = 20 * 1024 * 1024  # 20 MB (HTML comprimido/raw)


class UrlFetchError(Exception):
    """Error al descargar o procesar la URL."""


def _download(url: str, timeout: int, headers: dict) -> requests.Response:
    """Descarga con reintentos y rotación de User-Agent ante bloqueos (403/429)."""
    last_exc: Exception | None = None
    for ua in USER_AGENTS:
        hs = dict(headers)
        hs["User-Agent"] = ua
        try:
            resp = requests.get(
                url,
                headers=hs,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            if resp.status_code in (403, 429, 401):
                resp.close()
                continue  # probar otro User-Agent
            if resp.status_code == 410:
                resp.close()
                raise UrlFetchError(
                    "La página fue eliminada por el sitio web (HTTP 410 Gone). "
                    "Busca la versión más reciente o usa otra URL."
                )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise UrlFetchError(f"No se pudo descargar la URL: {last_exc}") from last_exc
    raise UrlFetchError(
        "El sitio bloqueó el acceso (403/429). Intenta con otra página o desde otro navegador."
    )


def fetch_markdown(
    url: str,
    media_root: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[Path, str, str]:
    """Descarga `url`, extrae su cuerpo a Markdown y lo guarda en media_root.

    Returns:
        (path_del_archivo_md, texto_markdown, titulo)
    """
    try:
        resp = _download(url, timeout, DEFAULT_HEADERS)
    except UrlFetchError:
        raise
    except Exception as exc:  # pragma: no cover
        raise UrlFetchError(f"No se pudo descargar la URL: {exc}") from exc

    content_type = resp.headers.get("Content-Type", "").lower()

    _collected: list[bytes] = []
    _total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        _total += len(chunk)
        if _total > MAX_BYTES:
            raise UrlFetchError(
                f"El contenido de la URL supera el límite de {MAX_BYTES // (1024*1024)} MB"
            )
        _collected.append(chunk)
    raw = b"".join(_collected)

    # Si es PDF/DOCX enlazado, devolvemos sin tratar como HTML (se bajaría aparte).
    if source_is_binary(content_type, url):
        raise UrlFetchError(
            "La URL apunta a un archivo binario (PDF/DOCX/etc.). Usa el enlace "
            "para archivos o sube el fichero directamente."
        )

    html = _decode(raw, content_type)

    # trafilatura extrae el bloque principal y lo convierte a Markdown.
    options = extra_options()
    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=0.4,  # preferir algo más de contenido
        include_links=True,
        output_format="markdown",
    )
    markdown = (extracted or "").strip()

    # --- Fallbacks: Google Cache → Wayback Machine ---
    if not markdown:
        for fallback_url in _fallback_urls(url):
            try:
                resp2 = _download(fallback_url, timeout, DEFAULT_HEADERS)
                ct2 = resp2.headers.get("Content-Type", "").lower()
                raw2 = b"".join(resp2.iter_content(chunk_size=65536))
                html2 = _decode(raw2, ct2)
                extracted2 = trafilatura.extract(
                    html2,
                    include_comments=False,
                    include_tables=True,
                    favor_precision=0.4,
                    include_links=True,
                    output_format="markdown",
                )
                markdown = (extracted2 or "").strip()
                if markdown:
                    break
            except Exception:
                continue

    if not markdown:
        raise UrlFetchError(
            "No se pudo extraer texto de la URL. "
            "Posibles causas: la página requiere JavaScript para mostrarse, "
        )

    title = _title_of(url, html)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    stamp = datetime.now().strftime("%Y%m%d")
    filename = f"url_{stamp}_{digest}.md"
    rel = Path("ingest") / stamp[:6] / filename  # carpeta por mes
    path = Path(media_root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")

    return path, markdown, title


def _fallback_urls(url: str) -> list[str]:
    """Devuelve URLs alternativas para intentar cuando la original falla."""
    return [
        f"https://webcache.googleusercontent.com/search?q=cache:{url}",
        f"https://web.archive.org/web/2024/{url}",
    ]


def source_is_binary(content_type: str, url: str) -> bool:
    """Detecta si la URL apunta a un archivo binario (no a HTML)."""
    binary_ct = ("application/pdf", "application/msword", "application/octet-stream")
    if any(ct in content_type for ct in binary_ct):
        return True
    path = url.split("?", 1)[0].lower()
    return path.endswith((".pdf", ".doc", ".docx", ".xlsx", ".zip", ".png", ".jpg", ".jpeg"))


def _decode(raw: bytes, content_type: str) -> str:
    """Decodifica el HTML respetando el charset indicado o infiriéndolo por BOM."""
    m = re.search(r"charset=([\w-]+)", content_type)
    encoding = m.group(1) if m else "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


def extra_options() -> str:
    return "markdown"


def _title_of(url: str, html: str) -> str:
    """Devuelve el <title> de la página o un slug de la URL como título."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        if title:
            return title[:200]
    # Fallback: último segmento de la URL, humanizado
    segment = url.split("?")[0].rstrip("/").split("/")[-1]
    if not segment:
        segment = url.split("//")[-1].split("/")[0]
    return re.sub(r"[-_]+", " ", segment).strip()[:200] or "Página web"