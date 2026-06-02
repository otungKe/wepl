from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.hashers import make_password, check_password


# ─────────────────────────────────────────────────────────────
# CUSTOM USER MANAGER
# ─────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number must be provided')
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone_number, password, **extra_fields)


# ─────────────────────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────────────────────

class User(AbstractUser):
    username = None  # removed — phone_number is the unique identifier
    phone_number = models.CharField(max_length=15, unique=True)
    name         = models.CharField(max_length=120, blank=True, default="")
    pin          = models.CharField(max_length=128, blank=True, default="")

    is_phone_verified = models.BooleanField(default=False)
    is_pin_set        = models.BooleanField(default=False)
    last_seen         = models.DateTimeField(null=True, blank=True, db_index=True)

    profile_photo = models.ImageField(upload_to='profile/', blank=True, null=True)
    bio           = models.TextField(blank=True, default="")

    USERNAME_FIELD  = 'phone_number'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def set_pin(self, raw_pin: str):
        if not raw_pin.isdigit() or len(raw_pin) != 6:
            raise ValidationError("PIN must be a 6-digit number.")
        self.pin       = make_password(raw_pin)
        self.is_pin_set = True
        self.save(update_fields=['pin', 'is_pin_set'])

    def check_pin(self, raw_pin: str) -> bool:
        if not self.pin:
            return False
        return check_password(raw_pin, self.pin)

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


# ─────────────────────────────────────────────────────────────
# KYC PROFILE
# ─────────────────────────────────────────────────────────────

class KYCProfile(models.Model):

    KENYA_COUNTIES = [
        ('Baringo', 'Baringo'), ('Bomet', 'Bomet'), ('Bungoma', 'Bungoma'),
        ('Busia', 'Busia'), ('Elgeyo-Marakwet', 'Elgeyo-Marakwet'), ('Embu', 'Embu'),
        ('Garissa', 'Garissa'), ('Homa Bay', 'Homa Bay'), ('Isiolo', 'Isiolo'),
        ('Kajiado', 'Kajiado'), ('Kakamega', 'Kakamega'), ('Kericho', 'Kericho'),
        ('Kiambu', 'Kiambu'), ('Kilifi', 'Kilifi'), ('Kirinyaga', 'Kirinyaga'),
        ('Kisii', 'Kisii'), ('Kisumu', 'Kisumu'), ('Kitui', 'Kitui'),
        ('Kwale', 'Kwale'), ('Laikipia', 'Laikipia'), ('Lamu', 'Lamu'),
        ('Machakos', 'Machakos'), ('Makueni', 'Makueni'), ('Mandera', 'Mandera'),
        ('Marsabit', 'Marsabit'), ('Meru', 'Meru'), ('Migori', 'Migori'),
        ('Mombasa', 'Mombasa'), ("Murang'a", "Murang'a"), ('Nairobi', 'Nairobi'),
        ('Nakuru', 'Nakuru'), ('Nandi', 'Nandi'), ('Narok', 'Narok'),
        ('Nyamira', 'Nyamira'), ('Nyandarua', 'Nyandarua'), ('Nyeri', 'Nyeri'),
        ('Samburu', 'Samburu'), ('Siaya', 'Siaya'), ('Taita-Taveta', 'Taita-Taveta'),
        ('Tana River', 'Tana River'), ('Tharaka-Nithi', 'Tharaka-Nithi'),
        ('Trans Nzoia', 'Trans Nzoia'), ('Turkana', 'Turkana'),
        ('Uasin Gishu', 'Uasin Gishu'), ('Vihiga', 'Vihiga'),
        ('Wajir', 'Wajir'), ('West Pokot', 'West Pokot'),
    ]

    SOURCE_CHOICES = [
        ('employment',  'Employment / Salary'),
        ('business',    'Business / Self-employment'),
        ('investment',  'Investment Returns'),
        ('pension',     'Pension / Retirement'),
        ('rental',      'Rental Income'),
        ('remittance',  'Remittance from Abroad'),
        ('farming',     'Farming / Agriculture'),
        ('other',       'Other'),
    ]

    INCOME_BAND_CHOICES = [
        ('under_250k', 'Up to KES 250,000 / month'),
        ('250k_to_1m', 'KES 250,001 – 1,000,000 / month'),
        ('above_1m',   'Above KES 1,000,000 / month'),
    ]

    STATUS_CHOICES = [
        ('pending',  'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='kyc',
    )

    # Identity
    given_names = models.CharField(max_length=150)
    surname     = models.CharField(max_length=100, default='')
    id_number   = models.CharField(max_length=20, unique=True)
    date_of_birth = models.DateField()
    email       = models.EmailField(blank=True, default='')

    # ID documents + selfie
    id_front = models.ImageField(upload_to='kyc/ids/')
    id_back  = models.ImageField(upload_to='kyc/ids/', blank=True, null=True)
    selfie   = models.ImageField(upload_to='kyc/selfies/', blank=True, null=True)

    # Location & financials
    county                  = models.CharField(max_length=50, choices=KENYA_COUNTIES)
    physical_address        = models.CharField(max_length=255, blank=False, default='')
    occupation              = models.CharField(max_length=255)
    source_of_income        = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    expected_monthly_income = models.CharField(max_length=20, choices=INCOME_BAND_CHOICES)

    # Optional
    referral_code = models.CharField(max_length=50, blank=True, default='')

    # Review state
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, default='')
    reviewed_at      = models.DateTimeField(null=True, blank=True)
    reviewed_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='kyc_reviews',
    )

    # Email verification
    email_verified              = models.BooleanField(default=False)
    email_verification_token    = models.CharField(max_length=64, blank=True, default='')
    email_verification_sent_at  = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='kyc_status_idx'),
        ]

    def __str__(self):
        return f"KYC({self.user.phone_number}) — {self.status}"

    @property
    def full_name(self):
        return f"{self.given_names} {self.surname}".strip()


# ─────────────────────────────────────────────────────────────
# PRIVACY PREFERENCES
# ─────────────────────────────────────────────────────────────

class PrivacyPreferences(models.Model):
    """
    Per-user privacy settings.

    One row per user, auto-created on first access with sensible defaults.
    Enforced in serializers and service-layer lookups — not just stored client-side.
    """

    VISIBILITY_CHOICES = [
        ('everyone', 'Everyone'),
        ('members',  'My communities only'),
        ('nobody',   'Only me'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='privacy_prefs',
    )

    # Profile visibility
    phone_visibility        = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='members')
    photo_visibility        = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='everyone')
    # Financial
    contribution_visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='members')
    # Discovery
    discoverable            = models.BooleanField(default=True)
    # Chat
    show_online_status      = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Privacy({self.user.phone_number})"
