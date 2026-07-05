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
    case = next(iter(kyc.cases.all()), None)   # prefetched; newest first
    return {
        "assignee": case.assigned_to.email if case and case.assigned_to else None,
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


def _doc_versions(case):
    """All immutable document versions on the case, newest first per type."""
    from apps.verification.models import CaseDocument
    out = {}
    for d in CaseDocument.objects.filter(case=case).order_by("doc_type", "-version"):
        try:
            url = d.file.url if d.file.storage.exists(d.file.name) else None
        except Exception:
            url = None
        out.setdefault(d.doc_type, []).append({
            "version": d.version, "url": url, "name": d.file.name,
            "source": d.source, "sha256": d.sha256,
            "at": d.created_at.isoformat(),
        })
    return out


def _case(kyc, request):
    from apps.verification import service as case_service
    from apps.verification.models import CaseEvent, RejectionReason

    case = case_service.case_for(kyc)
    timeline = [
        {"seq": e.seq, "type": e.event_type, "actor": e.actor_label or "system",
         "actor_kind": e.actor_kind, "at": e.created_at.isoformat(),
         "payload": e.payload}
        for e in CaseEvent.objects.filter(case=case).order_by("-seq")[:50]
    ]
    versions = _doc_versions(case)
    notes = [
        {"id": n.pk, "author": n.author_label, "body": n.body,
         "at": n.created_at.isoformat()}
        for n in case.notes.select_related("author_staff")[:50]
    ]
    rejection_reasons = [
        {"code": r.code, "label": r.label, "customer_message": r.customer_message}
        for r in RejectionReason.objects.filter(active=True)
    ]
    return {
        "case_id": str(case.id),
        "case_state": case.state,
        "assignee": case.assigned_to.email if case.assigned_to else None,
        "notes": notes,
        "rejection_reasons": rejection_reasons,
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
            "id_front": {**_doc(kyc.id_front), "versions": versions.get("id_front", [])},
            "id_back": {**_doc(kyc.id_back), "versions": versions.get("id_back", [])},
            "selfie": {**_doc(kyc.selfie), "versions": versions.get("selfie", [])},
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
        "timeline": timeline,
    }


class VerificationQueueView(OpsAPIView):
    permission_classes = [RequireCapability("verification.view")]

    def get(self, request):
        status_filter = request.query_params.get("status", "pending")
        qs = KYCProfile.objects.select_related("user").prefetch_related("cases__assigned_to")
        if status_filter == "open":
            qs = qs.filter(status__in=_OPEN_STATUSES)
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)
        if request.query_params.get("assigned") == "me":
            qs = qs.filter(cases__assigned_to=request.user)
        elif request.query_params.get("assigned") == "nobody":
            qs = qs.filter(cases__assigned_to__isnull=True)
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
        from apps.verification import service as case_service

        kyc = get_object_or_404(KYCProfile.objects.select_related("user"), user_id=user_id)
        action = (request.data.get("action") or "").strip()
        operator = request.user.email

        try:
            if action == "approve":
                case_service.decide(kyc, "approve", actor_label=f"ops:{operator}",
                                    staff=request.user)

            elif action == "reject":
                reason = (request.data.get("reason") or "").strip()
                reason_code = (request.data.get("reason_code") or "").strip()
                if not reason and not reason_code:
                    return Response({"detail": "A rejection reason is required."},
                                    status=http.HTTP_400_BAD_REQUEST)
                try:
                    case_service.decide(kyc, "reject", actor_label=f"ops:{operator}",
                                        staff=request.user, reason=reason,
                                        reason_code=reason_code)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

            elif action == "request_resubmission":
                items = request.data.get("items") or ["id_front", "id_back", "selfie"]
                items = [i for i in items if i in KYCProfile.RESUBMITTABLE_KEYS]
                if not items:
                    return Response({"detail": "Select at least one valid item."},
                                    status=http.HTTP_400_BAD_REQUEST)
                case_service.decide(kyc, "request_info", actor_label=f"ops:{operator}",
                                    staff=request.user, items=items)

            else:
                return Response({"detail": f"Unknown action: {action!r}."}, status=http.HTTP_400_BAD_REQUEST)

        except case_service.IllegalTransition as exc:
            return Response(
                {"detail": f"This case is {exc.state} — {action.replace('_', ' ')} isn't available from that state."},
                status=http.HTTP_409_CONFLICT,
            )

        record_action(
            action=f"ops.verification.{action}", actor=request.user, request=request,
            target_type="KYCProfile", target_id=kyc.id,
            metadata={"result": kyc.status, "reason": request.data.get("reason", ""),
                      "reason_code": request.data.get("reason_code", ""),
                      "items": kyc.resubmission_requested},
        )
        return Response(_case(kyc, request))


class VerificationNoteView(OpsAPIView):
    """POST … {body} — append an internal reviewer note to the case.
    Notes are never customer-visible and cannot be edited or deleted."""
    permission_classes = [RequireCapability("verification.view")]

    def post(self, request, user_id):
        from apps.verification import service as case_service

        kyc = get_object_or_404(KYCProfile.objects.select_related("user"), user_id=user_id)
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "A note body is required."}, status=http.HTTP_400_BAD_REQUEST)
        case_service.add_note(kyc, body=body, staff=request.user)
        record_action(
            action="ops.verification.note", actor=request.user, request=request,
            target_type="KYCProfile", target_id=kyc.id, metadata={},
        )
        return Response(_case(kyc, request), status=http.HTTP_201_CREATED)


class VerificationAssignView(OpsAPIView):
    """POST … {action: claim|release} — take a case into (or return it to) the
    working pool. Assignment is evented on the case timeline."""
    permission_classes = [RequireCapability("verification.decide")]

    def post(self, request, user_id):
        from apps.verification import service as case_service

        kyc = get_object_or_404(KYCProfile.objects.select_related("user"), user_id=user_id)
        action = (request.data.get("action") or "").strip()
        try:
            if action == "claim":
                case_service.claim(kyc, staff=request.user)
            elif action == "release":
                case_service.release(kyc, staff=request.user)
            else:
                return Response({"detail": f"Unknown action: {action!r}."},
                                status=http.HTTP_400_BAD_REQUEST)
        except case_service.IllegalTransition as exc:
            return Response({"detail": f"This case is {exc.state} and can no longer be claimed."},
                            status=http.HTTP_409_CONFLICT)
        record_action(
            action=f"ops.verification.{action}", actor=request.user, request=request,
            target_type="KYCProfile", target_id=kyc.id, metadata={},
        )
        return Response(_case(kyc, request))
