"""The controls side of a verification case decision (ADR-0033).

The behaviour itself — approve issues a single-use override and releases the
hold — is already covered end to end by
``apps.verification.tests.EddPipelineTests``. What needs its own tests is the
seam introduced when that code stopped being inline in
``verification.service.decide_subject_case`` and started being registered from
``ControlsConfig.ready()``: that it is actually wired up, that it stays a single
registration, and that it is still part of the decision rather than a
notification about one.
"""
from decimal import Decimal

from django.db import transaction
from django.test import TestCase

from apps.backoffice.models import StaffAccount
from apps.controls import cases
from apps.controls.models import ControlOverride, HeldMovement
from apps.users.models import User
from apps.verification import service, hooks
from apps.verification.models import VerificationCase


class RegistrationTests(TestCase):

    def test_the_reaction_is_registered_at_startup(self):
        """Unwired, nothing would ever release a hold and no test would fail."""
        self.assertIn(cases.on_subject_case_decided, hooks._subject_case_decided)

    def test_registration_is_idempotent(self):
        """ready() can run more than once in a process; the hold must not be
        released twice or the override issued twice."""
        before = list(hooks._subject_case_decided)
        cases.register()
        cases.register()
        self.assertEqual(hooks._subject_case_decided, before)


class ReactionTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(phone_number='+254700000901')
        self.staff = StaffAccount.objects.create(
            email='edd-hook@wepl.app', full_name='Edd Hook', is_superuser=True)
        self.staff.set_password('S3cure-pass!')
        self.staff.save()

    def _held(self):
        return HeldMovement.objects.create(
            decision='HOLD', op_type='CONTRIBUTION', direction='PAYIN',
            amount=Decimal('500000.00'), subject_user=self.user,
            reason='Daily total exceeded')

    def _case(self, *, subject_type, subject_id):
        return service.open_subject_case(
            self.user, case_type=VerificationCase.CaseType.EDD_TRANSACTION,
            subject_type=subject_type, subject_id=subject_id,
            requested_items=['proof_of_funds'], actor_label='controls')

    def test_a_case_over_something_else_is_a_no_op(self):
        """Only a case opened over a HeldMovement has anything to release."""
        case = self._case(subject_type='SomeOtherThing', subject_id=42)
        case.state = VerificationCase.State.SUBMITTED
        case.save(update_fields=['state'])

        service.decide_subject_case(case, 'approve', actor_label='ops', notify=False)

        self.assertFalse(ControlOverride.objects.exists())

    def test_held_movement_for_ignores_a_case_over_something_else(self):
        case = self._case(subject_type='SomeOtherThing', subject_id=42)
        self.assertIsNone(cases.held_movement_for(case))

    def test_a_failing_reaction_rolls_the_decision_back(self):
        """The reaction is part of the decision, not a notification about it. If
        the hold cannot be released, the case must not read as decided."""
        held = self._held()
        case = self._case(subject_type='HeldMovement', subject_id=held.pk)
        case.state = VerificationCase.State.SUBMITTED
        case.save(update_fields=['state'])

        def boom(*, case, action, actor_label, reason):
            raise RuntimeError("controls is down")

        hooks._subject_case_decided.append(boom)
        self.addCleanup(hooks._subject_case_decided.remove, boom)

        with self.assertRaises(RuntimeError):
            service.decide_subject_case(case, 'approve', actor_label='ops',
                                        notify=False)

        case.refresh_from_db()
        held.refresh_from_db()
        self.assertEqual(case.state, VerificationCase.State.SUBMITTED)
        self.assertEqual(held.status, HeldMovement.Status.OPEN)
        self.assertFalse(ControlOverride.objects.exists())
