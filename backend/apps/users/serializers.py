import re
from datetime import date

from rest_framework import serializers
from .models import User, KYCProfile


# ─────────────────────────────────────────────────────────────
# VALIDATORS
# ─────────────────────────────────────────────────────────────

def validate_kenyan_phone(value):
    """Accepts international Kenyan format: 2547XXXXXXXX (12 digits)."""
    if not re.match(r'^2547\d{8}$', value):
        raise serializers.ValidationError(
            "Phone number must be in format 2547XXXXXXXX (e.g. 254712345678)."
        )
    return value


# ─────────────────────────────────────────────────────────────
# AUTH SERIALIZERS
# ─────────────────────────────────────────────────────────────

class PhoneSerializer(serializers.Serializer):
    phone_number = serializers.CharField(validators=[validate_kenyan_phone])


class OTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField(validators=[validate_kenyan_phone])
    otp          = serializers.CharField(max_length=6, min_length=6)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be 6 digits.")
        return value


class PinSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=6, min_length=6)

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must be a 6-digit number.")
        return value


# ─────────────────────────────────────────────────────────────
# USER PROFILE SERIALIZER
# ─────────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    kyc_status = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id',
            'phone_number',
            'name',
            'bio',
            'profile_photo',
            'is_phone_verified',
            'is_pin_set',
            'kyc_status',
        ]
        read_only_fields = [
            'id',
            'phone_number',
            'is_phone_verified',
            'is_pin_set',
            'kyc_status',
        ]

    def get_kyc_status(self, obj) -> str:
        try:
            return obj.kyc.status
        except KYCProfile.DoesNotExist:
            return 'not_submitted'


# ─────────────────────────────────────────────────────────────
# KYC SERIALIZERS
# ─────────────────────────────────────────────────────────────

class KYCSubmitSerializer(serializers.ModelSerializer):
    """
    Used for POST /api/users/kyc/ — accepts multipart/form-data
    so ID scan images can be uploaded.
    """

    class Meta:
        model  = KYCProfile
        fields = [
            'given_names',
            'surname',
            'id_number',
            'date_of_birth',
            'email',
            'id_front',
            'id_back',
            'county',
            'sub_county',
            'occupation',
            'source_of_income',
            'expected_monthly_income',
            'referral_code',
        ]

    def validate_id_number(self, value):
        """Kenyan national ID / Passport: 7–9 digits for national ID."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("ID number is required.")
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        age   = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError("You must be at least 18 years old.")
        if age > 120:
            raise serializers.ValidationError("Invalid date of birth.")
        return value

    def validate_given_names(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Given names are required.")
        return value

    def validate_surname(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Surname is required.")
        return value


class KYCStatusSerializer(serializers.ModelSerializer):
    """
    Used for GET /api/users/kyc/ — returns full KYC state plus
    dropdown choices for the mobile form.
    """
    counties       = serializers.SerializerMethodField()
    income_bands   = serializers.SerializerMethodField()
    income_sources = serializers.SerializerMethodField()
    full_name      = serializers.CharField(read_only=True)

    # Include image URLs (absolute) when a request context is provided
    id_front = serializers.SerializerMethodField()
    id_back  = serializers.SerializerMethodField()

    class Meta:
        model  = KYCProfile
        fields = [
            'id',
            'given_names',
            'surname',
            'full_name',
            'id_number',
            'date_of_birth',
            'email',
            'id_front',
            'id_back',
            'county',
            'sub_county',
            'occupation',
            'source_of_income',
            'expected_monthly_income',
            'referral_code',
            'status',
            'rejection_reason',
            'submitted_at',
            'updated_at',
            # helpers for the mobile form
            'counties',
            'income_bands',
            'income_sources',
        ]
        read_only_fields = fields

    def _abs(self, img):
        """Return absolute URL for an image field, or None."""
        if not img:
            return None
        request = self.context.get('request')
        url     = img.url
        return request.build_absolute_uri(url) if request else url

    def get_id_front(self, obj):
        return self._abs(obj.id_front)

    def get_id_back(self, obj):
        return self._abs(obj.id_back)

    def get_counties(self, obj):
        return [c[0] for c in KYCProfile.KENYA_COUNTIES]

    def get_income_bands(self, obj):
        return [{'value': v, 'label': l} for v, l in KYCProfile.INCOME_BAND_CHOICES]

    def get_income_sources(self, obj):
        return [{'value': v, 'label': l} for v, l in KYCProfile.SOURCE_CHOICES]
