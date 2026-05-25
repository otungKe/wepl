from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class User(AbstractUser):

    # remove username completely
    username = None

    phone_number = models.CharField(
        max_length=20,
        unique=True
    )

    name = models.CharField(max_length=120, blank=True, default='')

    # store hashed PIN (VERY IMPORTANT)
    pin = models.CharField(
        max_length=128,
        null=True,
        blank=True
    )

    # onboarding state tracking
    is_phone_verified = models.BooleanField(default=False)
    is_pin_set = models.BooleanField(default=False)

    profile_photo = models.ImageField(
        upload_to="profiles/",
        null=True,
        blank=True
    )

    bio = models.TextField(null=True, blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    # -------------------------
    # PIN SECURITY METHODS
    # -------------------------
    def set_pin(self, raw_pin):
        if len(raw_pin) != 6 or not raw_pin.isdigit():
            raise ValidationError("PIN must be 6 digits")

        self.pin = make_password(raw_pin)
        self.is_pin_set = True
        self.save()

    def check_pin(self, raw_pin):
        if not self.pin:
            return False
        return check_password(raw_pin, self.pin)

    def __str__(self):
        return self.phone_number


class KYCProfile(models.Model):

    KENYA_COUNTIES = [(c, c) for c in [
        'Baringo', 'Bomet', 'Bungoma', 'Busia', 'Elgeyo-Marakwet', 'Embu',
        'Garissa', 'Homa Bay', 'Isiolo', 'Kajiado', 'Kakamega', 'Kericho',
        'Kiambu', 'Kilifi', 'Kirinyaga', 'Kisii', 'Kisumu', 'Kitui', 'Kwale',
        'Laikipia', 'Lamu', 'Machakos', 'Makueni', 'Mandera', 'Marsabit',
        'Meru', 'Migori', 'Mombasa', "Murang'a", 'Nairobi', 'Nakuru', 'Nandi',
        'Narok', 'Nyamira', 'Nyandarua', 'Nyeri', 'Samburu', 'Siaya',
        'Taita-Taveta', 'Tana River', 'Tharaka-Nithi', 'Trans Nzoia',
        'Turkana', 'Uasin Gishu', 'Vihiga', 'Wajir', 'West Pokot',
    ]]

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
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='kyc'
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    given_names     = models.CharField(max_length=150)
    surname         = models.CharField(max_length=100)
    id_number       = models.CharField(max_length=20, unique=True)
    date_of_birth   = models.DateField()
    email           = models.EmailField(blank=True, default='')

    # ── ID document scans ─────────────────────────────────────────────────────
    id_front = models.ImageField(upload_to='kyc/ids/')
    id_back  = models.ImageField(upload_to='kyc/ids/', blank=True, null=True)

    # ── Address ───────────────────────────────────────────────────────────────
    county     = models.CharField(max_length=50, choices=KENYA_COUNTIES)
    sub_county = models.CharField(max_length=100, blank=True, default='')

    # ── Financial profile ─────────────────────────────────────────────────────
    occupation               = models.CharField(max_length=255)
    source_of_income         = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    expected_monthly_income  = models.CharField(max_length=20, choices=INCOME_BAND_CHOICES)

    # ── Optional ──────────────────────────────────────────────────────────────
    referral_code = models.CharField(max_length=50, blank=True, default='')

    # ── Review lifecycle ──────────────────────────────────────────────────────
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True, default='')
    reviewed_at      = models.DateTimeField(null=True, blank=True)
    reviewed_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='kyc_reviews',
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='kyc_status_idx'),
        ]

    def __str__(self):
        return f"KYC({self.user.phone_number}) — {self.status}"