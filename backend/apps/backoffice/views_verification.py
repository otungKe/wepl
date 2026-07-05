"""
Verification Centre API (/api/ops/verification/) — the first real console
workspace. Turns the KYC review flow into an operator queue + case + decision,
reusing the domain logic already proven in the Django admin (notifications,
resubmission, OCR cross-check) but attributed to a StaffAccount and audited.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http
from rest_framework.response import Response

from apps.users.models import KYCProfile

from .audit import record_action
from .permissions import RequireCapability
from .views import OpsAPIView

# Statuses that constitute "work" in the queue, oldest first (SLA order).
_OPEN_STATUSES = ("pending",)


def _age_hours(dt):
    if not dt:
        return None
    return round((timezone.now() - dt).total_seconds() / 3600, 1)


def _ocr(kyc):
    return (kyc.verification_detail or {}).get("ocr") or {}


def _doc(file):
    """Return a document reference the console can render, degrading legibly when
    the object isn't in storage (e.g. object storage not enabled)."""
    if not file:
        return {"available": False, "url": None, "name": None}
    try:
        if not file.storage.exists(file.name):
            return {"available": False, "url": None, "name": file.name}
    except Exception:
        pass
    try:
        return {"available": True, "url": file.url, "name": file.name}
    except Exception:
        return {"available": False, "url": None, "name": file.name}


def _queue_row(kyc):
    ocr = _ocr(kyc)
    return {
        "user_id": kyc.user_id,
        "name": kyc.full_name or kyc.user.phone_number,
        "phone_number": kyc.user.phone_number,
        "id_number": kyc.id_number,
        "status": kyc.status,
        "email_verified": kyc.email_verified,
        "submitted_at": kyc.submitted_at.isoformat() if kyc.submitted_at else None,
        "age_hours": _age_hours(kyc.submitted_at),
        "ocr_mismatch": bool(ocr.get("mismatch")),
        "ocr_detected": ocr.get("detected"),
        "resubmission_pending": bool(kyc.resubmission_requested),
    }


def _case(kyc, request):
    from apps.audit.models import AuditEvent
    history = [
        {"action": e.action, "by": e.actor_label or "system",
         "at": e.created_at.isoformat(), "detail": e.metadata}
        for e in AuditEvent.objects.filter(
            target_type="KYCProfile", target_id=str(kyc.id)).order_by("-created_at")[:20]
    ]
    return {
        "user_id": kyc.user_id,
        "phone_number": kyc.user.phone_number,
        "status": kyc.status,
        "applicant": {
            "given_names": kyc.given_names, "surname": kyc.surname,
            "id_number": kyc.id_number, "kra_pin": kyc.kra_pin,
            "date_of_birth": kyc.date_of_birth.isoformat() if kyc.date_of_birth else None,
            "email": kyc.email, "email_verified": kyc.email_verified,
            "county": kyc.county, "physical_address": kyc.physical_address,
            "occupation": kyc.occupation, "source_of_income": kyc.source_of_income,
            "expected_monthly_income": kyc.expected_monthly_income,
        },
        "documents": {
            "id_front": _doc(kyc.id_front),
            "id_back": _doc(kyc.id_back),
            "selfie": _doc(kyc.selfie),
        },
        "checks": {
            "provider": kyc.verification_provider,
            "state": kyc.verification_state,
            "checked_at": kyc.verification_checked_at.isoformat() if kyc.verification_checked_at else None,
            "ocr": _ocr(kyc),
        },
        "rejection_reason": kyc.rejection_reason,
        "resubmission_requested": kyc.resubmission_requested or [],
        "resubmittable_items": dict(KYCProfile.RESUBMITTABLE_ITEMS),
        "submitted_at": kyc.submitted_at.isoformat() if kyc.submitted_at else None,
        "age_hours": _age_hours(kyc.submitted_at),
        "history": history,
    }


class VerificationQueueView(OpsAPIView):
    permission_classes = [RequireCapability("verification.view")]

    def get(self, request):
        status_filter = request.query_params.get("status", "pending")
        qs = KYCProfile.objects.select_related("user")
        if status_filter == "open":
            qs = qs.filter(status__in=_OPEN_STATUSES)
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)
        qs = qs.order_by("submitted_at")[:200]   # oldest first (SLA)
        rows = [_queue_row(k) for k in qs]
        return Response({"results": rows, "count": len(rows)})


class VerificationCaseView(OpsAPIView):
    permission_classes = [RequireCapability("verification.view")]

    def get(self, request, user_id):
        kyc = get_object_or_404(KYCProfile.objects.select_related("user"), user_id=user_id)
        return Response(_case(kyc, request))


class VerificationDecisionView(OpsAPIView):
    """POST … {action: approve|reject|request_resubmission, reason?, items?}.
    Reuses the KYC domain logic; attributed to the operator and audited."""
    permission_classes = [RequireCapability("verification.decide")]

    def post(self, request, user_id):
        from apps.users.admin import _notify_kyc_decision, _notify_resubmission_request

        kyc = get_object_or_404(KYCProfile.objects.select_related("user"), user_id=user_id)
        action = (request.data.get("action") or "").strip()
        operator = request.user.email
        now = timezone.now()

        def _stamp(state):
            kyc.verification_provider = f"ops:{operator}"
            kyc.verification_state = state
            kyc.verification_checked_at = now
            kyc.reviewed_at = now

        if action == "approve":
            kyc.status = "approved"
            kyc.rejection_reason = ""
            _stamp("verified")
            kyc.save(update_fields=["status", "rejection_reason", "reviewed_at",
                                    "verification_provider", "verification_state", "verification_checked_at"])
            _notify_kyc_decision(kyc)

        elif action == "reject":
            reason = (request.data.get("reason") or "").strip()
            if not reason:
                return Response({"detail": "A rejection reason is required."}, status=http.HTTP_400_BAD_REQUEST)
            kyc.status = "rejected"
            kyc.rejection_reason = reason
            _stamp("rejected")
            kyc.save(update_fields=["status", "rejection_reason", "reviewed_at",
                                    "verification_provider", "verification_state", "verification_checked_at"])
            _notify_kyc_decision(kyc)

        elif action == "request_resubmission":
            items = request.data.get("items") or ["id_front", "id_back", "selfie"]
            items = [i for i in items if i in KYCProfile.RESUBMITTABLE_KEYS]
            if not items:
                return Response({"detail": "Select at least one valid item."}, status=http.HTTP_400_BAD_REQUEST)
            kyc.resubmission_requested = items
            kyc.save(update_fields=["resubmission_requested"])
            _notify_resubmission_request(kyc)

        else:
            return Response({"detail": f"Unknown action: {action!r}."}, status=http.HTTP_400_BAD_REQUEST)

        record_action(
            action=f"ops.verification.{action}", actor=request.user, request=request,
            target_type="KYCProfile", target_id=kyc.id,
            metadata={"result": kyc.status, "reason": request.data.get("reason", ""),
                      "items": kyc.resubmission_requested},
        )
        return Response(_case(kyc, request))
