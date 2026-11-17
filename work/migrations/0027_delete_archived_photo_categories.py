from django.db import migrations


def delete_archived_categories(apps, schema_editor):
    PhotoCategory = apps.get_model("work", "PhotoCategory")
    Site = apps.get_model("work", "Site")
    SitePhotoRequirement = apps.get_model("work", "SitePhotoRequirement")
    WorkPhoto = apps.get_model("work", "WorkPhoto")
    database = schema_editor.connection.alias

    archived_ids = list(
        PhotoCategory.objects.using(database)
        .filter(is_active=False)
        .values_list("pk", flat=True)
    )
    if not archived_ids:
        return

    # Keep sites, submissions, and uploaded images while removing obsolete category links.
    Site.objects.using(database).filter(category_id__in=archived_ids).update(category=None)
    WorkPhoto.objects.using(database).filter(category_id__in=archived_ids).update(category=None)
    SitePhotoRequirement.objects.using(database).filter(category_id__in=archived_ids).delete()
    PhotoCategory.objects.using(database).filter(pk__in=archived_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("work", "0026_site_unique_site_address_category_ci"),
    ]

    operations = [
        migrations.RunPython(delete_archived_categories, migrations.RunPython.noop),
    ]
