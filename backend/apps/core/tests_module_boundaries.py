"""Module-boundary guards for the backend app graph.

The apps under ``backend/apps/`` are the unit we would ever split, extract or
reason about in isolation, and for years nothing checked how they depend on each
other. They drifted into a single import cycle spanning eleven of the nineteen
apps, held together by cross-app imports written *inside functions* rather than
at the top of the file — the workaround that keeps Django booting when the module
graph cannot be loaded in dependency order.

These tests read the imports out of the source (not at runtime, so a lazy import
counts exactly like a top-level one) and assert four things:

* ``apps.core`` is the foundation and depends on no sibling app.
* ``apps.ledger`` is the book of record and depends on nothing but ``core`` —
  including the ADR-0007 controls chokepoint, which is registered *into* the
  ledger rather than imported *by* it.
* ``apps.mpesa`` is a Daraja wire client and depends on no sibling app at all.
* the remaining cycle does not grow.

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
#: and ``audit`` behind it.
CYCLE_BASELINE = {
    "activity", "communities", "contributions", "users", "verification",
}

#: ``apps.ledger`` may import these and nothing else. Controls reach the ledger by
#: registering into ``apps.ledger.chokepoint`` at startup (ADR-0007), so the
#: enforcement point stays single without the ledger knowing who enforces it.
LEDGER_MAY_IMPORT = {"core"}

#: ``apps.mpesa`` may import these and nothing else: it is the Daraja wire client
#: plus the two rail records, and what a settled payment *means* is handed to it
#: through ``apps.mpesa.settlement`` (ADR-0033).
MPESA_MAY_IMPORT = {"core"}


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
