"""
Read-only financial reporting API (Phase 4).

Staff-gated (IsAdminUser): trial balance, balance sheet, income statement,
statement of account, and an immutable audit export. Every figure is computed
from immutable journal lines and is point-in-time reproducible via ?as_of=.
Community-admin-scoped self-serve is a planned enhancement (the reporting
functions already accept fund_type/fund_id filters).
"""
from datetime import datetime
from decimal import Decimal

from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import reporting
from .models import Account


def _jsonify(obj):
    """Recursively make a report JSON-safe (Decimal→str, datetime→isoformat)."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def _dt(request, key):
    raw = request.query_params.get(key)
    return parse_datetime(raw) if raw else None


def _dimensions(request):
    fund_id = request.query_params.get('fund_id')
    tenant_id = request.query_params.get('tenant_id')
    return {
        'fund_type': request.query_params.get('fund_type'),
        'fund_id': int(fund_id) if fund_id else None,
        'op_type': request.query_params.get('op_type'),
        'tenant_id': int(tenant_id) if tenant_id else None,
    }


class TrialBalanceView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_jsonify(reporting.trial_balance(as_of=_dt(request, 'as_of'), **_dimensions(request))))


class TrialBalanceByCurrencyView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(_jsonify(reporting.trial_balance_by_currency(
            as_of=_dt(request, 'as_of'), **_dimensions(request))))


class BalanceSheetView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        dims = _dimensions(request)
        return Response(_jsonify(reporting.balance_sheet(
            as_of=_dt(request, 'as_of'), fund_type=dims['fund_type'],
            fund_id=dims['fund_id'], tenant_id=dims['tenant_id'])))


class IncomeStatementView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        dims = _dimensions(request)
        return Response(_jsonify(reporting.income_statement(
            start=_dt(request, 'start'), end=_dt(request, 'end'),
            fund_type=dims['fund_type'], fund_id=dims['fund_id'], tenant_id=dims['tenant_id'])))


class StatementOfAccountView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        code = request.query_params.get('account')
        if code:
            account = Account.objects.filter(code=code).first()
        else:
            fund_type = request.query_params.get('fund_type')
            fund_id = request.query_params.get('fund_id')
            user_id = request.query_params.get('user_id')
            account = Account.objects.filter(
                owner_id=user_id, fund_type=fund_type, fund_id=fund_id,
            ).first() if (fund_type and fund_id and user_id) else None
        if account is None:
            return Response({'error': 'Account not found. Pass ?account=<code> or ?fund_type=&fund_id=&user_id=.'}, status=404)
        return Response(_jsonify(reporting.statement_of_account(
            account, start=_dt(request, 'start'), end=_dt(request, 'end'))))


class AuditExportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        rows = list(reporting.export_journal_rows(start=_dt(request, 'start'), end=_dt(request, 'end')))
        return Response({'columns': list(reporting.EXPORT_COLUMNS), 'count': len(rows), 'rows': rows})


class TenancyCheckView(APIView):
    """Is multi-tenant RLS actually enforcing in this deployment? (P6 ops check)

    Reports the DB role's superuser/bypass flags and whether RLS is enabled +
    forced on the financial tables. RLS only isolates tenant-pinned sessions when
    the role is NOT a superuser/bypassrls AND the tables are forced.
    """
    permission_classes = [IsAdminUser]

    RLS_TABLES = ('ledger_account', 'ledger_financialtransaction')

    def get(self, request):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            db_user, rolsuper, rolbypassrls = cur.fetchone()
            cur.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE relname = ANY(%s)", [list(self.RLS_TABLES)],
            )
            tables = {r[0]: {'rls_enabled': r[1], 'rls_forced': r[2]} for r in cur.fetchall()}

        all_forced = all(tables.get(t, {}).get('rls_enabled') and tables.get(t, {}).get('rls_forced')
                         for t in self.RLS_TABLES)
        enforcing = (not rolsuper) and (not rolbypassrls) and all_forced
        return Response({
            'db_user': db_user,
            'is_superuser': rolsuper,
            'bypass_rls': rolbypassrls,
            'tables': tables,
            'rls_enforcing': enforcing,
            'note': (
                'RLS is enforcing: tenant-pinned sessions are isolated at the database.'
                if enforcing else
                'RLS is DORMANT — the DB role is a superuser/bypassrls or the tables are '
                'not forced. Deploy with a non-superuser DB role for isolation to take effect.'
            ),
        })
