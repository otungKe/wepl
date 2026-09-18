"""``manage.py check_workers`` — the shell-side view of the async tier (#161).

Once Celery left the web process, the worker and beat services have no health
check path of their own; ``WorkerHeartbeat`` is the only evidence they are
alive. This command is how that evidence is read outside the ops console, so
its exit code has to be trustworthy.
"""
from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core import health
from apps.core.models import WorkerHeartbeat

WATCHED = "apps.core.tasks.process_outbox"


class CheckWorkersCommandTests(TestCase):

    def _run(self, **kwargs):
        out = StringIO()
        call_command("check_workers", stdout=out, skip_queues=True, **kwargs)
        return out.getvalue()

    def test_fresh_heartbeats_report_ok_and_exit_zero(self):
        now = timezone.now()
        for task in health.WATCHED_TASKS:
            WorkerHeartbeat.objects.create(task_name=task, last_seen=now)

        output = self._run()

        self.assertIn("no stale tasks", output)
        self.assertNotIn("STALE", output)

    def test_stale_heartbeat_exits_non_zero_and_names_the_task(self):
        now = timezone.now()
        for task in health.WATCHED_TASKS:
            WorkerHeartbeat.objects.create(task_name=task, last_seen=now)
        WorkerHeartbeat.objects.filter(task_name=WATCHED).update(
            last_seen=now - timedelta(seconds=health.WATCHED_TASKS[WATCHED] + 60))

        out = StringIO()
        with self.assertRaises(SystemExit) as raised:
            call_command("check_workers", stdout=out, skip_queues=True)

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("STALE", out.getvalue())
        self.assertIn(WATCHED, out.getvalue())

    def test_a_task_never_seen_is_surfaced_but_does_not_fail_the_check(self):
        """A stack that has just booted has stamped nothing yet; that is not a
        regression, and must not trip a monitor on every deploy."""
        output = self._run()

        self.assertIn("NEVER SEEN", output)
        self.assertIn("no stale tasks", output)

    def test_json_output_carries_the_stale_list(self):
        now = timezone.now()
        WorkerHeartbeat.objects.create(
            task_name=WATCHED,
            last_seen=now - timedelta(seconds=health.WATCHED_TASKS[WATCHED] + 60))

        out = StringIO()
        with self.assertRaises(SystemExit):
            call_command("check_workers", stdout=out, skip_queues=True, as_json=True)

        payload = json.loads(out.getvalue())
        self.assertEqual(payload["stale"], [WATCHED])
        self.assertEqual(payload["queues"], {})

    def test_unreachable_broker_does_not_break_the_report(self):
        """Queue depths are best-effort: a dead broker must still let the
        heartbeat half of the report through."""
        now = timezone.now()
        for task in health.WATCHED_TASKS:
            WorkerHeartbeat.objects.create(task_name=task, last_seen=now)

        out = StringIO()
        with mock.patch(
            "apps.core.management.commands.check_workers.queue_depths",
            return_value={q: None for q in health.CELERY_QUEUES},
        ):
            call_command("check_workers", stdout=out)

        self.assertIn("unreadable (broker unreachable)", out.getvalue())
        self.assertIn("no stale tasks", out.getvalue())
