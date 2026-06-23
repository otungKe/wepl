"""API-convention tests (P1 #6): OpenAPI schema + /api/v1 versioning."""
import yaml
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

User = get_user_model()


def active_client(user):
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    c = APIClient()
    c.force_authenticate(user=user, token=token)
    return c


class OpenAPISchemaTests(TestCase):

    def test_schema_endpoint_serves_valid_openapi(self):
        r = self.client.get("/api/schema/")
        self.assertEqual(r.status_code, 200)
        doc = yaml.safe_load(r.content)
        self.assertIn("openapi", doc)
        self.assertEqual(doc["info"]["title"], "WEPL API")

    def test_swagger_ui_loads(self):
        self.assertEqual(self.client.get("/api/schema/swagger-ui/").status_code, 200)

    def test_schema_documents_versioned_paths_only(self):
        doc = yaml.safe_load(self.client.get("/api/schema/").content)
        paths = doc["paths"]
        self.assertTrue(any(p.startswith("/api/v1/") for p in paths))
        # the legacy unversioned prefix is deliberately not documented (dedupe)
        self.assertFalse(any(p.startswith("/api/users/") for p in paths))
        self.assertFalse(any(p.startswith("/api/communities/") for p in paths))

    def test_schema_advertises_bearer_jwt_auth(self):
        doc = yaml.safe_load(self.client.get("/api/schema/").content)
        schemes = doc.get("components", {}).get("securitySchemes", {})
        self.assertIn("jwtAuth", schemes)
        self.assertEqual(schemes["jwtAuth"]["scheme"], "bearer")


class APIVersioningTests(TestCase):
    """The same map is served at /api/ (legacy) and /api/v1/ (versioned)."""

    def setUp(self):
        self.user = User.objects.create(phone_number="254700000001")
        self.user.set_pin("123456")

    def test_versioned_route_works(self):
        r = active_client(self.user).get("/api/v1/users/protected/")
        self.assertEqual(r.status_code, 200)

    def test_legacy_route_still_works(self):
        r = active_client(self.user).get("/api/users/protected/")
        self.assertEqual(r.status_code, 200)

    def test_unknown_route_is_404_under_both(self):
        c = active_client(self.user)
        self.assertEqual(c.get("/api/v1/users/does-not-exist/").status_code, 404)
        self.assertEqual(c.get("/api/users/does-not-exist/").status_code, 404)
