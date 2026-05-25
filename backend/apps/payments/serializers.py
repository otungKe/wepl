from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):

    # -----------------------------
    # USER DISPLAY (PHONE-BASED IDENTITY)
    # replaces username system
    # -----------------------------
    user = serializers.CharField(
        source='user.phone_number',
        read_only=True
    )

    # -----------------------------
    # WHO RECORDED PAYMENT
    # -----------------------------
    recorded_by = serializers.CharField(
        source='recorded_by.phone_number',
        read_only=True
    )

    # -----------------------------
    # FRONTEND CONVENIENCE FIELD
    # avoids extra API calls
    # -----------------------------
    contribution_title = serializers.CharField(
        source='contribution.title',
        read_only=True
    )

    class Meta:
        model = Payment

        fields = [
            'id',
            'contribution',
            'contribution_title',
            'user',
            'amount',
            'reference',
            'status',
            'recorded_by',
            'created_at',
        ]