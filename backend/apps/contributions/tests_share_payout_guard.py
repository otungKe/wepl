"""No path pays a member out of their share without a group decision (ADR-0027 §0).

A member's share is a claim on the group, realised only by a group decision — a
payout, an exit settlement or a wind-up — never withdrawn on demand. The ledger
recipes that draw a single member's share down are few, so this reads the
source (like ``apps/core/tests_module_boundaries.py``, so a lazy call counts)
and fails the build if one of them is called from anywhere not listed here.

Adding a caller is a product decision, not a refactor: the entry has to say
which group decision governs it.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

APPS_DIR = Path(settings.BASE_DIR) / "apps"

#: Names that take money out of one member's share, directly or by running
#: the step that does.
SHARE_DRAWING = {
    "disbursement_lines",        # debit one member's share, cash out
    "advance_setoff_lines",      # debit one member's share to clear their debt
    "reallocate_to_org_lines",   # move one member's share to an organization
    "_pay_out_share",            # DisbursementService: pays a whole share
    "_set_off_advances",         # DisbursementService: runs the set-off
    "_execute_exit",             # DisbursementService: set-off + pay-out
}

#: (module, enclosing function, name called) → the group decision behind it.
ALLOWED = {
    ("contributions/services/rosca.py", "ROSCAService.mark_slot_paid", "disbursement_lines"):
        "A ROSCA turn, in the order the group set; ROSCAs are unchanged by ADR-0027.",
    ("contributions/services/standing_orders.py", "StandingOrderService.execute_standing_order",
     "disbursement_lines"):
        "A rotating standing order paying a participant their turn, set up and run by an admin.",
    ("contributions/services/disbursement.py", "DisbursementService._pay_out_share",
     "disbursement_lines"):
        "An exit or wind-up payout; see its callers below.",
    ("contributions/services/disbursement.py", "DisbursementService._set_off_advances",
     "advance_setoff_lines"):
        "Clearing a leaver's debt; see its callers below.",
    ("contributions/services/disbursement.py", "DisbursementService._execute_exit",
     "_set_off_advances"):
        "An exit, once the group has voted it.",
    ("contributions/services/disbursement.py", "DisbursementService._execute_exit",
     "_pay_out_share"):
        "An exit, once the group has voted it.",
    ("contributions/services/disbursement.py", "DisbursementService._schedule_execution",
     "_execute_exit"):
        "Reached only from vote() once approvals meet the group's threshold.",
    ("contributions/services/wind_up.py", "WindUpService.execute", "_set_off_advances"):
        "A wind-up the group approved through PoolGovernanceService.",
    ("contributions/services/wind_up.py", "WindUpService.execute", "_pay_out_share"):
        "A wind-up the group approved through PoolGovernanceService.",
}


def _calls():
    """Every call to a SHARE_DRAWING name outside tests and migrations."""
    found = set()
    for path in APPS_DIR.rglob("*.py"):
        rel = path.relative_to(APPS_DIR).as_posix()
        if "/migrations/" in rel or path.name.startswith("tests") or "/tests/" in rel:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))

        def visit(node, scope):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    visit(child, scope + [child.name])
                    continue
                if isinstance(child, ast.Call):
                    fn = child.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                    if name in SHARE_DRAWING:
                        found.add((rel, ".".join(scope) or "<module>", name))
                visit(child, scope)

        visit(tree, [])
    return found


class SharePayoutNeedsAGroupDecisionTests(SimpleTestCase):

    def test_every_share_drawing_call_is_governed(self):
        unexpected = _calls() - set(ALLOWED)
        self.assertFalse(
            unexpected,
            "These pay a member out of their share without a listed group decision "
            f"(ADR-0027 §0). Route them through a vote, or add them to ALLOWED with "
            f"the decision that governs them: {sorted(unexpected)}")

    def test_allowlist_has_no_stale_entries(self):
        stale = set(ALLOWED) - _calls()
        self.assertFalse(stale, f"ALLOWED names calls that no longer exist: {sorted(stale)}")

    def test_scan_sees_a_known_call(self):
        # Guards the guard: if the scan stopped finding anything it would pass.
        self.assertIn(
            ("contributions/services/rosca.py", "ROSCAService.mark_slot_paid", "disbursement_lines"),
            _calls())
