from django.apps import AppConfig


class ContributionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contributions'

    def ready(self):
        # Register the contribution authorization policy (ADR-0009).
        from . import policies  # noqa: F401
        # Register the inline settlement consumer (ADR-0028/0029 Stage 2).
        from . import settlement_consumer
        settlement_consumer.register()
        # Register each context's settlement reactions (ADR-0030 Slice B).
        from . import settlement_targets
        settlement_targets.register()
        # Hand the ledger the fund → tenant lookup it must not import (P6-03).
        from . import fund_tenant
        fund_tenant.register()
        # Hand the M-Pesa rail the settlement decisions it must not import (ADR-0033).
        from . import settlement
        settlement.register()
        # Answer for group money when an account closes or is exported (step 8).
        from . import lifecycle
        lifecycle.register()
