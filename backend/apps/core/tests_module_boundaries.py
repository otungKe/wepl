"""Module-boundary guards for the backend app graph.

The apps under ``backend/apps/`` are the unit we would ever split, extract or
reason about in isolation, and for years nothing checked how they depend on each
other. They drifted into a single import cycle spanning eleven of the nineteen
apps, held together by cross-app imports written *inside functions* rather than
at the top of the file — the workaround that keeps Django booting when the module
graph cannot be loaded in dependency order.

These tests read the imports out of the source (not at runtime, so a lazy import
counts exactly like a top-level one) and assert five things:

* ``apps.core`` is the foundation and depends on no sibling app.
* ``apps.ledger`` is the book of record and depends on nothing but ``core`` —
  including the ADR-0007 controls chokepoint, which is registered *into* the
  ledger rather than imported *by* it — and stores no rail vocabulary either.
* ``apps.mpesa`` is a Daraja wire client and depends on no sibling app at all.
* ``apps.verification`` is the identity ledger and depends on nothing but
  ``core``: what a decision *does* elsewhere registers into
  ``apps.verification.hooks``.
* the remaining cycle does not grow.

A last group checks the three leaf apps again through the model registry, since a
foreign key written as a string never shows up as an import (``FK_BASELINE``).

The last is a ratchet, not an endorsement: :data:`CYCLE_BASELINE` is the set of
apps that are still mutually entangled. Shrinking it is the work; adding to it is
a regression, and this test is what makes the difference visible in review
instead of two years later.

Test modules are excluded throughout. A test importing across apps is normal and
says nothing about whether the apps themselves are separable.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

APPS_DIR = Path(settings.BASE_DIR) / "apps"

#: Apps still in one strongly-connected component. This set must only ever shrink.
#:
#: History, so the direction is visible: eleven apps when this test was written
#: (ADR-0033 freed ``ledger``), then nine once ``controls`` stopped being reached
#: into by ``apps.verification`` and started registering its own reaction instead,
#: then seven once the Daraja endpoints moved off ``apps.mpesa`` — which freed
#: ``payments`` with it, because nothing below the domain reached up any more —
#: then five once the RLS tenant pin stopped subclassing the authenticator and
#: started registering into ``apps.core.request_context``, freeing ``tenants``
#: and ``audit`` behind it, then four once the case ledger stopped writing the
#: customer-facing ``VerificationRequest`` row and stopped reaching into
#: ``apps.users.admin`` for its notification helpers.
#:
#: What is left is not another seam. These four are mutually entangled through
#: the domain itself — ``contributions`` alone imports ``communities`` in 24
#: places — and no single edge removal frees any of them. Shrinking further is a
#: question about who owns a group and its money, not a registry away.
CYCLE_BASELINE = {
    "communities", "contributions", "users",
}

#: ``apps.ledger`` may import these and nothing else. Controls reach the ledger by
#: registering into ``apps.ledger.chokepoint`` at startup (ADR-0007), so the
#: enforcement point stays single without the ledger knowing who enforces it.
LEDGER_MAY_IMPORT = {"core"}

#: ``apps.mpesa`` may import these and nothing else: it is the Daraja wire client
#: plus the two rail records, and what a settled payment *means* is handed to it
#: through ``apps.mpesa.settlement`` (ADR-0033).
MPESA_MAY_IMPORT = {"core"}

#: ``apps.verification`` may import these and nothing else. It owns the KYC case
#: timeline and the transition table; who reacts to a decision — controls closing
#: the held movement and the customer's request row, users telling the applicant —
#: registers into ``apps.verification.hooks`` (ADR-0033).
VERIFICATION_MAY_IMPORT = {"core"}


def _app_names() -> set[str]:
    return {
        d.name for d in APPS_DIR.iterdir()
        if d.is_dir() and (d / "__init__.py").exists()
    }


def _is_test_module(path: Path) -> bool:
    return path.name == "tests.py" or path.name.startswith("tests_") or path.name.startswith("test_")


def _imports_of(app: str, known: set[str]) -> dict[str, list[str]]:
    """Map each sibling app *app* imports to the files that import it.

    Walks the AST rather than grepping, so ``from apps.x import y`` and
    ``import apps.x.y`` are both caught and a match inside a string or comment is
    not. Migrations are excluded: they are a frozen historical record, not code
    anyone is free to restructure.
    """
    found: dict[str, list[str]] = {}
    root = APPS_DIR / app
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "migrations")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath) / filename
            if _is_test_module(path):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - would fail the build elsewhere
                continue
            for node in ast.walk(tree):
                targets: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    targets.append(node.module)
                elif isinstance(node, ast.Import):
                    targets.extend(alias.name for alias in node.names)
                for dotted in targets:
                    parts = dotted.split(".")
                    if len(parts) >= 2 and parts[0] == "apps" and parts[1] in known:
                        other = parts[1]
                        if other != app:
                            rel = str(path.relative_to(APPS_DIR.parent))
                            found.setdefault(other, [])
                            if rel not in found[other]:
                                found[other].append(rel)
    return found


def _graph() -> dict[str, set[str]]:
    known = _app_names()
    return {app: set(_imports_of(app, known)) for app in known}


def _cycles(graph: dict[str, set[str]]) -> list[set[str]]:
    """Strongly-connected components of size > 1 (Tarjan, iterative)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    counter = 0
    out: list[set[str]] = []

    for root in graph:
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph.get(child, ())))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = set()
                while True:
                    popped = stack.pop()
                    on_stack.discard(popped)
                    component.add(popped)
                    if popped == node:
                        break
                if len(component) > 1:
                    out.append(component)
    return out


