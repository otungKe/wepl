from ._common import *  # shared imports/helpers (ADR-0013 view split)


class KYCView(APIView):
    """
    GET  /api/users/kyc/ — return the user's KYC profile and status.
                           Returns {"status": "not_submitted"} if none exists yet.
                           Also returns county list and choice labels for the mobile form.

    POST /api/users/kyc/ — submit (or re-submit after rejection) KYC.
                           Accepts multipart/form-data so ID scan images can be uploaded.
                           Approved profiles cannot be re-submitted.
    """
    permission_classes = [IsActiveSession]
    parser_classes_override = None  # multipart handled automatically by DRF

    def get(self, request):
        try:
            kyc = request.user.kyc
            return Response(KYCStatusSerializer(kyc, context={'request': request}).data)
        except KYCProfile.DoesNotExist:
            return Response({
                'status': 'not_submitted',
                'counties':       [c[0] for c in KYCProfile.KENYA_COUNTIES],
                'income_bands':   [{'value': v, 'label': l} for v, l in KYCProfile.INCOME_BAND_CHOICES],
                'income_sources': [{'value': v, 'label': l} for v, l in KYCProfile.SOURCE_CHOICES],
            })

    def post(self, request):
        try:
            kyc = request.user.kyc
            if kyc.status == 'approved':
                return Response(
                    {'error': 'Your KYC has already been approved and cannot be re-submitted.'},
                    status=status.HTTP_409_CONFLICT,
                )
            # Re-submission after rejection — reset to pending
            serializer = KYCSubmitSerializer(kyc, data=request.data, partial=False)
        except KYCProfile.DoesNotExist:
            serializer = KYCSubmitSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        kyc = serializer.save(
            user=request.user,
            status='pending',
            rejection_reason='',
            email_verified=False,       # reset on re-submission
        )

        # Record the submission on the verification case ledger: opens the case
        # on first submission, snapshots the uploaded documents as immutable
        # versions, and appends the timeline event (apps.verification).
        from apps.verification import service as case_service
        try:
            kind = 'full_resubmit' if kyc.cases.exists() else 'initial'
            case_service.record_submission(kyc, kind=kind)
        except Exception:
            logger.exception("Case ledger recording failed for KYC submit (user %s)", kyc.user_id)

        # NOTE: User.name (display name) is intentionally NOT synced from KYC.
        # The display name is what the user wants to appear to their community —
        # they set it themselves during onboarding and can change it any time.
        # KYC given_names + surname are the legal identity fields used only for
        # verification; they are never exposed as the profile display name.

        # Send email verification link
        _send_kyc_verification_email(kyc, request)

        return Response(
            KYCStatusSerializer(kyc, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


def _send_kyc_verification_email(kyc, request):
    """Generate a verification token and queue the email for out-of-band delivery.

    The SMTP send runs in a Celery task (apps.users.tasks) so the request returns
    immediately — sending inline previously blocked the ASGI worker until Daphne
    killed it whenever SMTP was slow.
    """
    import secrets
    from django.utils import timezone
    from ..tasks import send_kyc_verification_email

    token = secrets.token_urlsafe(32)
    kyc.email_verification_token   = token
    kyc.email_verification_sent_at = timezone.now()
    kyc.email_verified             = False
    kyc.save(update_fields=['email_verification_token', 'email_verification_sent_at', 'email_verified'])

    # Build verification URL — works for both dev (console email) and production
    verify_url = request.build_absolute_uri(f"/api/users/kyc/verify-email/?token={token}")

    # Best-effort: a broker outage must not 500 the KYC request — the token is
    # persisted, so the member can re-request the email once the broker recovers.
    from apps.core.dispatch import safe_enqueue
    safe_enqueue(
        send_kyc_verification_email,
        email=kyc.email,
        given_names=kyc.given_names,
        verify_url=verify_url,
        user_id=kyc.user_id,
    )


def _run_identity_check(kyc):
    """Hand the submission to verification, which owns the identity check."""
    from apps.verification.checks import run_identity_check
    run_identity_check(kyc)


class KYCResubmitView(APIView):
    """POST /api/users/kyc/resubmit/ — targeted top-up of ONLY the items a
    reviewer asked for (``kyc.resubmission_requested``), so the user does not
    re-enter the whole KYC form. Accepts multipart/form-data for re-requested
    photos. Anything the client sends that wasn't requested is ignored."""
    permission_classes = [IsActiveSession]

    def post(self, request):
        try:
            kyc = request.user.kyc
        except KYCProfile.DoesNotExist:
            return Response({'error': 'No KYC submission found.'},
                            status=status.HTTP_404_NOT_FOUND)

        # Approved KYC is closed to re-submission — nothing can be topped up,
        # and reviewers can no longer request items on an approved case.
        if kyc.status == 'approved':
            return Response({'error': 'Your KYC is approved — no re-submission is needed.'},
                            status=status.HTTP_409_CONFLICT)

        requested = list(kyc.resubmission_requested or [])
        if not requested:
            return Response({'error': 'No re-submission has been requested.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Only accept the requested fields — a top-up can never change items that
        # weren't asked for.
        data = {k: v for k, v in request.data.items() if k in requested}
        missing = [
            k for k in requested
            if k not in data or (isinstance(data.get(k), str) and not data[k].strip())
        ]
        if missing:
            labels = dict(KYCProfile.RESUBMITTABLE_ITEMS)
            return Response(
                {'error': 'Please provide all requested items.',
                 'missing': [labels.get(m, m) for m in missing]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = KYCSubmitSerializer(kyc, data=data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        kyc = serializer.save(status='pending', resubmission_requested=[])

        # Record the top-up on the case ledger: snapshots any new document
        # versions (the prior versions are never overwritten) and moves the
        # case back to SUBMITTED for review.
        from apps.verification import service as case_service
        try:
            case_service.record_submission(kyc, kind='targeted_resubmit', items=requested)
        except Exception:
            logger.exception("Case ledger recording failed for KYC resubmit (user %s)", kyc.user_id)

        # Re-check the (possibly new) documents and hand back to the reviewer.
        # Email verification is untouched — this is not a fresh submission.
        _run_identity_check(kyc)

        return Response(
            KYCStatusSerializer(kyc, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class KYCCheckEmailView(APIView):
    """
    GET /api/users/kyc/check-email/?email=<value>

    Soft check: is this email already used by another KYC profile?
    Returns a warning (not an error) — email is a communication channel,
    not a legally unique identifier like a national ID.

    The caller should warn the user but allow them to proceed if they
    confirm the email is theirs.
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        email = request.query_params.get('email', '').strip().lower()
        if not email or '@' not in email:
            return Response({'available': True})

        taken = KYCProfile.objects.filter(
            email__iexact=email
        ).exclude(user=request.user).exists()

        if taken:
            return Response({
                'available': False,
                'warning': True,   # soft — warn, don't block
                'message': (
                    'This email is already linked to another account. '
                    'If it\'s yours, you can continue — '
                    'otherwise use a different address.'
                ),
            })
        return Response({'available': True})


class KYCEmailVerifyView(APIView):
    """
    GET /api/users/kyc/verify-email/?token=<token>

    Called when the user clicks the verification link in their email.
    No authentication required — the token IS the credential.
    Returns a simple HTML page so any browser (or email client preview) works.
    """
    permission_classes = []   # public — token is the auth

    def get(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from datetime import timedelta

        token = request.query_params.get('token', '').strip()
        if not token:
            return HttpResponse(self._page("Invalid link", "The verification link is missing a token.", success=False))

        try:
            kyc = KYCProfile.objects.get(email_verification_token=token)
        except KYCProfile.DoesNotExist:
            return HttpResponse(self._page("Link not found", "This verification link is invalid or has already been used.", success=False))

        # Check expiry (48 hours)
        if kyc.email_verification_sent_at:
            expiry = kyc.email_verification_sent_at + timedelta(hours=48)
            if timezone.now() > expiry:
                return HttpResponse(self._page("Link expired", "This link has expired. Please re-submit your KYC to receive a new one.", success=False))

        already_verified = kyc.email_verified

        if not already_verified:
            kyc.email_verified            = True
            kyc.email_verification_token  = ''   # single-use — invalidate now
            kyc.save(update_fields=['email_verified', 'email_verification_token'])
            logger.info("KYC email verified for user %s (%s)", kyc.user_id, kyc.email)

            from apps.verification import service as case_service
            try:
                case_service.record_email_verified(kyc)
            except Exception:
                logger.exception("Case ledger recording failed for email verify (user %s)", kyc.user_id)

            # ── Identity verification (apps.verification.identity port) ───
            # The active provider decides the outcome. Today: ManualProvider in
            # production (human review) and FakeProvider under DEBUG (auto-verify)
            # — historical behaviour preserved. A real vendor or an IPRS lookup
            # drops in as another adapter with no change here.
            _run_identity_check(kyc)

        # The email verification page ONLY confirms the email address.
        # Identity verification is a separate step — the outcome is
        # communicated via an in-app notification, not here.
        page_message = (
            f"Your email address ({kyc.email}) has been confirmed. "
            "We're now processing your identity verification in the background. "
            "Open the WEPL app — you'll receive a notification as soon as it's complete."
        )

        return HttpResponse(self._page("Email confirmed!", page_message, success=True))

    @staticmethod
    def _page(title: str, message: str, success: bool) -> str:
        colour = "#1A5C38" if success else "#C0392B"
        icon   = "✓" if success else "✗"
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — WEPL</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #F5F8F6; }}
    .card {{ background: #fff; border-radius: 16px; padding: 40px 32px;
             max-width: 420px; width: 90%; text-align: center;
             box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
    .icon {{ font-size: 56px; color: {colour}; margin-bottom: 16px; }}
    h1 {{ color: #111; font-size: 22px; margin: 0 0 12px; }}
    p  {{ color: #4D6358; line-height: 1.6; margin: 0 0 24px; }}
    .btn {{ display: inline-block; background: {colour}; color: #fff;
            padding: 12px 28px; border-radius: 8px; text-decoration: none;
            font-weight: 700; font-size: 15px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <a class="btn" href="weplmobile://">Open WEPL</a>
  </div>
</body>
</html>"""


class KYCCheckIDView(APIView):
    """
    GET /api/users/kyc/check-id/?id_number=<value>

    Real-time check: is this national ID number already registered?

    Returns:
      { "available": true }   — ID is free to use
      { "available": false, "message": "..." }  — already taken

    The current user's own KYC row is excluded so re-submission after
    rejection doesn't falsely flag their own ID as taken.
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        id_number = request.query_params.get('id_number', '').strip()
        if not id_number or len(id_number) < 4:
            return Response({'available': True})

        taken = KYCProfile.objects.filter(
            id_number=id_number
        ).exclude(user=request.user).exists()

        if taken:
            return Response({
                'available': False,
                'message':   'This ID number is already registered to another account.',
            })
        return Response({'available': True})


class KYCResendEmailView(APIView):
    """POST /api/users/kyc/resend-verification/ — resend the verification email."""
    permission_classes = [IsActiveSession]

    def post(self, request):
        from django.utils import timezone
        from datetime import timedelta

        try:
            kyc = request.user.kyc
        except KYCProfile.DoesNotExist:
            return Response({'error': 'No KYC submission found.'}, status=status.HTTP_404_NOT_FOUND)

        if kyc.email_verified:
            return Response({'message': 'Email already verified.'})

        if not kyc.email:
            return Response({'error': 'No email address on file.'}, status=status.HTTP_400_BAD_REQUEST)

        # Rate-limit resend: once per 2 minutes
        if kyc.email_verification_sent_at:
            cooldown = kyc.email_verification_sent_at + timedelta(minutes=2)
            if timezone.now() < cooldown:
                wait = int((cooldown - timezone.now()).total_seconds())
                return Response(
                    {'error': f'Please wait {wait}s before requesting another email.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        _send_kyc_verification_email(kyc, request)
        return Response({'message': f'Verification email sent to {kyc.email}.'})


# -----------------------------
# 8. FINANCIAL SUMMARY
# -----------------------------
