"""
Chart of Accounts (COA).

Defines the canonical GL accounts and resolves member sub-ledger accounts.
All resolution keys on Account.code, so every helper is idempotent: the same
logical account always maps to the same row.

GL accounts (seeded once):
    1000  ASSET      M-Pesa Float / Settlement
    1100  ASSET      Suspense
    1200  ASSET      Advances Receivable            (parent of advance sub-ledgers)
    2000  LIABILITY  Member Contributions Payable   (parent of contribution sub-ledgers)
    2100  LIABILITY  Welfare Payable                (parent of welfare sub-ledgers)
    2200  LIABILITY  Shares Payable                 (parent of shares sub-ledgers)
    3000  EQUITY     Opening Balance Equity
    4000  INCOME     Fee Revenue
    4100  INCOME     Interest Income                (emergency-advance interest)

Sub-ledger accounts (created lazily on first use):
    member liability — code = "SL-<FUND_TYPE>-<fund_id>-U<user_id>"
    member advance   — code = "AR-<fund_id>-U<user_id>"  (ASSET, under 1200)
"""
from django.db import transaction

from .models import Account

# ── Canonical GL account codes ──────────────────────────────────────────────
MPESA_FLOAT          = '1000'
SUSPENSE             = '1100'
ADVANCES_RECEIVABLE  = '1200'
MEMBER_CONTRIB_PAYABLE = '2000'
WELFARE_PAYABLE      = '2100'
SHARES_PAYABLE       = '2200'
OPENING_BALANCE_EQUITY = '3000'
FEE_REVENUE          = '4000'
INTEREST_INCOME      = '4100'

# Each GL account: code → (name, type)
_GL_ACCOUNTS = {
    MPESA_FLOAT:            ('M-Pesa Float / Settlement',   Account.Type.ASSET),
    SUSPENSE:               ('Suspense',                    Account.Type.ASSET),
    ADVANCES_RECEIVABLE:    ('Advances Receivable',         Account.Type.ASSET),
    MEMBER_CONTRIB_PAYABLE: ('Member Contributions Payable', Account.Type.LIABILITY),
    WELFARE_PAYABLE:        ('Welfare Payable',             Account.Type.LIABILITY),
    SHARES_PAYABLE:         ('Shares Payable',              Account.Type.LIABILITY),
    OPENING_BALANCE_EQUITY: ('Opening Balance Equity',      Account.Type.EQUITY),
    FEE_REVENUE:            ('Fee Revenue',                 Account.Type.INCOME),
    INTEREST_INCOME:        ('Interest Income',             Account.Type.INCOME),
}

# Which GL liability account each fund_type's member sub-ledgers roll up into.
_FUND_PAYABLE_PARENT = {
    'contribution': MEMBER_CONTRIB_PAYABLE,
    'welfare':      WELFARE_PAYABLE,
    'shares':       SHARES_PAYABLE,
}


@transaction.atomic
def seed_chart_of_accounts() -> dict[str, Account]:
    """
    Idempotently create the canonical GL accounts. Returns {code: Account}.
    Safe to call repeatedly (used by data migration and the seed_coa command).
    """
    out: dict[str, Account] = {}
    for code, (name, type_) in _GL_ACCOUNTS.items():
        acct, _ = Account.objects.get_or_create(
            code=code, defaults={'name': name, 'type': type_},
        )
        out[code] = acct
    return out


def gl_account(code: str) -> Account:
    """Fetch a canonical GL account by code; assumes seeding has run."""
    return Account.objects.get(code=code)


def mpesa_float_account() -> Account:
    return gl_account(MPESA_FLOAT)


def fee_revenue_account() -> Account:
    return gl_account(FEE_REVENUE)


def suspense_account() -> Account:
    return gl_account(SUSPENSE)


def interest_income_account() -> Account:
    return gl_account(INTEREST_INCOME)


def _tenant_for_fund(fund_type: str, fund_id: int):
    """Resolve the tenant that owns a fund's community (Phase 6, P6-03).

    Lazy imports avoid a ledger→contributions dependency at module load. Returns
    None (shared) when not resolvable — safe under RLS (null tenant is visible).
    """
    try:
        from apps.contributions.models import Contribution, SharesFund, WelfareFund
        model = {
            'contribution': Contribution,
            'welfare':      WelfareFund,
            'shares':       SharesFund,
        }.get(fund_type)
        if model is None:
            return None
        obj = model.objects.filter(pk=fund_id).first()
        return getattr(getattr(obj, 'community', None), 'tenant', None)
    except Exception:
        return None


def member_receivable_account(*, user, fund_id: int) -> Account:
    """Resolve (get-or-create) the member's ASSET sub-ledger for emergency
    advances, rolling up into 1200 Advances Receivable. The member owes the
    advance back, so this is an asset of the platform/pool.

    Keyed on the structured identity (owner, fund_type, fund_id) — not the code
    string (ADR-0025). The unique constraint on those fields makes this
    idempotent and race-safe.
    """
    code = f"AR-{fund_id}-U{user.pk}"
    acct, _ = Account.objects.get_or_create(
        owner=user, fund_type='advance', fund_id=fund_id,
        defaults={
            'code':      code,
            'name':      f"{getattr(user, 'phone_number', user.pk)} · advance #{fund_id}",
            'type':      Account.Type.ASSET,
            'parent':    gl_account(ADVANCES_RECEIVABLE),
        },
    )
    return acct


def member_fund_account(*, user, fund_type: str, fund_id: int) -> Account:
    """
    Resolve (get-or-create) the member's sub-ledger LIABILITY account for a fund.

    The platform owes contributed funds back to the member, hence LIABILITY.
    Rolls up into the fund_type's payable GL account. New sub-ledgers are stamped
    with the fund's tenant (Phase 6); GL parents stay shared (tenant null).
    """
    parent_code = _FUND_PAYABLE_PARENT.get(fund_type)
    if parent_code is None:
        raise ValueError(f"Unknown fund_type {fund_type!r} for sub-ledger resolution.")

    # Keyed on the structured identity (owner, fund_type, fund_id) — not the code
    # string (ADR-0025); the unique constraint makes it idempotent and race-safe.
    code = f"SL-{fund_type.upper()}-{fund_id}-U{user.pk}"
    acct, _ = Account.objects.get_or_create(
        owner=user, fund_type=fund_type, fund_id=fund_id,
        defaults={
            'code':      code,
            'name':      f"{getattr(user, 'phone_number', user.pk)} · {fund_type} #{fund_id}",
            'type':      Account.Type.LIABILITY,
            'parent':    gl_account(parent_code),
            'tenant':    _tenant_for_fund(fund_type, fund_id),
        },
    )
    return acct
