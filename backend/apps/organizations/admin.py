from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display  = ('name', 'archetype', 'tenant', 'uid', 'created_at')
    list_filter   = ('archetype', 'created_at')
    search_fields = ('name', 'uid')
    readonly_fields = ('uid', 'created_at')