class CoreIsTheFoundationTests(SimpleTestCase):

    def test_core_imports_no_sibling_app(self):
        offenders = _imports_of("core", _app_names())
        self.assertEqual(
            offenders, {},
            "apps.core is the foundation every other app builds on, so it must not "
            "depend on any of them. Move the shared piece down into core, or invert "
            "the call with a registry the way apps.core.events does.\n"
            f"Found: {offenders}",
        )


class LedgerIsALeafTests(SimpleTestCase):

    def test_ledger_imports_only_core(self):
        imports = _imports_of("ledger", _app_names())
        stray = {k: v for k, v in imports.items() if k not in LEDGER_MAY_IMPORT}
        self.assertEqual(
            stray, {},
            "apps.ledger is the book of record: it answers what a balance is, never "
            "who may move it or which rail carried it. Domain role checks belong in "
            "the domain app, rail detail in apps.payments, and anything that must run "
            "inside post_journal registers into apps.ledger.chokepoint (ADR-0007) "
            "instead of being imported here.\n"
            f"Found: {stray}",
        )

    def test_ledger_models_carry_no_rail_vocabulary(self):
        """No ledger model field is named after a payment rail (#159, ADR-0030).

        The import check above says the ledger does not *call* a rail. This says
        it does not *store* one either — which is the half of #159 that survived
        the payout-orchestration move, as three Daraja-named columns on
        ``FinancialTransaction``. They were dropped in ``ledger.0021``: the rail
        dimension is ``payments.PaymentIntent``'s, read through
        ``apps.payments.money_activity``, and a column here would be a second
        copy of it — which is how they drifted in the first place (the payout
        path wrote them, the collection path never did).

        Field declarations only. ``coa.MPESA_FLOAT`` is a chart-of-accounts code
        for the settlement account, not a rail detail, and prose describing a
        counterparty's registered M-Pesa name is not a field.
        """
        rail_words = ("mpesa", "daraja", "safaricom", "stk", "b2c", "c2b")
        offenders: dict[str, list[str]] = {}
        for path in sorted((APPS_DIR / "ledger").rglob("*.py")):
            if "migrations" in path.parts or _is_test_module(path):
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                call = node.value
                if not (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "models"):
                    continue
                for target in node.targets:
                    name = getattr(target, "id", "")
                    if any(word in name.lower() for word in rail_words):
                        offenders.setdefault(
                            str(path.relative_to(APPS_DIR)), []).append(name)

        self.assertEqual(
            offenders, {},
            "A rail-named field was added to a ledger model. The ledger answers "
            "what a balance is, never which rail carried it: the correlation id "
            "and the receipt belong to payments.PaymentIntent (ADR-0014/0030), "
            "read through apps.payments.money_activity.\n"
            f"Found: {offenders}",
        )

    def test_ledger_is_not_in_any_cycle(self):
        for component in _cycles(_graph()):
            self.assertNotIn(
                "ledger", component,
                "apps.ledger has been pulled back into an import cycle with "
                f"{sorted(component - {'ledger'})}. Whatever the ledger now needs from "
                "them, it should be handed rather than fetched.",
            )


