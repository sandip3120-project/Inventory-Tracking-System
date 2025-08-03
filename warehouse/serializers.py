from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.conf import settings
from .models import Material, Batch, Customer, Roll, Location, Transaction

class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Material
        fields = '__all__'

class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Batch
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Customer
        fields = '__all__'



class RollSerializer(serializers.ModelSerializer):
    # existing QR fields
    qr_link       = serializers.SerializerMethodField()
    qr_image_url  = serializers.SerializerMethodField()

    # new read‑only roll metadata
    status            = serializers.SerializerMethodField()
    material_number   = serializers.CharField(
        source='batch.material.material_number', read_only=True
    )
    description       = serializers.CharField(
        source='batch.material.description', read_only=True
    )
    batch_number      = serializers.CharField(
        source='batch.batch_number', read_only=True
    )
    posting_date      = serializers.SerializerMethodField()
    dispatch_customer = serializers.SerializerMethodField()

    class Meta:
        model = Roll
        fields = [
            'roll_id',
            'material_number', 'description', 'batch_number',
            'weight_kg', 'current_location','status', 'status',
            'posting_date', 'dispatch_customer',
            'qr_link', 'qr_image_url',
        ]
        read_only_fields = [
            'roll_id', 'current_location', 'status',
            'posting_date', 'dispatch_customer',
            'qr_link', 'qr_image_url',
        ]
    def get_status(self, obj):
        # Look at the very last transaction
        last_tx = obj.transaction_set.order_by('-scanned_at').first()
        if not last_tx:
            return "Yet to store or dispatch"

        if last_tx.action == 'DISPATCH' and last_tx.customer:
            return f"Dispatched to {last_tx.customer.name}"

        if last_tx.action in ('PUTAWAY', 'TRANSFER', 'TEMP_STORAGE') and last_tx.location:
            # location is a FK to Location, so use its code
            return f"In stock at {last_tx.location.location_code}"

        return "Yet to store or dispatch"     

    def get_qr_link(self, obj):
        return f"{settings.SITE_URL}/r/{obj.roll_id}"

    def get_qr_image_url(self, obj):
        return f"{settings.SITE_URL}{settings.MEDIA_URL}qrcodes/{obj.roll_id}.png"

    def get_posting_date(self, obj):
        # last transaction timestamp, or None
        last_tx = obj.transaction_set.order_by('-scanned_at').first()
        return last_tx.scanned_at if last_tx else None

    def get_dispatch_customer(self, obj):
        # if the last action was a DISPATCH, return its customer name
        last_dispatch = (
            obj.transaction_set
               .filter(action='DISPATCH')
               .order_by('-scanned_at')
               .first()
        )
        return getattr(last_dispatch, 'customer', None) and last_dispatch.customer.name or None

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Location
        fields = '__all__'



class TransactionSerializer(serializers.ModelSerializer):
    # Accept the Roll.roll_id (UUID) instead of its integer PK
    roll = serializers.SlugRelatedField(
        queryset=Roll.objects.all(),
        slug_field='roll_id'
    )
    # Accept the Location.location_code (string) instead of its integer PK
    location = serializers.SlugRelatedField(
        queryset=Location.objects.all(),
        slug_field='location_code',
        allow_null=True,
        required=False
    )
    customer = serializers.CharField(required=False, allow_blank=False)    

    class Meta:
        model = Transaction
        fields = '__all__'

    def validate(self, data):
        roll = data['roll']
        next_action = data['action']

        # Fetch the last transaction (if any)
        last_tx = (
            Transaction.objects
            .filter(roll=roll)
            .order_by('-scanned_at')
            .first()
        )
        last_action = last_tx.action if last_tx else None

        # Define your allowed transitions
        allowed = {
            None:      ['PUTAWAY','DISPATCH','TRANSFER'],  
            'PUTAWAY': ['DISPATCH','TRANSFER'],
            'TRANSFER':['PUTAWAY','DISPATCH'],
            'QA_SCAN': ['PUTAWAY', 'DISPATCH', 'TRANSFER'],                   # if you support transfer→putaway
            # no transitions allowed _from_ DISPATCH
        }

        legal_next = allowed.get(last_action, [])

        if next_action not in legal_next:
            raise ValidationError({
                'action': (
                    f"Invalid transition: cannot do '{next_action}' after "
                    f"'{last_action}'. Allowed: {legal_next or 'none'}."
                )
            })

        return data
    def create(self, validated_data):
        name = validated_data.pop('customer', None)
        if name:
            # find or create the Customer record
            customer_obj, _ = Customer.objects.get_or_create(name=name)
            validated_data['customer'] = customer_obj

        # Auto-create the customer if a new name is provided
#        cust_name = validated_data.pop('customer', None)
#        if cust_name:
#            customer_obj, _ = Customer.objects.get_or_create(name=cust_name)
#            validated_data['customer'] = customer_obj
        return super().create(validated_data)
    