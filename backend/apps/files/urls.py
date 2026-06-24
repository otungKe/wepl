from django.urls import path

from .views import FileUploadView, FileDownloadView

urlpatterns = [
    path('', FileUploadView.as_view()),
    path('<uuid:file_id>/download/', FileDownloadView.as_view()),
]
