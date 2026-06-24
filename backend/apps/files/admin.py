from django.contrib import admin

from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'kind', 'original_name', 'content_type',
                     'size_bytes', 'scan_status', 'owner', 'deleted_at')
    list_filter   = ('kind', 'scan_status', 'created_at')
    search_fields = ('original_name', 'checksum_sha256', 'id')
    date_hierarchy = 'created_at'
    readonly_fields = ('id', 'checksum_sha256', 'created_at')
