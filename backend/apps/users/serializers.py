import re
from datetime import date

from rest_framework import serializers
from .models import User, KYCProfile, UserSession, VerificationRequest, PaymentMethod


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
        extra_kwargs = {
            'profile_photo': {'required': False, 'allow_null': True},
        }

    def get_kyc_status(self, obj) -> str:
        try:
            return obj.kyc.status
        except KYCProfile.DoesNotExist:
            return 'not_submitted'

    def to_representation(self, instance):
        """
        Override to return an absolute URL for profile_photo.

        SerializerMethodField was NOT used because it makes the field
        read-only, silently discarding the uploaded file on PATCH.
        Using to_representation keeps the field writable while still
        controlling the output URL format.
        """
        data = super().to_representation(instance)

        if instance.profile_photo:
            try:
                url = instance.profile_photo.url
                # MinIO/S3 returns a full URL already; local storage returns
                # a relative path — make it absolute using the request context.
                if url and not url.startswith("http"):
                    request = self.context.get("request")
                    if request:
                        url = request.build_absolute_uri(url)
                data['profile_photo'] = url
            except Exception:
                data['profile_photo'] = None

        return data


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
            'kra_pin',
            'date_of_birth',
            'email',
            'id_front',
            'id_back',
            'selfie',
            'county',
            'physical_address',
            'occupation',
            'source_of_income',
            'expected_monthly_income',
            'referral_code',
        ]
        extra_kwargs = {
            'email': {
                'required': True,
                'allow_blank': False,
                'error_messages': {'required': 'Email address is required for identity verification.'},
            },
            'physical_address': {
                'required': True,
                'allow_blank': False,
                'error_messages': {'required': 'Physical address is required.'},
            },
            # KRA PIN — entered manually for now (a vendor may auto-populate it
            # post-verification later). Required at submit; format-checked below.
            'kra_pin': {
                'required': True,
                'allow_blank': False,
                'error_messages': {'required': 'KRA PIN is required.'},
            },
            # Both sides of the ID and a live selfie are mandatory so a human
            # reviewer always has the full document set to verify against (and a
            # vendor has the selfie to run liveness on). The model keeps these
            # nullable for backward compatibility with historical rows; new
            # submissions and re-submissions must include them.
            'id_front': {
                'required': True,
                'error_messages': {'required': 'A photo of the front of your ID is required.'},
            },
            'id_back': {
                'required': True,
                'allow_null': False,
                'error_messages': {'required': 'A photo of the back of your ID is required.'},
            },
            'selfie': {
                'required': True,
                'allow_null': False,
                'error_messages': {'required': 'A selfie is required to verify your identity.'},
            },
        }

    def validate_id_number(self, value):
        """Kenyan national ID / Passport: 7–9 digits for national ID."""
        value = value.strip()
        if not value:
            raise serializers.ValidationError("ID number is required.")
        return value

    def validate_kra_pin(self, value):
        """KRA PIN format: a letter, 9 digits, then a letter (e.g. A012345678Z)."""
        value = (value or "").strip().upper()
        if not re.match(r"^[A-Z]\d{9}[A-Z]$", value):
            raise serializers.ValidationError(
                "Enter a valid KRA PIN, e.g. A012345678Z."
            )
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
            'email_verified',
            'id_front',
            'id_back',
            'county',
            'physical_address',
            'occupation',
            'source_of_income',
            'expected_monthly_income',
            'referral_code',
            'status',
            'rejection_reason',
            'resubmission_requested',
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


# ─────────────────────────────────────────────────────────────
# USER SESSION (device/session registry — ADR-0010)
# ─────────────────────────────────────────────────────────────

class UserSessionSerializer(serializers.ModelSerializer):
    """Serialize a session for the 'where am I logged in' screen. Flags the
    session that the requesting token belongs to via context['current_sid']."""

    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = (
            "sid", "device_label", "ip_address",
            "created_at", "last_seen_at", "is_current",
        )

    def get_is_current(self, obj) -> bool:
        return str(obj.sid) == self.context.get("current_sid")


class VerificationRequestSerializer(serializers.ModelSerializer):
    """Read serializer for the mobile Verification Center's requests section."""
    kind_label   = serializers.CharField(source='get_kind_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = VerificationRequest
        fields = (
            'id', 'kind', 'kind_label', 'title', 'detail',
            'status', 'status_label', 'response_note', 'document',
            'review_note', 'created_at', 'responded_at', 'resolved_at',
        )
        read_only_fields = fields


class VerificationRespondSerializer(serializers.Serializer):
    """User's answer to an open request: a note and/or a document."""
    response_note = serializers.CharField(required=False, allow_blank=True, default='')
    document      = serializers.FileField(required=False)

    def validate(self, attrs):
        if not (attrs.get('response_note') or '').strip() and not attrs.get('document'):
            raise serializers.ValidationError(
                "Add a note or attach a document to submit your response."
            )
        return attrs


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Read serializer for the Payment methods screen."""
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    display    = serializers.CharField(read_only=True)

    class Meta:
        model = PaymentMethod
        fields = (
            'id', 'kind', 'kind_label', 'label', 'is_default', 'status', 'display',
            'mpesa_phone', 'card_brand', 'card_last4', 'card_exp',
            'bank_name', 'bank_account_last4', 'created_at',
        )
        read_only_fields = fields
