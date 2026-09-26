"""Closing a customer account and exporting what WEPL holds about them.

Users owns the account, so it runs the workflow; every other context answers
for its own data through ``apps.core.lifecycle`` (boundary audit step 8). This
replaces the 90-line view that checked two things, erased part of the KYC
profile outside any transaction and left no record that it had happened.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.services import AuditService
from apps.core import lifecycle

from .sessions import blacklist_outstanding, revoke_all_for_user

logger = logging.getLogger(__name__)


class AccountCannotClose(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__(reasons[0] if reasons else "Account cannot close.")
        self.reasons = reasons


def closure_blockers(user) -> list[str]:
    reasons: list[str] = []
    for p in lifecycle.participants():
        if p.blockers:
            reasons.extend(p.blockers(user))
    return reasons


def close_account(user, *, request=None) -> None:
    """Close ``user``'s account: refuse if any context objects, else erase every
    context's personal data, anonymise the account and sign it out everywhere,
    all in one transaction, with an audit record. Financial records stay: the
    ledger is retained as the law requires and refers to the user by id only."""
    reasons = closure_blockers(user)
    if reasons:
        raise AccountCannotClose(reasons)

    with transaction.atomic():
        for p in lifecycle.participants():
            if p.erase:
                p.erase(user)
        _erase_account(user)
        AuditService.log(
            "account.closed", actor=None, target=user, request=request,
            metadata={"contexts": [p.name for p in lifecycle.participants() if p.erase]},
        )
    logger.info("Account closed: user %d anonymised.", user.id)


def _erase_account(user) -> None:
    from .models import PrivacyPreferences

    photo = user.profile_photo.name if user.profile_photo else ""
    storage = user.profile_photo.storage if user.profile_photo else None

    PrivacyPreferences.objects.filter(user=user).delete()
    revoke_all_for_user(user)
    blacklist_outstanding(user)

    user.phone_number      = f'+0000{user.id:08d}'
    user.name              = '[deleted]'
    user.bio               = ''
    user.pin               = ''
    user.is_pin_set        = False
    user.is_active         = False
    user.is_phone_verified = False
    user.profile_photo     = None
    user.save()

    if photo:
        transaction.on_commit(lambda: _delete_quietly(storage, photo))


def _delete_quietly(storage, name) -> None:
    try:
        storage.delete(name)
    except Exception:
        logger.warning("Could not delete stored file %s", name)


def export_account(user) -> dict:
    """Everything WEPL holds about ``user``, one section per context."""
    out = {"exported_at": timezone.now().isoformat(), "account": _account_section(user),
           "privacy_preferences": _privacy_section(user)}
    for p in lifecycle.participants():
        if p.export:
            out.update(p.export(user))
    return out


def _account_section(u) -> dict:
    return {
        "phone_number": u.phone_number,
        "name": getattr(u, "name", ""),
        "bio": getattr(u, "bio", ""),
        "is_phone_verified": u.is_phone_verified,
        "date_joined": u.date_joined.isoformat() if getattr(u, "date_joined", None) else None,
    }


def _privacy_section(u):
    from .models import PrivacyPreferences
    p = PrivacyPreferences.objects.filter(user=u).first()
    if p is None:
        return None
    return {f: getattr(p, f) for f in (
        "phone_visibility", "photo_visibility", "contribution_visibility",
        "discoverable", "show_online_status")}
