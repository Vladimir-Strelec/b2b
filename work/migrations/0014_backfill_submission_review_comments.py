from django.db import migrations


def copy_current_revision_comments(apps, schema_editor):
    WorkPlan = apps.get_model("work", "WorkPlan")
    WorkSubmission = apps.get_model("work", "WorkSubmission")
    db_alias = schema_editor.connection.alias
    plans = WorkPlan.objects.using(db_alias).filter(
        status="revision",
    ).exclude(review_comment="")
    for plan in plans.iterator():
        submission = WorkSubmission.objects.using(db_alias).filter(
            plan_id=plan.pk,
        ).order_by("-created_at", "-pk").first()
        if submission:
            WorkSubmission.objects.using(db_alias).filter(pk=submission.pk).update(
                review_comment=plan.review_comment,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0013_worksubmission_review_comment"),
    ]

    operations = [
        migrations.RunPython(copy_current_revision_comments, migrations.RunPython.noop),
    ]
