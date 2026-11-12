from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0012_workshift"),
    ]

    operations = [
        migrations.AddField(
            model_name="worksubmission",
            name="review_comment",
            field=models.TextField(blank=True, verbose_name="Причина возврата на доработку"),
        ),
    ]
