from django.db import migrations, models
import django.db.models.deletion


def create_pgvector_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                id BIGSERIAL PRIMARY KEY,
                chunk_id BIGINT UNIQUE NOT NULL REFERENCES documents_chunk(id) ON DELETE CASCADE,
                embedding vector(1536) NOT NULL,
                embedding_model VARCHAR(128) NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS chunk_embeddings_hnsw_idx
            ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);
            """
        )


def drop_pgvector_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS chunk_embeddings;")
        cursor.execute("DROP EXTENSION IF EXISTS vector;")


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=500)),
                ("file", models.FileField(upload_to="ingest/%Y/%m/")),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("pdf", "PDF"),
                            ("docx", "DOCX"),
                            ("md", "Markdown"),
                            ("txt", "Texto"),
                        ],
                        max_length=10,
                    ),
                ),
                ("content_hash", models.CharField(max_length=64, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("processing", "Procesando"),
                            ("chunked", "Fragmentado"),
                            ("embedded", "Embeddings listos"),
                            ("ready", "Listo"),
                            ("failed", "Fallido"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("total_chunks", models.PositiveIntegerField(default=0)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Chunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("index", models.PositiveIntegerField()),
                ("section", models.CharField(blank=True, max_length=500)),
                ("page", models.PositiveIntegerField(blank=True, null=True)),
                ("content", models.TextField()),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="documents.document",
                    ),
                ),
            ],
            options={"ordering": ["document", "index"]},
        ),
        migrations.CreateModel(
            name="QueryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query_text", models.TextField()),
                ("embedding_model", models.CharField(blank=True, max_length=128)),
                ("llm_model", models.CharField(blank=True, max_length=128)),
                ("candidate_count", models.PositiveIntegerField(default=0)),
                ("rerank_count", models.PositiveIntegerField(default=0)),
                ("tokens_prompt", models.PositiveIntegerField(default=0)),
                ("tokens_completion", models.PositiveIntegerField(default=0)),
                ("total_cost_usd", models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("answer", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="chunk",
            constraint=models.UniqueConstraint(fields=("document", "index"), name="unique_chunk_index"),
        ),
        migrations.RunPython(
            create_pgvector_tables,
            reverse_code=drop_pgvector_tables,
        ),
    ]
