"""Deployment-topology guards for the async tier (#161 / P0-01).

Celery used to run inside the web process. It now runs as its own Render
services, which introduces a class of failure the test suite could not see
before: a queue nobody consumes, a beat task whose queue has no worker, two
schedulers firing the same job, or a worker whose SECRET_KEY differs from the
web's. None of those raise anywhere — they just silently stop work from
happening (or, for a second beat, do it twice).

So these tests read the deployment artefacts themselves — ``render.yaml``,
``render.worker-tier.yaml`` and the entrypoint scripts — and assert them
against the Celery settings that are the actual source of truth for routing and
scheduling.

The async services are declared in ``render.worker-tier.yaml``, which Render
does not read, because they need a paid instance type that has not been adopted
yet; Celery still runs inside the web process. These tests therefore read the
worker services from whichever file currently declares them, so they guard the
definitions while they wait, and keep guarding them after the cutover moves
them into ``render.yaml``. ``EmbeddedCelerySwitchTests`` is what makes the
cutover atomic: it fails on either half of it.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml
from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR).parent
BACKEND = Path(settings.BASE_DIR)
RENDER_YAML = REPO_ROOT / "render.yaml"
# The async services, held out of the synced blueprint until a paid worker plan
# is adopted. The cutover moves these entries into render.yaml.
WORKER_TIER_YAML = REPO_ROOT / "render.worker-tier.yaml"

WEB_ENTRYPOINT = BACKEND / "start.sh"
WORKER_ENTRYPOINT = BACKEND / "start-worker.sh"
BEAT_ENTRYPOINT = BACKEND / "start-beat.sh"


def _blueprint() -> dict:
    return yaml.safe_load(RENDER_YAML.read_text())


def _worker_tier() -> dict:
    return yaml.safe_load(WORKER_TIER_YAML.read_text())


def _cutover_done() -> bool:
    """True once the async services live in the synced blueprint."""
    return any(s.get("type") == "worker" for s in _blueprint()["services"])


def _all_services() -> list[dict]:
    """Every declared service, wherever it is declared. Before the cutover the
    async ones are in the held-out fragment; after it, all in render.yaml."""
    out = list(_blueprint()["services"])
    if not _cutover_done():
        out += _worker_tier()["services"]
    return out


def _services(kind: str | None = None, runtime: str | None = None) -> list[dict]:
    out = _all_services()
    if kind:
        out = [s for s in out if s.get("type") == kind]
    if runtime:
        out = [s for s in out if s.get("runtime") == runtime]
    return out


def _env(service: dict) -> dict[str, dict]:
    return {e["key"]: e for e in service.get("envVars", [])}


def _script_default(script: Path, var: str) -> str | None:
    """Read a ``VAR="${OTHER:-default}"`` default out of a shell script."""
    m = re.search(
        r'^%s="\$\{[A-Z_]+:-([^}"]*)\}"' % re.escape(var),
        script.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def _routed_queues() -> set[str]:
    """Every queue the routing table can send a task to."""
    queues = {settings.CELERY_TASK_DEFAULT_QUEUE}
    for route in settings.CELERY_TASK_ROUTES.values():
        queues.add(route["queue"])
    return queues


def _queue_for(task_name: str) -> str:
    """Resolve a task name to its queue the way CELERY_TASK_ROUTES does."""
    for pattern, route in settings.CELERY_TASK_ROUTES.items():
        if fnmatch.fnmatch(task_name, pattern):
            return route["queue"]
    return settings.CELERY_TASK_DEFAULT_QUEUE


def _worker_services() -> list[dict]:
    return [s for s in _services("worker")
            if s.get("startCommand", "").endswith("start-worker.sh")]


def _beat_services() -> list[dict]:
    return [s for s in _services("worker")
            if s.get("startCommand", "").endswith("start-beat.sh")]


def _served_queues(service: dict) -> set[str]:
    """Queues one worker service consumes: its CELERY_QUEUES override if it
    declares one, otherwise the entrypoint's default."""
    override = _env(service).get("CELERY_QUEUES", {}).get("value")
    spec = override or _script_default(WORKER_ENTRYPOINT, "QUEUES")
    assert spec, "could not determine the queue list for %s" % service["name"]
    return {q.strip() for q in spec.split(",") if q.strip()}


