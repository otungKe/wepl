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
RETAINED_SURPLUS     = '3200'
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
    RETAINED_SURPLUS:       ('Retained Surplus',            Account.Type.EQUITY),
    FEE_REVENUE:            ('Fee Revenue',                 Account.Type.INCOME),
    INTEREST_INCOME:        ('Interest Income',             Account.Type.INCOME),
}

# Which GL liability account each fund_type's member sub-ledgers roll up into.
_FUND_PAYABLE_PARENT = {
    'contribution': MEMBER_CONTRIB_PAYABLE,
    'welfare':      WELFARE_PAYABLE,
    'shares':       SHARES_PAYABLE,
}

# The GL "head" every sub-ledger fund_type hangs off — the prefix of its code.
# Stable regardless of re-parenting (pool control accounts, ADR-0025 Part B).
_FUND_GL = {**_FUND_PAYABLE_PARENT, 'advance': ADVANCES_RECEIVABLE}

# ── Canonical, GL-anchored account codes (ADR-0025) ──────────────────────────
# One consistent, sortable shape for every account so the whole tree is a single
# searchable namespace. Fixed-width so codes align and sort; safe to widen later
# because the code is display metadata, not identity (identity = id/account_uid).
POOL_CODE_WIDTH   = 7    # up to 9,999,999 pools/funds per GL head
MEMBER_CODE_WIDTH = 9    # up to ~1e9 members


def pool_code(gl_code: str, fund_id: int) -> str:
    """A pool/fund control account, e.g. ``2000-0350000`` (GL 2000, pool 350000)."""
    return f"{gl_code}-{int(fund_id):0{POOL_CODE_WIDTH}d}"


def sub_ledger_code(gl_code: str, fund_id: int, owner_id: int) -> str:
    """A member sub-ledger, e.g. ``2000-0350000-000000055`` (member 55 in pool)."""
    return f"{pool_code(gl_code, fund_id)}-{int(owner_id):0{MEMBER_CODE_WIDTH}d}"


def code_for_fund(fund_type: str, fund_id: int, owner_id: int) -> str:
    """Canonical sub-ledger code for a (fund_type, fund_id, owner)."""
    gl = _FUND_GL.get(fund_type)
    if gl is None:
        raise ValueError(f"Unknown fund_type {fund_type!r} for code generation.")
    return sub_ledger_code(gl, fund_id, owner_id)


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
    acct, _ = Account.objects.get_or_create(
        owner=user, fund_type='advance', fund_id=fund_id,
        defaults={
            'code':      code_for_fund('advance', fund_id, user.pk),
            'name':      f"{getattr(user, 'phone_number', user.pk)} · advance #{fund_id}",
            'type':      Account.Type.ASSET,
            'parent':    gl_account(ADVANCES_RECEIVABLE),
        },
    )
    return acct


def ensure_custody(*, fund_type: str, fund_id: int):
    """Ensure a pool has a custody/legal-title anchor (ADR-0027).

    Idempotent; defaults to the platform holding the pool in trust for its
    members. Called when a pool is born so every pool answers "held by whom,
    under what basis" — the trust-law anchor that makes collective ownership and
    "a liability owed by whom" legally defined.
    """
    from .models import CustodyArrangement
    arrangement, _ = CustodyArrangement.objects.get_or_create(
        fund_type=fund_type, fund_id=fund_id,
    )
    return arrangement


def retained_surplus_account(*, fund_id: int) -> Account:
    """Resolve (get-or-create) a pool's **retained-surplus** control account
    (ADR-0027). Owner-less EQUITY account (code e.g. ``3200-0000042``) holding a
    pool's collectively-owned surplus — external income lands here and stays until
    a distribution is declared. Keyed on ``fund_type='retained'`` so it never
    collides with the LIABILITY pool control account for the same fund id.
    """
    gl = gl_account(RETAINED_SURPLUS)
    acct, _ = Account.objects.get_or_create(
        owner=None, fund_type='retained', fund_id=fund_id,
        defaults={
            'code':   pool_code(RETAINED_SURPLUS, fund_id),
            'name':   f"Pool #{fund_id} · retained surplus",
            'type':   gl.type,
            'parent': gl,
            'tenant': _tenant_for_fund('contribution', fund_id),
        },
    )
    return acct


def pool_account(*, fund_type: str, fund_id: int) -> Account:
    """Resolve (get-or-create) a pool/fund **control account** (ADR-0025 Part B).

    A pool is a first-class ledger entity: an owner-less account (code e.g.
    ``2000-0350000``) that parents the pool's member sub-ledgers and can hold
    pool-level money (escrow, unallocated pot). Keyed on (fund_type, fund_id).
    Its birth also anchors the pool's custody arrangement (ADR-0027).
    """
    parent_code = _FUND_PAYABLE_PARENT.get(fund_type)
    if parent_code is None:
        raise ValueError(f"Unknown fund_type {fund_type!r} for pool account.")
    gl = gl_account(parent_code)
    acct, _ = Account.objects.get_or_create(
        owner=None, fund_type=fund_type, fund_id=fund_id,
        defaults={
            'code':   pool_code(parent_code, fund_id),
            'name':   f"Pool #{fund_id} · {fund_type} payable",
            'type':   gl.type,
            'parent': gl,
            'tenant': _tenant_for_fund(fund_type, fund_id),
        },
    )
    ensure_custody(fund_type=fund_type, fund_id=fund_id)
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
    # Parented under the pool control account, which nets into the GL head.
    pool = pool_account(fund_type=fund_type, fund_id=fund_id)
    acct, _ = Account.objects.get_or_create(
        owner=user, fund_type=fund_type, fund_id=fund_id,
        defaults={
            'code':      code_for_fund(fund_type, fund_id, user.pk),
            'name':      f"{getattr(user, 'phone_number', user.pk)} · {fund_type} #{fund_id}",
            'type':      Account.Type.LIABILITY,
            'parent':    pool,
            'tenant':    _tenant_for_fund(fund_type, fund_id),
        },
    )
    return acct
