"""
Chart of Accounts (COA).

Defines the canonical GL accounts and resolves member sub-ledger accounts.
All resolution keys on Account.code, so every helper is idempotent: the same
logical account always maps to the same row.

GL accounts (seeded once):
    1000  ASSET      M-Pesa Float / Settlement
    1100  ASSET      Suspense
    2000  LIABILITY  Member Contributions Payable   (parent of contribution sub-ledgers)
    2100  LIABILITY  Welfare Payable                (parent of welfare sub-ledgers)
    2200  LIABILITY  Shares Payable                 (parent of shares sub-ledgers)
    3000  EQUITY     Opening Balance Equity
    4000  INCOME     Fee Revenue

Sub-ledger accounts (created lazily on first use):
    code = "SL-<FUND_TYPE>-<fund_id>-U<user_id>"
"""
from django.db import transaction

from .models import Account

# ── Canonical GL account codes ──────────────────────────────────────────────
MPESA_FLOAT          = '1000'
SUSPENSE             = '1100'
MEMBER_CONTRIB_PAYABLE = '2000'
WELFARE_PAYABLE      = '2100'
SHARES_PAYABLE       = '2200'
OPENING_BALANCE_EQUITY = '3000'
FEE_REVENUE          = '4000'

# Each GL account: code → (name, type)
_GL_ACCOUNTS = {
    MPESA_FLOAT:            ('M-Pesa Float / Settlement',   Account.Type.ASSET),
    SUSPENSE:               ('Suspense',                    Account.Type.ASSET),
    MEMBER_CONTRIB_PAYABLE: ('Member Contributions Payable', Account.Type.LIABILITY),
    WELFARE_PAYABLE:        ('Welfare Payable',             Account.Type.LIABILITY),
    SHARES_PAYABLE:         ('Shares Payable',              Account.Type.LIABILITY),
    OPENING_BALANCE_EQUITY: ('Opening Balance Equity',      Account.Type.EQUITY),
    FEE_REVENUE:            ('Fee Revenue',                 Account.Type.INCOME),
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


def member_fund_account(*, user, fund_type: str, fund_id: int) -> Account:
    """
    Resolve (get-or-create) the member's sub-ledger LIABILITY account for a fund.

    The platform owes contributed funds back to the member, hence LIABILITY.
    Rolls up into the fund_type's payable GL account.
    """
    parent_code = _FUND_PAYABLE_PARENT.get(fund_type)
    if parent_code is None:
        raise ValueError(f"Unknown fund_type {fund_type!r} for sub-ledger resolution.")

    code = f"SL-{fund_type.upper()}-{fund_id}-U{user.pk}"
    acct, _ = Account.objects.get_or_create(
        code=code,
        defaults={
            'name':      f"{getattr(user, 'phone_number', user.pk)} · {fund_type} #{fund_id}",
            'type':      Account.Type.LIABILITY,
            'parent':    gl_account(parent_code),
            'owner':     user,
            'fund_type': fund_type,
            'fund_id':   fund_id,
        },
    )
    return acct
