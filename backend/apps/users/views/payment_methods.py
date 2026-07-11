import re

from django.db import transaction

from ._common import *  # shared imports/helpers (ADR-0013)
from ..models import PaymentMethod
from ..phone import normalize_phone
from ..serializers import PaymentMethodSerializer

# Canonical Kenyan MSISDN after normalisation.
_KE_MSISDN = re.compile(r"^254(7|1)\d{8}$")


class PaymentMethodListCreateView(APIView):
    """GET  /api/users/payment-methods/  — the user's linked methods.
    POST /api/users/payment-methods/  — link a method.

    M-Pesa is live. Card and bank are modelled and have UI, but linking them is
    not enabled yet — those requests return 501 so the client shows "coming
    soon" without any fabricated card/bank data being stored."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        qs = PaymentMethod.objects.filter(user=request.user)
        return Response(PaymentMethodSerializer(qs, many=True).data)

    @transaction.atomic
    def post(self, request):
        kind = (request.data.get('kind') or '').lower()

        if kind == PaymentMethod.Kind.MPESA:
            phone = normalize_phone(request.data.get('mpesa_phone') or '')
            if not _KE_MSISDN.match(phone):
                return Response(
                    {"error": "Enter a valid M-Pesa number, e.g. 0712345678."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if PaymentMethod.objects.filter(
                user=request.user, kind=PaymentMethod.Kind.MPESA, mpesa_phone=phone
            ).exists():
                return Response({"error": "That M-Pesa number is already linked."},
                                status=status.HTTP_400_BAD_REQUEST)

            make_default = bool(request.data.get('is_default')) or \
                not PaymentMethod.objects.filter(user=request.user).exists()
            if make_default:
                PaymentMethod.objects.filter(user=request.user, is_default=True).update(is_default=False)

            method = PaymentMethod.objects.create(
                user=request.user, kind=PaymentMethod.Kind.MPESA,
                mpesa_phone=phone, label=(request.data.get('label') or '').strip(),
                is_default=make_default,
            )
            return Response(PaymentMethodSerializer(method).data, status=status.HTTP_201_CREATED)

        if kind in (PaymentMethod.Kind.CARD, PaymentMethod.Kind.BANK):
            label = "Card payments" if kind == PaymentMethod.Kind.CARD else "Bank transfers"
            return Response(
                {"error": f"{label} are coming soon.", "code": "RAIL_UNAVAILABLE"},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        return Response({"error": "Unknown payment method type."},
                        status=status.HTTP_400_BAD_REQUEST)


class PaymentMethodDetailView(APIView):
    """DELETE .../<id>/         — unlink a method.
    POST   .../<id>/default/  — make it the default."""
    permission_classes = [IsActiveSession]

    def _get(self, request, pk):
        return PaymentMethod.objects.filter(pk=pk, user=request.user).first()

    def delete(self, request, pk):
        method = self._get(request, pk)
        if not method:
            return Response({"error": "Method not found."}, status=status.HTTP_404_NOT_FOUND)
        was_default = method.is_default
        method.delete()
        # Promote another method to default so the user always has one.
        if was_default:
            nxt = PaymentMethod.objects.filter(user=request.user).order_by('-created_at').first()
            if nxt:
                nxt.is_default = True
                nxt.save(update_fields=['is_default'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def post(self, request, pk):
        method = self._get(request, pk)
        if not method:
            return Response({"error": "Method not found."}, status=status.HTTP_404_NOT_FOUND)
        PaymentMethod.objects.filter(user=request.user, is_default=True).update(is_default=False)
        method.is_default = True
        method.save(update_fields=['is_default'])
        return Response(PaymentMethodSerializer(method).data)
