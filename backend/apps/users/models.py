import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.hashers import make_password, check_password

# Unambiguous base32 (no 0/1/I/L/O/U) — member numbers get read aloud on support
# calls, so avoid characters people confuse.
_MEMBER_NO_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_member_number() -> str:
    """An opaque, non-PII member handle, e.g. ``WM-7F9K2``."""
    return "WM-" + "".join(secrets.choice(_MEMBER_NO_ALPHABET) for _ in range(5))


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

    # Stable, non-PII member handle (e.g. WM-7F9K2). Shareable in support without
    # saying the phone aloud, survives a phone-number change, searchable in ops.
    # Phone number remains the authentication identifier.
    member_number = models.CharField(
        max_length=16, unique=True, null=True, blank=True, db_index=True)

    USERNAME_FIELD  = 'phone_number'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.member_number:
            self.member_number = self._unique_member_number()
        super().save(*args, **kwargs)

    @classmethod
    def _unique_member_number(cls) -> str:
        for _ in range(12):
            candidate = generate_member_number()
            if not cls.objects.filter(member_number=candidate).exists():
                return candidate
        # Astronomically unlikely — widen to remove any doubt.
        return "WM-" + "".join(secrets.choice(_MEMBER_NO_ALPHABET) for _ in range(9))

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

    # ── Access tiers (ADR-0022) ──────────────────────────────────────────────
    # Derived from verification state — nothing extra is stored.
    #   Tier 0: identity verified (phone), KYC not yet approved  → discovery only
    #   Tier 1: identity verified + KYC approved                 → full access
    @property
    def kyc_status(self) -> str:
        """'not_submitted' | 'pending' | 'approved' | 'rejected' — safe if no KYC."""
        try:
            return self.kyc.status
        except self.__class__.kyc.RelatedObjectDoesNotExist:
            return 'not_submitted'

    @property
    def is_tier1(self) -> bool:
        """Full access: phone verified AND KYC approved (pending/rejected do not qualify)."""
        return bool(self.is_phone_verified) and self.kyc_status == 'approved'

    @property
    def is_tier0(self) -> bool:
        """Verified identity, not yet KYC-approved."""
        return not self.is_tier1

    def has_full_access(self) -> bool:
        return self.is_tier1

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

    # Items a reviewer can ask the user to re-provide on a targeted re-submission.
    # Each key is a KYCProfile field the user tops up via /kyc/resubmit/ without
    # re-entering the rest of the form.
    RESUBMITTABLE_ITEMS = [
        ('id_front',                'Front of ID'),
        ('id_back',                 'Back of ID'),
        ('selfie',                  'Selfie'),
        ('id_number',               'ID number'),
        ('kra_pin',                 'KRA PIN'),
        ('date_of_birth',           'Date of birth'),
        ('physical_address',        'Physical address'),
        ('county',                  'County'),
        ('occupation',              'Occupation'),
        ('source_of_income',        'Source of income'),
        ('expected_monthly_income', 'Income band'),
        ('email',                   'Email address'),
    ]
    RESUBMITTABLE_KEYS = [k for k, _ in RESUBMITTABLE_ITEMS]

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
    # KRA (Kenya Revenue Authority) tax PIN. Entered manually today; a future
    # identity-verification vendor may auto-populate it after ID verification
    # (ADR-0023). Kept blank-able at the model level; required at submit.
    kra_pin     = models.CharField(max_length=11, blank=True, default='')

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

    # Identity-verification provider outcome (apps.users.identity port).
    # Records which checker ran and what it returned — audit trail for both
    # manual review and any future automated vendor. `verification_state` holds
    # the normalised IdentityCheckResult.state; the KYC `status` is derived from it.
    verification_provider   = models.CharField(max_length=40, blank=True, default='')
    verification_ref        = models.CharField(max_length=128, blank=True, default='')
    verification_state      = models.CharField(max_length=20, blank=True, default='')
    verification_detail     = models.JSONField(default=dict, blank=True)
    verification_checked_at = models.DateTimeField(null=True, blank=True)

    # Email verification
    email_verified              = models.BooleanField(default=False)
    email_verification_token    = models.CharField(max_length=64, blank=True, default='')
    email_verification_sent_at  = models.DateTimeField(null=True, blank=True)

    # Targeted re-submission: the specific items a reviewer has asked the user to
    # re-provide (subset of RESUBMITTABLE_ITEM keys, e.g. ['id_front','selfie']).
    # Empty = nothing outstanding. The user tops up ONLY these via /kyc/resubmit/
    # — they do not re-enter the whole KYC form.
    resubmission_requested = models.JSONField(default=list, blank=True)

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


# ─────────────────────────────────────────────────────────────
# USER SESSION (device/session registry — ADR-0010)
# ─────────────────────────────────────────────────────────────

