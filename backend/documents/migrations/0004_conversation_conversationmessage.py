from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0004_agent_base_url_alter_agent_provider"),
        ("documents", "0003_querylog_used_agent"),
    ]

    operations = [
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=200)),
                ("topic", models.CharField(blank=True, help_text="Tema o categoría de la conversación", max_length=100)),
                ("visibility", models.CharField(choices=[("private", "Privada"), ("shared", "Compartida")], default="private", max_length=10)),
                ("session_key", models.CharField(blank=True, help_text="Identificador de sesión del usuario", max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversations", to="agents.agent")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ConversationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "Usuario"), ("assistant", "Asistente"), ("system", "Sistema")], max_length=10)),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="documents.conversation")),
            ],
        ),
    ]
