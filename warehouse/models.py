from django.db import models
from django.contrib.auth.models import User
import uuid
from django.utils import timezone

class Department(models.Model):
    code = models.CharField(max_length=4, unique=True)  # e.g. "FM", "LM"
    name = models.CharField(max_length=64)              # e.g. "Film", "Lamination"

    def __str__(self):
        return f"{self.code} – {self.name}"
# ─────────────────────────────────────────────────────────────────────────────
# Core domain models
# ─────────────────────────────────────────────────────────────────────────────

class Material(models.Model):
    material_number = models.CharField(max_length=50, unique=True)
    description     = models.CharField(max_length=200)

    # ← NEW fields →
    department    = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True, blank=True,
        help_text="Which department first registered this material",
    )
    created_by    = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        editable=False,
        help_text="Which user first created this material"
    )
    created_at    = models.DateTimeField(
#        auto_now_add=True,
        default=timezone.now,
        editable=False
    )

    def __str__(self):
        return self.material_number

class Batch(models.Model):
    batch_number = models.CharField(max_length=50)
    material     = models.ForeignKey(Material, on_delete=models.CASCADE)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('material', 'batch_number')]

    def __str__(self):
        return f"{self.batch_number} – {self.material.material_number}"


class Customer(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Roll(models.Model):
    roll_id           = models.UUIDField(default=uuid.uuid4,
                                        editable=False, unique=True)
    batch             = models.ForeignKey(Batch, on_delete=models.CASCADE)
    weight_kg         = models.FloatField()
    customer          = models.ForeignKey(Customer,
                                          on_delete=models.SET_NULL,
                                          null=True, blank=True)
    current_location  = models.CharField(max_length=20,
                                         blank=True, null=True)
    status            = models.CharField(max_length=20,
                                         default='IN_STOCK')

    def __str__(self):
        return str(self.roll_id)


# ─────────────────────────────────────────────────────────────────────────────
# Warehouse layout models
# ─────────────────────────────────────────────────────────────────────────────




class Location(models.Model):
    location_code = models.CharField(max_length=10, unique=True)
    department    = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='locations',
        null=True, blank=True,   # allow empty for existing data; remove once backfilled
    )
    row      = models.CharField(max_length=5, blank=True)
    column   = models.CharField(max_length=5, blank=True)
    TYPE_CHOICES = [
        ('STORAGE',    'Storage'),
        ('DEPT',       'Dept'),
        ('DISPATCH',   'Dispatch'),
    ]
    type     = models.CharField(max_length=20, choices=TYPE_CHOICES)

    def __str__(self):
        return self.location_code


class Transaction(models.Model):
    ACTIONS = [
        ('QA_SCAN',     'QA Scan'),
        ('PUTAWAY',     'Putaway'),
        ('TRANSFER',    'Transfer'),
        ('DISPATCH',    'Dispatch'),
        ('TEMP_STORAGE','Temp Storage'),
    ]
    roll       = models.ForeignKey(Roll, on_delete=models.CASCADE)
    action     = models.CharField(max_length=20, choices=ACTIONS)
    location   = models.ForeignKey(Location,
                                   on_delete=models.SET_NULL,
                                   null=True, blank=True)
    user       = models.CharField(max_length=50)
    scanned_at = models.DateTimeField(auto_now_add=True)
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Who this roll was dispatched to (if action=DISPATCH)."
    )

    def __str__(self):
        return f"{self.roll.roll_id} – {self.action}"


# ─────────────────────────────────────────────────────────────────────────────
# User profile + permissions
# ─────────────────────────────────────────────────────────────────────────────

ROLE_CHOICES = [
    ('Factory Admin',   'Factory Admin'),
    ('Plant Manager',   'Plant Manager'),
    ('Stock Keeper',    'Stock Keeper'),
    ('Operator',        'Operator'),
    ('Forklift Driver', 'Forklift Driver'),
    ('Dept SK',         'Dept SK'),
    ('View Only',       'View Only'),
]

class Profile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE)
    phone           = models.CharField(max_length=20)
    pin             = models.CharField(max_length=4)
    id_card         = models.ImageField(upload_to='id_cards/')
    needs_approval  = models.BooleanField(default=True)
    requested_group = models.CharField(max_length=50,
                                       choices=ROLE_CHOICES)
    department      = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True, blank=True,   # allow until you backfill existing rows
        help_text="Home department",
        default=1,
    )
    extra_access    = models.CharField(
        max_length=100, blank=True,
        help_text="Stock Keeper only: comma‑separated extra dept codes"
    )

    def get_extra_access_list(self):
        return [d.strip() for d in self.extra_access.split(',') if d.strip()]

    def __str__(self):
        dept = self.department.code if self.department else '—'
        return f"{self.user.username} ({self.requested_group}, {dept})"


# auto‑create a Profile for every new User
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def ensure_profile(sender, instance, **kwargs):
    Profile.objects.get_or_create(user=instance)


# ─────────────────────────────────────────────────────────────────────────────
# Site‑wide configuration toggle
# ─────────────────────────────────────────────────────────────────────────────

class SiteConfig(models.Model):
    enable_qa_scan = models.BooleanField(default=True)

    def __str__(self):
        return "Site Configuration"

    class Meta:
        verbose_name        = "Site Configuration"
        verbose_name_plural = "Site Configuration"





class ReconciliationLog(models.Model):
    run_at     = models.DateTimeField(auto_now_add=True)
    is_clean   = models.BooleanField(
        default=True,
        help_text="True if dashboard/API counts matched"
    )
    mismatches = models.TextField(
        blank=True,
        help_text="One line per location: e.g. 'FMA01: dash=8 vs api=7'"
    )

    def __str__(self):
        return f"{self.run_at:%Y-%m-%d %H:%M} – {'OK' if self.is_clean else '❌'}"




class ImportLog(models.Model):
    run_at      = models.DateTimeField(auto_now_add=True)
    total_rows  = models.IntegerField()
    imported    = models.IntegerField()
    skipped     = models.IntegerField()
    details     = models.TextField(
        blank=True,
        help_text="One line per skipped row: material|batch"
    )
