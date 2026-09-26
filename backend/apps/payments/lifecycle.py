"""Payments' part in closing an account and exporting its data
(``apps.core.lifecycle``, boundary audit step 8). Saved payment methods carry a
phone number, so they go when the account closes; payment records stay with the
ledger."""
from apps.core import lifecycle

from .models import PaymentMethod


def erase(user) -> None:
    PaymentMethod.objects.filter(user=user).delete()


def export(user) -> dict:
    return {"payment_methods": [
        {"kind": pm.kind, "display": pm.display, "is_default": pm.is_default}
        for pm in PaymentMethod.objects.filter(user=user)
    ]}


def register() -> None:
    lifecycle.register("payments", erase=erase, export=export)
