import base64
import logging
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


def _normalize_phone(phone: str) -> str:
    """Convert any Kenyan phone format to 254XXXXXXXXX."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("07") or phone.startswith("01"):
        phone = "254" + phone[1:]
    return phone


class MpesaService:

    @staticmethod
    def _get_access_token() -> str:
        consumer_key = settings.MPESA_CONSUMER_KEY
        consumer_secret = settings.MPESA_CONSUMER_SECRET
        credentials = base64.b64encode(
            f"{consumer_key}:{consumer_secret}".encode()
        ).decode()
        url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
        resp = requests.get(url, headers={"Authorization": f"Basic {credentials}"}, timeout=10)
        resp.raise_for_status()
        return resp.json()["access_token"]

    @staticmethod
    def stk_push(phone_number: str, amount: Decimal, account_ref: str, description: str) -> dict:
        """
        Initiate an STK Push (Lipa Na M-Pesa Online) to the member's phone.
        Returns the raw Daraja API response dict.
        """
        token = MpesaService._get_access_token()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        shortcode = settings.MPESA_SHORTCODE
        passkey = settings.MPESA_PASSKEY
        password = base64.b64encode(
            f"{shortcode}{passkey}{timestamp}".encode()
        ).decode()

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": _normalize_phone(phone_number),
            "PartyB": shortcode,
            "PhoneNumber": _normalize_phone(phone_number),
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": account_ref[:12],
            "TransactionDesc": description[:20],
        }

        resp = requests.post(
            f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def b2c_payment(phone_number: str, amount: Decimal, reference: str, remarks: str) -> dict:
        """
        Send money from the business shortcode to a customer's M-Pesa (B2C).
        Used for welfare fund disbursements.
        Returns the raw Daraja API response dict.
        """
        token = MpesaService._get_access_token()

        payload = {
            "InitiatorName":      settings.MPESA_B2C_INITIATOR_NAME,
            "SecurityCredential": settings.MPESA_B2C_SECURITY_CREDENTIAL,
            "CommandID":          "BusinessPayment",
            "Amount":             int(amount),
            "PartyA":             settings.MPESA_SHORTCODE,
            "PartyB":             _normalize_phone(phone_number),
            "Remarks":            remarks[:100],
            "QueueTimeOutURL":    settings.MPESA_B2C_TIMEOUT_URL,
            "ResultURL":          settings.MPESA_B2C_RESULT_URL,
            "Occasion":           reference[:100],
        }

        resp = requests.post(
            f"{settings.MPESA_BASE_URL}/mpesa/b2c/v3/paymentrequest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def reconcile_c2b(transaction) -> bool:
        """
        Match an inbound C2B payment to a contribution and user, then
        trigger the contribution ledger update.
        Returns True if reconciled successfully.
        """
        from apps.contributions.models import Contribution, ContributionParticipant
        from apps.contributions.services import ContributionService

        # bill_ref_number format: "WEPL-{contribution_id}"
        ref = transaction.bill_ref_number.upper()
        if not ref.startswith("WEPL-"):
            logger.warning("Unknown bill ref: %s", ref)
            return False

        try:
            contribution_id = int(ref.split("-", 1)[1])
        except (IndexError, ValueError):
            return False

        try:
            contribution = Contribution.objects.get(id=contribution_id, is_active=True)
        except Contribution.DoesNotExist:
            return False

        # Match user by phone
        phone = _normalize_phone(transaction.phone_number)
        try:
            user = User.objects.get(phone_number=phone)
        except User.DoesNotExist:
            logger.warning("C2B reconcile: no user for phone %s — receipt %s unmatched",
                           phone, transaction.mpesa_receipt)
            return False

        # ── Community membership gate ──────────────────────────────────────────
        # If this contribution belongs to a community, the payer must be an active
        # member of that community before we add them as a participant.
        # Skipping this check is the same bug as the communities join-bypass: anyone
        # who knows a contribution ID (or guesses "WEPL-42") could pay their way in.
        if contribution.community_id:
            from apps.communities.models import CommunityMembership
            is_community_member = CommunityMembership.objects.filter(
                community_id=contribution.community_id,
                user=user,
                is_active=True,
            ).exists()
            if not is_community_member:
                # Record the payment against the transaction row so the money is
                # not lost, but do NOT auto-join. Flag for admin review.
                transaction.contribution = contribution
                transaction.user = user
                transaction.is_reconciled = False  # intentionally left un-reconciled
                transaction.save(update_fields=["contribution", "user", "is_reconciled"])
                logger.warning(
                    "C2B reconcile: user %s (phone %s) paid into community contribution %s "
                    "but is NOT a community member — payment recorded, NOT auto-joined. "
                    "Receipt: %s. Admin review required.",
                    user.id, phone, contribution.id, transaction.mpesa_receipt,
                )
                return False

        # Auto-join as participant if not already one (open / already-member path).
        ContributionParticipant.objects.get_or_create(
            contribution=contribution, user=user, defaults={"is_active": True}
        )

        ContributionService.contribute(
            user, contribution.id, transaction.amount,
            mpesa_receipt=transaction.mpesa_receipt,
        )

        transaction.contribution = contribution
        transaction.user = user
        transaction.is_reconciled = True
        transaction.save(update_fields=["contribution", "user", "is_reconciled"])
        logger.info(
            "C2B reconcile: receipt %s → user %s, contribution %s, amount %s",
            transaction.mpesa_receipt, user.id, contribution.id, transaction.amount,
        )
        return True
