from rest_framework import serializers

from .models import StoredFile
from .signing import make_token


class StoredFileSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = StoredFile
        fields = ('id', 'kind', 'original_name', 'content_type', 'size_bytes',
                  'scan_status', 'created_at', 'download_url')
        read_only_fields = fields

    def get_download_url(self, obj) -> str:
        return f"/api/files/{obj.id}/download/?token={make_token(obj.id)}"
