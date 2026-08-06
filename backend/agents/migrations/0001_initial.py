from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "agent_type",
                    models.CharField(
                        choices=[("chat", "Generación (LLM)"), ("embedding", "Embeddings"), ("reranker", "Re-ranking")],
                        max_length=20,
                    ),
                ),
                (
                    "provider",
                    models.CharField(choices=[("openai", "OpenAI")], default="openai", max_length=20),
                ),
                ("model", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True)),
                ("temperature", models.FloatField(default=0.2)),
                ("max_tokens", models.PositiveIntegerField(default=1024)),
                ("top_k", models.PositiveIntegerField(default=5)),
                ("system_prompt", models.TextField(blank=True)),
                ("embedding_dim", models.PositiveIntegerField(default=1536)),
                ("is_active", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["agent_type", "name"]},
        ),
        migrations.CreateModel(
            name="PlatformConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="default", max_length=64, unique=True)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="agent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("agent_type",),
                name="unique_active_agent_per_type",
            ),
        ),
    ]