class UserSession(models.Model):
    """One row per active login, keyed by a ``sid`` UUID embedded in the JWT.

    The ``sid`` survives refresh-token rotation (SimpleJWT copies non-reserved
    claims), so a single row represents the whole rotation chain of one login.
    Setting ``revoked_at`` kills the session: both the authentication class and
    the refresh view reject any token whose ``sid`` points here.
    """
    import uuid as _uuid

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions",
    )
    sid = models.UUIDField(default=_uuid.uuid4, editable=False, unique=True, db_index=True)

    device_label = models.CharField(max_length=120, blank=True, default="")
    user_agent   = models.CharField(max_length=400, blank=True, default="")
    ip_address   = models.GenericIPAddressField(null=True, blank=True)

    created_at   = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    revoked_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="usersession_user_active_idx"),
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        state = "revoked" if self.revoked_at else "active"
        return f"Session({self.user_id}, {self.device_label or 'device'}, {state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


# ─────────────────────────────────────────────────────────────
# VERIFICATION REQUESTS (ongoing compliance)
# ─────────────────────────────────────────────────────────────

class VerificationRequest(models.Model):
    """A follow-up item the compliance team raises against a user — before OR
    after KYC approval. Backs the mobile Verification Center's ongoing
    "Requests & documents" section: supporting documents for a transaction,
    proof of address, a KYC clarification, or feedback on a submitted item.

    Raised by staff (admin), answered by the user (a note and/or a document),
    then resolved by staff. The user is notified on both transitions via the
    durable event bus.
    """

    class Kind(models.TextChoices):
        TRANSACTION_DOCS = 'transaction_docs', 'Transaction supporting documents'
        ADDRESS_PROOF    = 'address_proof',    'Proof of address'
        KYC_SUPPLEMENT   = 'kyc_supplement',   'Additional KYC information'
        CLARIFICATION    = 'clarification',    'Clarification'
        OTHER            = 'other',            'Other'

    class Status(models.TextChoices):
        OPEN      = 'open',      'Awaiting your response'
        SUBMITTED = 'submitted', 'Submitted — under review'
        RESOLVED  = 'resolved',  'Resolved'

    user   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='verification_requests',
    )
    # When set, this request is the customer-facing projection of a
    # verification case (EDD): the response is pinned onto the case as a
    # versioned CaseDocument and the case decides the outcome.
    case = models.ForeignKey(
        'verification.VerificationCase', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='customer_requests',
    )
    kind   = models.CharField(max_length=24, choices=Kind.choices, default=Kind.OTHER)
    title  = models.CharField(max_length=140)
    detail = models.TextField(help_text='What the user is being asked to provide.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    # The user's answer.
    response_note = models.TextField(blank=True, default='')
    document      = models.FileField(upload_to='verification/requests/', blank=True, null=True)

    # Staff feedback shown to the user (e.g. why it was resolved, or what's still needed).
    review_note   = models.TextField(blank=True, default='')

    created_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verification_requests_created',
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status'], name='verifreq_user_status_idx'),
        ]

    def __str__(self):
        return f"VerificationRequest({self.user_id}, {self.kind}, {self.status})"


# ─────────────────────────────────────────────────────────────
# PAYMENT METHODS (scalable payout rails)
# ─────────────────────────────────────────────────────────────

class PaymentMethod(models.Model):
    """A payout/collection method a user has linked. Designed to scale across
    rails: M-Pesa is live today; card and bank are modelled now so the UI and
    storage don't need reshaping when those rails are wired.

    Only one method per user is the default. Card/bank rows carry no PAN/full
    account number — only the display fragments a UI needs (brand + last 4).
    """

    class Kind(models.TextChoices):
        MPESA = 'mpesa', 'M-Pesa'
        CARD  = 'card',  'Debit or credit card'
        BANK  = 'bank',  'Bank account'

    class Status(models.TextChoices):
        ACTIVE      = 'active',      'Active'
        UNAVAILABLE = 'unavailable', 'Coming soon'

    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_methods',
    )
    kind       = models.CharField(max_length=8, choices=Kind.choices)
    label      = models.CharField(max_length=60, blank=True, default='')
    is_default = models.BooleanField(default=False)
    status     = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    # M-Pesa (live)
    mpesa_phone = models.CharField(max_length=15, blank=True, default='')

    # Card (future) — display fragments only, never the PAN.
    card_brand = models.CharField(max_length=20, blank=True, default='')
    card_last4 = models.CharField(max_length=4, blank=True, default='')
    card_exp   = models.CharField(max_length=5, blank=True, default='')  # MM/YY

    # Bank (future) — display fragments only.
    bank_name          = models.CharField(max_length=60, blank=True, default='')
    bank_account_last4 = models.CharField(max_length=4, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        indexes = [models.Index(fields=['user', 'is_default'], name='paymethod_user_default_idx')]

    def __str__(self):
        return f"PaymentMethod({self.user_id}, {self.kind}, default={self.is_default})"

    @property
    def display(self) -> str:
        """Human label for the method, e.g. '•••• 4242' or '0712 ••• 890'."""
        if self.kind == self.Kind.MPESA:
            p = self.mpesa_phone
            return f"{p[:4]} ••• {p[-3:]}" if len(p) >= 7 else p
        if self.kind == self.Kind.CARD:
            return f"{self.card_brand} •••• {self.card_last4}".strip()
        if self.kind == self.Kind.BANK:
            return f"{self.bank_name} •••• {self.bank_account_last4}".strip()
        return self.label
