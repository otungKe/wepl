"""``manage.py check_workers`` — is the async tier alive? (OP-2 / #161)

The only evidence Celery is actually processing is the DB-backed
``WorkerHeartbeat`` each watched beat task stamps on completion — and it is the
*only* evidence once the worker and beat tiers move off the web service, since
they then have no HTTP surface and no health-check path of their own.
``/api/ops/health/`` shows it to operators; this command shows the same rows
from a shell or a monitor, and exits non-zero when a task has gone quiet, so it
can back a check rather than be read by eye.

Exit codes: 0 healthy, 1 at least one watched task is stale.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.core.health import heartbeats, queue_depths


class Command(BaseCommand):
    help = "Report Celery worker heartbeats and queue depths; exit 1 if any task is stale."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true", dest="as_json",
            help="Emit a single JSON object instead of a table.",
        )
        parser.add_argument(
            "--skip-queues", action="store_true",
            help="Skip the broker read (queue depths) and report heartbeats only.",
        )

    def handle(self, *args, **options):
        rows = heartbeats()
        queues = {} if options["skip_queues"] else queue_depths()
        stale = [r["task"] for r in rows if r["stale"]]

        if options["as_json"]:
            self.stdout.write(json.dumps(
                {"heartbeats": rows, "queues": queues, "stale": stale},
                indent=2, sort_keys=True,
            ))
        else:
            self._write_table(rows, queues, stale)

        if stale:
            # Non-zero so a cron/monitor treats this as a failure. Never raise
            # CommandError: the stale list is the finding, not an error.
            raise SystemExit(1)

    def _write_table(self, rows, queues, stale):
        self.stdout.write("worker heartbeats")
        for r in rows:
            if r["never_seen"]:
                state, detail = "NEVER SEEN", "no run recorded yet"
            elif r["stale"]:
                state = "STALE"
                detail = f"last seen {r['age_seconds']}s ago (window {r['window_seconds']}s)"
            else:
                state = "ok"
                detail = f"last seen {r['age_seconds']}s ago"
            style = self.style.ERROR if r["stale"] else (
                self.style.WARNING if r["never_seen"] else self.style.SUCCESS)
            self.stdout.write(f"  {style(state.ljust(10))} {r['task']} — {detail}")

        if queues:
            self.stdout.write("queue depths")
            for name, depth in sorted(queues.items()):
                shown = "unreadable (broker unreachable)" if depth is None else depth
                self.stdout.write(f"  {name}: {shown}")

        if stale:
            self.stdout.write(self.style.ERROR(
                f"{len(stale)} watched task(s) stale — Celery is not processing. "
                "Check the wepl-worker / wepl-beat services, or the web service's "
                "own Celery processes while RUN_EMBEDDED_CELERY is on."))
        else:
            self.stdout.write(self.style.SUCCESS("no stale tasks"))
