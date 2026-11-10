from django.db import migrations


def add_categories(apps, schema_editor):
    PhotoCategory = apps.get_model("work", "PhotoCategory")
    for position, name in enumerate(("Фронт", "Слева", "Справа", "Сзади", "Внутри")):
        PhotoCategory.objects.get_or_create(name=name, defaults={"order": position})


class Migration(migrations.Migration):
    dependencies = [("work", "0003_alter_workphoto_category_alter_workphoto_description")]

    operations = [migrations.RunPython(add_categories, migrations.RunPython.noop)]
