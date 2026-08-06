from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0004_conversation_conversationmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="topic",
            field=models.CharField(blank=True, help_text="Tema o categor�a del documento", max_length=100),
        ),
    ]