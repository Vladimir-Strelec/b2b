from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0010_worksubmission_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="site",
            name="completion_reverted",
            field=models.BooleanField(
                default=False,
                help_text="Объект исключён из завершённых без удаления планов и отчётов.",
                verbose_name="Статус завершения сброшен",
            ),
        ),
    ]
