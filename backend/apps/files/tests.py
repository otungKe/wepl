"""Files pipeline tests (ADR-0018): validation, signed download, scan, retention."""
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

from .models import StoredFile
from .services import FileService
from .signing import make_token, read_token
from .tasks import purge_expired_files, scan_file

User = get_user_model()
_MEDIA = tempfile.mkdtemp(prefix="wepl-test-media-")


def make_user(phone="254700000001"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def png(name="a.png", size=1024, content_type="image/png"):
    return SimpleUploadedFile(name, b"x" * size, content_type=content_type)


def active_client(user):
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    c = APIClient()
    c.force_authenticate(user=user, token=token)
    return c


@override_settings(MEDIA_ROOT=_MEDIA)
class FileServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_save_valid_image(self):
        f = FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR, uploaded_file=png())
        self.assertEqual(f.kind, "avatar")
        self.assertEqual(f.size_bytes, 1024)
        self.assertEqual(len(f.checksum_sha256), 64)
        self.assertTrue(f.file.name)

    def test_reject_bad_content_type(self):
        with self.assertRaises(ValidationError):
            FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR,
                             uploaded_file=png(content_type="application/x-msdownload"))

    def test_reject_oversize(self):
        with self.assertRaises(ValidationError):
            FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR,
                             uploaded_file=png(size=6 * 1024 * 1024))

    def test_reject_unknown_kind(self):
        with self.assertRaises(ValidationError):
            FileService.save(owner=self.user, kind="malware", uploaded_file=png())

    def test_pdf_allowed_for_kyc_not_avatar(self):
        pdf = SimpleUploadedFile("id.pdf", b"%PDF-1.4 xxx", content_type="application/pdf")
        FileService.save(owner=self.user, kind=StoredFile.Kind.KYC_DOC, uploaded_file=pdf)
        with self.assertRaises(ValidationError):
            FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR,
                             uploaded_file=SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf"))


class SigningTests(TestCase):
    def test_round_trip(self):
        t = make_token("abc")
        self.assertEqual(read_token(t), "abc")

    def test_tampered_rejected(self):
        self.assertIsNone(read_token(make_token("abc") + "x"))

    def test_expired_rejected(self):
        self.assertIsNone(read_token(make_token("abc"), max_age=-1))


@override_settings(MEDIA_ROOT=_MEDIA)
class DownloadViewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.f = FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR, uploaded_file=png())

    def test_valid_token_serves_file(self):
        r = self.client.get(f"/api/files/{self.f.id}/download/?token={make_token(self.f.id)}")
        self.assertEqual(r.status_code, 200)

    def test_missing_token_forbidden(self):
        self.assertEqual(self.client.get(f"/api/files/{self.f.id}/download/").status_code, 403)

    def test_wrong_token_forbidden(self):
        other = make_token("00000000-0000-0000-0000-000000000000")
        self.assertEqual(
            self.client.get(f"/api/files/{self.f.id}/download/?token={other}").status_code, 403)

    def test_infected_not_served(self):
        StoredFile.objects.filter(pk=self.f.pk).update(scan_status=StoredFile.ScanStatus.INFECTED)
        r = self.client.get(f"/api/files/{self.f.id}/download/?token={make_token(self.f.id)}")
        self.assertEqual(r.status_code, 404)

    def test_soft_deleted_not_served(self):
        FileService.soft_delete(self.f)
        r = self.client.get(f"/api/files/{self.f.id}/download/?token={make_token(self.f.id)}")
        self.assertEqual(r.status_code, 404)


@override_settings(MEDIA_ROOT=_MEDIA)
class UploadApiTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_upload_returns_signed_url(self):
        r = active_client(self.user).post(
            "/api/files/", {"kind": "avatar", "file": png()}, format="multipart")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertIn("/download/?token=", body["download_url"])

    def test_upload_rejects_bad_type(self):
        r = active_client(self.user).post(
            "/api/files/", {"kind": "avatar", "file": png(content_type="text/html")},
            format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_upload_requires_auth(self):
        r = APIClient().post("/api/files/", {"kind": "avatar", "file": png()}, format="multipart")
        self.assertIn(r.status_code, (401, 403))


@override_settings(MEDIA_ROOT=_MEDIA)
class ScanAndRetentionTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_scan_marks_skipped_without_scanner(self):
        f = FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR, uploaded_file=png())
        scan_file(str(f.id))
        f.refresh_from_db()
        self.assertEqual(f.scan_status, StoredFile.ScanStatus.SKIPPED)

    def test_purge_removes_old_soft_deleted(self):
        f = FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR, uploaded_file=png())
        StoredFile.objects.filter(pk=f.pk).update(deleted_at=timezone.now() - timedelta(days=40))
        self.assertEqual(purge_expired_files(retention_days=30), 1)
        self.assertFalse(StoredFile.objects.filter(pk=f.pk).exists())

    def test_purge_keeps_recent_soft_deleted(self):
        f = FileService.save(owner=self.user, kind=StoredFile.Kind.AVATAR, uploaded_file=png())
        FileService.soft_delete(f)
        self.assertEqual(purge_expired_files(retention_days=30), 0)
        self.assertTrue(StoredFile.objects.filter(pk=f.pk).exists())
