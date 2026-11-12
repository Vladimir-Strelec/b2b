from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0011_site_completion_reverted"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkShift",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True, verbose_name="Начало смены")),
                ("ended_at", models.DateTimeField(blank=True, null=True, verbose_name="Конец смены")),
                ("worker", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shifts", to="work.worker", verbose_name="Работник")),
            ],
            options={
                "verbose_name": "Рабочая смена",
                "verbose_name_plural": "Рабочие смены",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="workshift",
            constraint=models.UniqueConstraint(condition=models.Q(("ended_at__isnull", True)), fields=("worker",), name="one_open_shift_per_worker"),
        ),
    ]