class WebServiceStaysWebOnlyTests(SimpleTestCase):
    """The point of the split: the web process serves requests and nothing else."""

    def test_web_entrypoint_launches_celery_only_behind_the_fallback_flag(self):
        lines = WEB_ENTRYPOINT.read_text().splitlines()
        guard = next(i for i, l in enumerate(lines) if "RUN_EMBEDDED_CELERY" in l and l.strip().startswith("if "))
        closing = next(i for i, l in enumerate(lines[guard:], start=guard) if l.strip() == "fi")

        celery_lines = [i for i, l in enumerate(lines)
                        if re.match(r"\s*celery\s", l)]
        self.assertTrue(celery_lines, "start.sh no longer references celery at all — "
                                      "the RUN_EMBEDDED_CELERY fallback has gone missing")
        for i in celery_lines:
            self.assertTrue(
                guard < i < closing,
                "start.sh line %d starts Celery outside the RUN_EMBEDDED_CELERY guard: "
                "%r. Async work must run on the worker tier, not in the web process." % (i + 1, lines[i]),
            )

    def test_embedded_celery_default_matches_the_deployed_layout(self):
        """Unconfigured, the web process must do whatever the deployed topology
        needs. With no worker service anywhere, that is running Celery itself:
        "off" would mean the outbox never relays and nothing reconciles, with
        nothing raising to say so."""
        expected = "false" if _cutover_done() else "true"
        self.assertIn(
            "RUN_EMBEDDED_CELERY:-%s" % expected, WEB_ENTRYPOINT.read_text(),
            "start.sh must default RUN_EMBEDDED_CELERY to %r while the async "
            "services are %s the synced blueprint."
            % (expected, "in" if _cutover_done() else "held out of"))


class EmbeddedCelerySwitchTests(SimpleTestCase):
    """Exactly one tier may schedule. Both half-states are broken, so neither
    is allowed to merge.

    Celery in the web process *and* a dedicated beat service is two schedulers
    re-firing every ``CELERY_BEAT_SCHEDULE`` entry. Neither is no async
    processing at all — and that one is silent, because a task nobody runs
    raises nothing. So the switch in ``render.yaml`` and the presence of the
    worker services have to move together, in one edit.
    """

    def _api_services(self) -> list[dict]:
        services = [s for s in _blueprint()["services"]
                    if s.get("type") == "web" and s.get("runtime") == "python"]
        self.assertTrue(services, "render.yaml declares no Django web service")
        return services

    def test_every_web_service_declares_the_switch(self):
        for service in self._api_services():
            self.assertIn(
                "RUN_EMBEDDED_CELERY", _env(service),
                "%s does not declare RUN_EMBEDDED_CELERY. Declare it explicitly "
                "rather than relying on the default, so a blueprint re-sync "
                "overwrites whatever was set on the service by hand." % service["name"])

    def test_the_switch_agrees_with_the_worker_services(self):
        expected = "false" if _cutover_done() else "true"
        for service in self._api_services():
            actual = _env(service)["RUN_EMBEDDED_CELERY"].get("value")
            if _cutover_done():
                reason = ("render.yaml declares dedicated worker services, so %s must "
                          "set it to \"false\" — embedded beat plus a dedicated beat is "
                          "two schedulers double-firing every scheduled task."
                          % service["name"])
            else:
                reason = ("no worker service is declared in render.yaml, so %s must set "
                          "it to \"true\" — otherwise nothing runs the outbox relay, the "
                          "notifications or the reconciliation, and nothing says so."
                          % service["name"])
            self.assertEqual(actual, expected, reason)

    def test_the_held_out_fragment_declares_the_whole_async_tier(self):
        """Before the cutover, the fragment is the only definition of these
        services, so it has to be complete enough to paste in."""
        if _cutover_done():
            self.skipTest("the async services now live in render.yaml")
        names = {s["name"] for s in _worker_tier()["services"]}
        self.assertTrue(
            any(n.startswith("wepl-worker") for n in names)
            and any(n.startswith("wepl-beat") for n in names),
            "render.worker-tier.yaml must declare both a worker and a beat "
            "service; found %s" % sorted(names))


class QueueCoverageTests(SimpleTestCase):
    """A queue with no consumer is a task that never runs, and nothing raises."""

    def test_every_routed_queue_has_a_consumer(self):
        workers = _worker_services()
        self.assertTrue(workers, "render.yaml declares no Celery worker service")
        served = set().union(*(_served_queues(w) for w in workers))
        missing = _routed_queues() - served
        self.assertFalse(
            missing,
            "CELERY_TASK_ROUTES sends tasks to %s but no worker service consumes "
            "them — those tasks would queue forever. Add the queue to the -Q list "
            "in start-worker.sh (or to a service's CELERY_QUEUES)." % sorted(missing))

    def test_workers_consume_no_queue_that_is_never_routed_to(self):
        workers = _worker_services()
        served = set().union(*(_served_queues(w) for w in workers))
        stray = served - _routed_queues()
        self.assertFalse(
            stray,
            "worker services consume %s, which CELERY_TASK_ROUTES never routes to. "
            "Either the routing table lost an entry or the queue list is stale." % sorted(stray))

    def test_health_watched_queue_list_matches_the_routing_table(self):
        from apps.core import health
        self.assertEqual(
            set(health.CELERY_QUEUES), _routed_queues(),
            "apps.core.health.CELERY_QUEUES drives the queue depths shown at "
            "/api/ops/health/; a queue missing from it is invisible to operators.")


