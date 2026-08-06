from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0004_agent_base_url_alter_agent_provider"),
        ("documents", "0002_tenant_querylog_feedback_querylog_updated_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="querylog",
            name="used_agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="query_logs",
                to="agents.agent",
            ),
        ),
    ]
