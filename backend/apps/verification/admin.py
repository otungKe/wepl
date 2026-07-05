"""Read-only Django-admin views over the case ledger. Cases advance only
through apps.verification.service — never by editing rows here."""
from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import CaseDocument, CaseEvent, VerificationCase


class _ReadOnly(UnfoldModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VerificationCase)
class VerificationCaseAdmin(_ReadOnly):
    list_display  = ('id', 'user', 'case_type', 'state', 'event_seq', 'opened_at', 'closed_at')
    list_filter   = ('state', 'case_type')
    search_fields = ('user__phone_number', 'kyc__id_number')
    ordering      = ('-opened_at',)


@admin.register(CaseEvent)
class CaseEventAdmin(_ReadOnly):
    list_display  = ('case', 'seq', 'event_type', 'actor_kind', 'actor_label', 'created_at')
    list_filter   = ('event_type', 'actor_kind')
    search_fields = ('case__user__phone_number', 'actor_label')
    ordering      = ('-created_at',)


@admin.register(CaseDocument)
class CaseDocumentAdmin(_ReadOnly):
    list_display  = ('case', 'doc_type', 'version', 'source', 'size_bytes', 'created_at')
    list_filter   = ('doc_type', 'source')
    search_fields = ('case__user__phone_number',)
    ordering      = ('-created_at',)
