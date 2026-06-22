from django.contrib import admin

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
