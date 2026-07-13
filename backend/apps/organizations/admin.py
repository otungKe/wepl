from django.contrib import admin

from .models import Organization, Program


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display  = ('name', 'archetype', 'tenant', 'uid', 'created_at')
    list_filter   = ('archetype', 'created_at')
    search_fields = ('name', 'uid')
    readonly_fields = ('uid', 'created_at')


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display  = ('name', 'program_type', 'organization', 'tenant', 'uid', 'created_at')
    list_filter   = ('program_type', 'created_at')
    search_fields = ('name', 'uid', 'organization__name')
    readonly_fields = ('uid', 'created_at')