class MpesaIsARailClientTests(SimpleTestCase):

    def test_mpesa_imports_no_domain_app(self):
        imports = _imports_of("mpesa", _app_names())
        stray = {k: v for k, v in imports.items() if k not in MPESA_MAY_IMPORT}
        self.assertEqual(
            stray, {},
            "apps.mpesa speaks Daraja and owns the two rail records; it does not "
            "decide what a payment is for. The pay-in endpoint lives in "
            "apps.contributions and the webhooks in apps.payments, and anything the "
            "rail needs from the domain is registered into apps.mpesa.settlement "
            "(ADR-0033) instead of being imported here.\n"
            f"Found: {stray}",
        )

    def test_mpesa_is_not_in_any_cycle(self):
        for component in _cycles(_graph()):
            self.assertNotIn(
                "mpesa", component,
                "apps.mpesa has been pulled back into an import cycle with "
                f"{sorted(component - {'mpesa'})}. A rail client that imports the "
                "application layer is how the Daraja views ended up owning the "
                "contribution model graph.",
            )


class VerificationIsACaseLedgerTests(SimpleTestCase):

    def test_verification_imports_only_core(self):
        imports = _imports_of("verification", _app_names())
        stray = {k: v for k, v in imports.items() if k not in VERIFICATION_MAY_IMPORT}
        self.assertEqual(
            stray, {},
            "apps.verification is the identity analogue of the ledger: it records "
            "what was decided about a case and enforces the transition table. It "
            "does not own the movement a case was opened over, the customer-facing "
            "request row, or what the applicant is told — those register into "
            "apps.verification.hooks (ADR-0033) instead of being imported here.\n"
            f"Found: {stray}",
        )

    def test_verification_is_not_in_any_cycle(self):
        for component in _cycles(_graph()):
            self.assertNotIn(
                "verification", component,
                "apps.verification has been pulled back into an import cycle with "
                f"{sorted(component - {'verification'})}. A case ledger that writes "
                "another app's rows is how KYC review state ended up editable from "
                "three places at once.",
            )


class ImportCycleRatchetTests(SimpleTestCase):

    def test_the_cycle_does_not_grow(self):
        entangled: set[str] = set()
        for component in _cycles(_graph()):
            entangled |= component
        added = entangled - CYCLE_BASELINE
        self.assertEqual(
            added, set(),
            f"These apps have joined the import cycle: {sorted(added)}. A new mutual "
            "dependency between apps is a structural regression — the graph is "
            "supposed to be getting simpler. Invert the new edge (a registry filled "
            "at AppConfig.ready(), or an event through apps.core.events) rather than "
            "widening CYCLE_BASELINE.",
        )

    def test_the_baseline_is_not_stale(self):
        """CYCLE_BASELINE must describe reality, so freeing an app updates it."""
        entangled: set[str] = set()
        for component in _cycles(_graph()):
            entangled |= component
        freed = CYCLE_BASELINE - entangled
        self.assertEqual(
            freed, set(),
            f"{sorted(freed)} no longer sit in an import cycle — good. Remove them "
            "from CYCLE_BASELINE so the ratchet holds at the new, better position.",
        )