class BeatScheduleTests(SimpleTestCase):
    """Scheduled jobs run on the beat + worker tiers, not the web process."""

    def test_every_scheduled_task_lands_on_a_consumed_queue(self):
        served = set().union(*(_served_queues(w) for w in _worker_services()))
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            queue = _queue_for(entry["task"])
            self.assertIn(
                queue, served,
                "beat entry %r dispatches %s to queue %r, which no worker service "
                "consumes — the schedule would fire into a void." % (name, entry["task"], queue))

    def test_exactly_one_beat_service_per_stack(self):
        beats = _beat_services()
        self.assertTrue(beats, "render.yaml declares no Celery beat service")
        for service in beats:
            self.assertEqual(
                service.get("numInstances"), 1,
                "%s must be pinned to numInstances: 1. A second scheduler re-fires "
                "every CELERY_BEAT_SCHEDULE entry, and execute_due_standing_orders "
                "firing twice is a duplicate money movement attempt." % service["name"])

    def test_watched_heartbeat_tasks_are_actually_scheduled(self):
        from apps.core import health
        scheduled = {e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values()}
        for task in health.WATCHED_TASKS:
            self.assertIn(
                task, scheduled,
                "%s is watched for staleness but is not in CELERY_BEAT_SCHEDULE, so "
                "it can never stamp a heartbeat and would read as permanently "
                "never-seen." % task)


class AsyncServiceConfigTests(SimpleTestCase):
    """Config the split makes newly load-bearing."""

    def test_async_services_do_not_run_migrations(self):
        for script in (WORKER_ENTRYPOINT, BEAT_ENTRYPOINT):
            body = script.read_text()
            self.assertNotIn(
                "manage.py migrate --noinput", body,
                "%s applies migrations. The web service is the single migration "
                "writer; three services racing `migrate` contend on the same locks." % script.name)
            self.assertIn(
                "wait-for-migrations.sh", body,
                "%s must wait for the web deploy's migrations, or it can boot "
                "against a half-migrated schema." % script.name)

    def test_async_services_inherit_the_web_secret_key(self):
        for service in _worker_services() + _beat_services():
            entry = _env(service).get("SECRET_KEY")
            self.assertIsNotNone(entry, "%s declares no SECRET_KEY" % service["name"])
            self.assertNotIn(
                "generateValue", entry,
                "%s generates its own SECRET_KEY. It must copy the web service's: "
                "signed download URLs (apps.files.signing) and the "
                "FIELD_ENCRYPTION_KEYS fallback derive from it, so a different key "
                "silently breaks anything the other tier signed or encrypted." % service["name"])
            self.assertEqual(
                entry.get("fromService", {}).get("envVarKey"), "SECRET_KEY",
                "%s should copy SECRET_KEY from its web service via "
                "fromService/envVarKey." % service["name"])

    def test_async_services_share_the_broker_with_their_web_service(self):
        """Worker and web must point at the same Redis, or enqueued tasks are
        published to a broker nobody is consuming."""
        for service in _worker_services() + _beat_services():
            broker = _env(service).get("REDIS_URL", {}).get("fromService", {})
            self.assertEqual(
                broker.get("type"), "redis",
                "%s must take REDIS_URL from the Redis instance its web service "
                "uses." % service["name"])

    def test_async_services_are_not_on_a_free_plan(self):
        """Render has no free instance type for `type: worker`; a `free` plan here
        makes the whole blueprint sync fail."""
        for service in _services("worker"):
            self.assertNotEqual(
                service.get("plan"), "free",
                "%s: Render offers no free instance type for background workers." % service["name"])

    def test_async_services_declare_the_settings_module(self):
        for service in _services("worker"):
            env = _env(service)
            self.assertEqual(
                env.get("DJANGO_SETTINGS_MODULE", {}).get("value"),
                "config.settings.production",
                "%s must pin DJANGO_SETTINGS_MODULE; config/celery.py's fallback is "
                "easy to drift from." % service["name"])
            self.assertIn(
                "ALLOWED_HOSTS", env,
                "%s must set ALLOWED_HOSTS — production.py has no default for it, so "
                "settings do not import without it, even with no HTTP surface." % service["name"])
