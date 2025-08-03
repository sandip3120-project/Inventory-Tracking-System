from django.db import migrations

def set_legacy_department(apps, schema_editor):
    Material   = apps.get_model('warehouse', 'Material')
    Department = apps.get_model('warehouse', 'Department')
    # find your Legacy/Admin department
    legacy = Department.objects.get(code='LG')
    # assign it to all Materials where department is NULL
    Material.objects.filter(department__isnull=True).update(department=legacy)

class Migration(migrations.Migration):

    dependencies = [
        ('warehouse', '0004_remove_material_colour_and_more')
    ]

    operations = [
        migrations.RunPython(set_legacy_department, reverse_code=migrations.RunPython.noop),
    ]
