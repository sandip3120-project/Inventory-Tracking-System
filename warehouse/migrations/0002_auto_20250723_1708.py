from django.db import migrations

def seed_departments(apps, schema_editor):
    Department = apps.get_model('warehouse', 'Department')
    for code, name in [
        ('FM', 'Film'),
        ('LO', 'Loom Saswad'),
        ('TP', 'Tape'),
        ('LM', 'Lamination'),
        ('FL', 'FIBC'),
        ('FB', 'Fabrication'),
        ('WB', 'Belt'),
        ('PH', 'Pouch'),
        ('TL', 'Tarpaulin'),
        ('CO', 'Coting'),
        # …the rest…
    ]:
        Department.objects.get_or_create(code=code, name=name)

class Migration(migrations.Migration):
    dependencies = [
        ('warehouse', '0001_initial'),  # or whatever your first migration is
    ]
    operations = [
        migrations.RunPython(seed_departments, reverse_code=migrations.RunPython.noop),
    ]