# ── Foreign keys ──────────────────────────────────────────────────────────────
#
# The import scan above cannot see a foreign key written as a string
# (``models.ForeignKey('contributions.Contribution', ...)``): the app imports
# nothing, yet its table still depends on the other app's table, its migrations
# depend on the other app's migrations, and its rows cannot exist without the
# other app's rows. So the three leaf apps are checked again at the level of the
# model registry.
#
# Every leaf may point at the user model (who acted / whose money) and at
# ``tenants.Tenant`` (the isolation boundary). Anything else is listed in
# ``FK_BASELINE`` with the reason it is still there, and that list may only
# shrink: a new edge fails the build, and so does an entry left behind after
# its field is gone.

#: Apps whose models are held to the leaf rule.
FK_LEAF_APPS = ("ledger", "mpesa", "verification")

#: Targets any leaf model may reference.
FK_ALWAYS_ALLOWED = {"tenants.Tenant"}  # plus settings.AUTH_USER_MODEL, added below

#: ``"<app>.<Model>.<field>": "<target app>.<Model>"`` edges that exist today.
FK_BASELINE = {
    # ADR-0030 is dissolving FinancialTransaction; these go with it.
    "ledger.FinancialTransaction.contribution": "contributions.Contribution",
    "ledger.FinancialTransaction.welfare_fund": "contributions.WelfareFund",
    "ledger.FinancialTransaction.shares_fund": "contributions.SharesFund",
    # A sub-ledger's owning party. A party reference, not a domain dependency,
    # but still an edge into the group context.
    "ledger.Account.owner_org": "organizations.Organization",
    # The rail record remembers what a pay-in is for. That belongs on the
    # PaymentIntent as an opaque purpose/subject (boundary audit, finding 8).
    "mpesa.MpesaSTKRequest.contribution": "contributions.Contribution",
    "mpesa.MpesaSTKRequest.welfare_fund": "contributions.WelfareFund",
    "mpesa.MpesaSTKRequest.shares_fund": "contributions.SharesFund",
    "mpesa.MpesaSTKRequest.advance": "contributions.EmergencyAdvance",
    "mpesa.MpesaC2BTransaction.contribution": "contributions.Contribution",
    # Which operator acted. An actor reference into the back office.
    "verification.VerificationCase.assigned_to": "backoffice.StaffAccount",
    "verification.CaseEvent.actor_staff": "backoffice.StaffAccount",
    "verification.CaseNote.author_staff": "backoffice.StaffAccount",
}


def _leaf_foreign_keys() -> dict[str, str]:
    """Every concrete relation from a leaf app's model to another app's model."""
    from django.apps import apps as registry

    edges: dict[str, str] = {}
    for label in FK_LEAF_APPS:
        for model in registry.get_app_config(label).get_models():
            for field in model._meta.get_fields():
                if not (field.is_relation and field.concrete and field.related_model):
                    continue
                target = field.related_model._meta
                if target.app_label == label:
                    continue
                edges[f"{label}.{model.__name__}.{field.name}"] = f"{target.app_label}.{target.object_name}"
    return edges


class LeafForeignKeyRatchetTests(SimpleTestCase):

    def _allowed(self) -> set[str]:
        return FK_ALWAYS_ALLOWED | {settings.AUTH_USER_MODEL}

    def test_no_new_foreign_key_leaves_a_leaf_app(self):
        allowed = self._allowed()
        new = {
            edge: target for edge, target in _leaf_foreign_keys().items()
            if target not in allowed and FK_BASELINE.get(edge) != target
        }
        self.assertEqual(
            new, {},
            "A leaf app (ledger, mpesa, verification) gained a foreign key into "
            "another context. A string reference hides it from the import test, but "
            "the tables and migrations still depend on each other. Carry an opaque "
            "id or a (purpose, subject_ref) pair instead, or have the other app hold "
            f"the relation.\nFound: {new}",
        )

    def test_the_foreign_key_baseline_is_not_stale(self):
        present = _leaf_foreign_keys()
        gone = {edge: target for edge, target in FK_BASELINE.items()
                if present.get(edge) != target}
        self.assertEqual(
            gone, {},
            f"{sorted(gone)} no longer exist — good. Remove them from FK_BASELINE "
            "so the ratchet holds at the new position.",
        )
