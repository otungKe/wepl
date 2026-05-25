from datetime import date
from rest_framework import serializers
from .models import User, KYCProfile


# -----------------------------
# PHONE AUTH SERIALIZER (NO PASSWORDS)
# -----------------------------
class PhoneSerializer(serializers.Serializer):
    phone_number = serializers.CharField()


# -----------------------------
# OTP VERIFY SERIALIZER
# -----------------------------
class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField(max_length=6)


# -----------------------------
# PIN SERIALIZER
# -----------------------------
class PINSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=6)

    def validate_pin(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("PIN must be exactly 6 digits")
        return value


# -----------------------------
# USER PROFILE SERIALIZER
# -----------------------------
class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "bio",
            "profile_photo",
            "pin"
        ]
        read_only_fields = ["id", "phone_number", "pin"]


class KYCSubmitSerializer(serializers.ModelSerializer):
    """Used for initial submission and re-submission after rejection."""

    class Meta:
        model  = KYCProfile
        fields = [
            'given_names', 'surname', 'id_number', 'date_of_birth', 'email',
            'id_front', 'id_back',
            'county', 'sub_county',
            'occupation', 'source_of_income', 'expected_monthly_income',
            'referral_code',
        ]

    def validate_id_number(self, value):
        qs = KYCProfile.objects.filter(id_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This ID number is already registered.")
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - (
            (today.month, today.day) < (value.month, value.day)
        )
        if age < 18:
            raise serializers.ValidationError(
                "You must be at least 18 years old to register."
            )
        return value


class KYCStatusSerializer(serializers.ModelSerializer):
    """Read-only view returned to the user after submission."""
    counties       = serializers.SerializerMethodField()
    income_bands   = serializers.SerializerMethodField()
    income_sources = serializers.SerializerMethodField()

    class Meta:
        model  = KYCProfile
        fields = [
            'id', 'given_names', 'surname', 'id_number', 'date_of_birth', 'email',
            'id_front', 'id_back',
            'county', 'sub_county',
            'occupation', 'source_of_income', 'expected_monthly_income',
            'referral_code',
            'status', 'rejection_reason',
            'submitted_at', 'updated_at',
            'counties', 'income_bands', 'income_sources',
        ]
        read_only_fields = fields

    def get_counties(self, obj):
        return [c[0] for c in KYCProfile.KENYA_COUNTIES]

    def get_income_bands(self, obj):
        return [{'value': v, 'label': l} for v, l in KYCProfile.INCOME_BAND_CHOICES]

    def get_income_sources(self, obj):
        return [{'value': v, 'label': l} for v, l in KYCProfile.SOURCE_CHOICES]