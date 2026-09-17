from ._common import *  # shared imports/helpers (ADR-0013 view split)


class FinancialSummaryView(APIView):
    """
    GET /api/users/financial-summary/

    Aggregated financial snapshot for the profile dashboard.
    Returned fields:
      total_contributed    — sum of all CONTRIBUTION transactions by this user
      total_received       — sum of all WITHDRAWAL transactions to this user
      active_contributions — count of active participations
      total_contributions  — count of all participations (ever)
      pending_advances     — count of advances in PENDING/APPROVED/DISBURSED state
      advance_balance_due  — total outstanding advance repayment balance
      this_month           — contributions made in the current calendar month
      last_month           — contributions made in the previous calendar month
      monthly_trend        — list of {month, amount} for last 6 months
      member_since         — ISO8601 date_joined
      kyc_status           — 'approved' | 'pending' | 'rejected' | 'not_submitted'
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        from django.db.models import Sum, Count, Q
        from django.db.models.functions import TruncMonth
        from django.utils import timezone
        from datetime import timedelta

        from apps.contributions.models import (
            ContributionParticipant, EmergencyAdvance,
        )
        from apps.contributions.history import member_contribution_credits, member_summary

        user = request.user
        now  = timezone.now()

        # ── Contribution sums (ledger-derived — ADR-0002/0027) ────────────────
        summary = member_summary(user)
        total_contributed = float(summary['total_contributed'])
        total_received    = float(summary['total_received'])
        tx_count          = summary['tx_count']

        # ── Participation counts ──────────────────────────────────────────────
        participation = ContributionParticipant.objects.filter(user=user).aggregate(
            active_count=Count('id', filter=Q(is_active=True)),
            total_count=Count('id'),
        )
        active_contributions = participation['active_count'] or 0
        total_contributions  = participation['total_count']  or 0

        # ── Advances ─────────────────────────────────────────────────────────
        # balance_due is a @property (amount * (1 + rate/100) − repaid), not a
        # DB column — fetch the rows and sum in Python (dataset is always small).
        from decimal import Decimal as D
        active_advances = list(EmergencyAdvance.objects.filter(
            borrower=user,
            status__in=['PENDING', 'APPROVED', 'DISBURSED'],
        ).only('amount', 'interest_rate', 'amount_repaid'))
        pending_advances = len(active_advances)
        advance_balance  = float(sum(
            a.amount * (D('1') + a.interest_rate / D('100')) - a.amount_repaid
            for a in active_advances
        ))

        # ── Monthly contributions ─────────────────────────────────────────────
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_start = (month_start - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Contribution "money in" = CREDITs to the member's contribution
        # sub-ledgers (ledger-derived), windowed by line date.
        credits = member_contribution_credits(user)
        this_month = float(
            credits.filter(created_at__gte=month_start).aggregate(s=Sum('amount'))['s'] or 0)
        last_month = float(
            credits.filter(created_at__gte=prev_month_start, created_at__lt=month_start)
            .aggregate(s=Sum('amount'))['s'] or 0)

        # ── 6-month trend ─────────────────────────────────────────────────────
        six_months_ago = month_start - timedelta(days=180)
        trend_qs = (
            credits
            .filter(created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(amount=Sum('amount'))
            .order_by('month')
        )
        monthly_trend = [
            {
                'month':  entry['month'].strftime('%b %Y'),
                'amount': float(entry['amount'] or 0),
            }
            for entry in trend_qs
        ]

        # ── KYC status ───────────────────────────────────────────────────────
        try:
            kyc_status = user.kyc.status
        except Exception:
            kyc_status = 'not_submitted'

        return Response({
            'total_contributed':    total_contributed,
            'total_received':       total_received,
            'active_contributions': active_contributions,
            'total_contributions':  total_contributions,
            'pending_advances':     pending_advances,
            'advance_balance_due':  advance_balance,
            'this_month':           this_month,
            'last_month':           last_month,
            'monthly_trend':        monthly_trend,
            'tx_count':             tx_count,
            'member_since':         user.date_joined.date().isoformat(),
            'kyc_status':           kyc_status,
        })


# ─── Privacy Preferences ──────────────────────────────────────────────────────
