import base64
import logging
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


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
    def query_stk_status(checkout_request_id: str) -> dict:
        """Query an STK push's status (Daraja stkpushquery). Returns raw response."""
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
            "CheckoutRequestID": checkout_request_id,
        }
        resp = requests.post(
            f"{settings.MPESA_BASE_URL}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def reconcile_c2b(transaction) -> bool:
        """Thin rail adapter (Move 2b): hand the C2B deposit's normalised fields to
        the contributions resolver and stamp the outcome onto the rail record.

        The business logic — resolve the fund from the WEPL-<id> reference, match
        the member, gate community membership, auto-join, and credit — lives in
        ``ContributionService.credit_paybill_payin``. This app only owns the C2B
        model. Returns True when the payment was reconciled."""
        from apps.contributions.services import ContributionService

        result = ContributionService.credit_paybill_payin(
            reference=transaction.bill_ref_number,
            phone=transaction.phone_number,
            amount=transaction.amount,
            receipt=transaction.mpesa_receipt,
            payer_name=transaction.payer_name,
        )
        # Stamp the rail record when the deposit resolved to a member+fund (both
        # the reconciled path and the recorded-but-not-a-member review case).
        if result.get("contribution_id") and result.get("user_id"):
            transaction.contribution_id = result["contribution_id"]
            transaction.user_id = result["user_id"]
            transaction.is_reconciled = result["reconciled"]
            transaction.save(update_fields=["contribution", "user", "is_reconciled"])
        return result["reconciled"]
