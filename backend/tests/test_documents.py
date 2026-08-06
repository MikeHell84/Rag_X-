"""Tests de los endpoints de documentos (upload / list / detail / retry / delete)."""

import hashlib
import tempfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from documents.models import Document


@pytest.fixture(autouse=True)
def _tmp_media():
    with tempfile.TemporaryDirectory() as tmp:
        with override_settings(MEDIA_ROOT=tmp):
            yield


class _FakeTask:
    id = "task-123"

    def delay(self, document_id):
        _FakeTask.last_document_id = document_id
        return self


def _make_doc(title="notas.md", status=Document.Status.READY, **kwargs):
    content = title.encode()
    return Document.objects.create(
        title=title,
        source_type="md",
        content_hash=hashlib.sha256(content).hexdigest(),
        status=status,
        **kwargs,
    )


@pytest.mark.django_db
def test_upload_accepts_and_creates_document(monkeypatch):
    _FakeTask.last_document_id = None
    monkeypatch.setattr("documents.views.ingest_document", _FakeTask())
    client = APIClient()
    file = SimpleUploadedFile("manual.md", b"# Manual de operaciones", content_type="text/markdown")
    resp = client.post("/api/documents/upload/", {"file": file}, format="multipart")
    assert resp.status_code == 202
    body = resp.json()
    doc = Document.objects.get(pk=body["id"])
    assert doc.status == Document.Status.PENDING
    assert _FakeTask.last_document_id == doc.id
    assert doc.metadata["task_id"] == "task-123"


@pytest.mark.django_db
def test_upload_rejects_unsupported_extension():
    client = APIClient()
    file = SimpleUploadedFile("malware.exe", b"x", content_type="application/octet-stream")
    resp = client.post("/api/documents/upload/", {"file": file}, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_upload_duplicate_returns_409():
    existing = _make_doc()
    client = APIClient()
    file = SimpleUploadedFile("otro.md", existing.title.encode(), content_type="text/markdown")
    resp = client.post("/api/documents/upload/", {"file": file}, format="multipart")
    assert resp.status_code == 409
    assert resp.json()["duplicate"] is True
    assert resp.json()["id"] == existing.id


@pytest.mark.django_db
def test_list_returns_documents_ordered():
    _make_doc("b.md")
    _make_doc("a.md")
    client = APIClient()
    resp = client.get("/api/documents/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # Filter to just the two test docs
    test_titles = [row["title"] for row in body["results"] if row["title"] in ("a.md", "b.md")]
    # Most recent first: a.md was created after b.md
    assert test_titles == ["a.md", "b.md"]


@pytest.mark.django_db
def test_retry_resets_status_and_enqueues(monkeypatch):
    doc = _make_doc(status=Document.Status.FAILED, error_message="boom")
    _FakeTask.last_document_id = None
    monkeypatch.setattr("documents.views.ingest_document", _FakeTask())
    client = APIClient()
    resp = client.post(f"/api/documents/{doc.id}/retry/")
    assert resp.status_code == 202
    doc.refresh_from_db()
    assert doc.status == Document.Status.PENDING
    assert doc.error_message == ""
    assert doc.metadata["task_id"] == "task-123"
    assert _FakeTask.last_document_id == doc.id


@pytest.mark.django_db
def test_retry_missing_document_404():
    client = APIClient()
    resp = client.post("/api/documents/999/retry/")
    assert resp.status_code == 404


class _FakeBM25:
    def delete_document(self, document_id):
        return None


@pytest.mark.django_db
def test_delete_removes_document_and_chunks(monkeypatch):
    doc = _make_doc()
    doc.chunks.create(index=0, content="un chunk", token_count=3)
    monkeypatch.setattr("documents.views.get_bm25_index", lambda: _FakeBM25())
    client = APIClient()
    resp = client.delete(f"/api/documents/{doc.id}/")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert not Document.objects.filter(pk=doc.id).exists()


@pytest.mark.django_db
def test_delete_missing_document_404():
    client = APIClient()
    resp = client.delete("/api/documents/999/")
    assert resp.status_code == 404
