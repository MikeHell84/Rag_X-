FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 rag && \
    useradd --uid 10001 --gid rag --create-home --shell /usr/sbin/nologin rag

# OCR opcional: tesseract + pytesseract + poppler (para pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/storage/whoosh /app/media /app/staticfiles && \
    chown -R rag:rag /app/storage /app/media /app/staticfiles && \
    chmod +x /app/entrypoint.sh

USER rag

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
