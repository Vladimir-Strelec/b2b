from django.db import migrations


def update_categories(apps, schema_editor):
    Category = apps.get_model("work", "PhotoCategory")
    Photo = apps.get_model("work", "WorkPhoto")
    renames = {
        "Фронт": "Front",
        "Слева": "Links",
        "Справа": "Right",
        "Сзади": "Back",
        "Внутри": "Inside",
    }
    for old_name, new_name in renames.items():
        old = Category.objects.filter(name=old_name).first()
        if not old:
            continue
        existing = Category.objects.filter(name=new_name).first()
        if existing:
            Photo.objects.filter(category_id=old.pk).update(category_id=existing.pk)
            old.delete()
        else:
            old.name = new_name
            old.save(update_fields=["name"])

    for position, name in enumerate(("Front", "Links", "Right", "Back", "Top", "Bottom", "Inside", "Outside", "Detail", "General")):
        Category.objects.update_or_create(name=name, defaults={"order": position, "is_active": True})


class Migration(migrations.Migration):
    dependencies = [("work", "0005_alter_workplan_status_plantask")]

    operations = [migrations.RunPython(update_categories, migrations.RunPython.noop)]
