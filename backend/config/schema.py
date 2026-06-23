"""drf-spectacular preprocessing hooks + extensions (P1 #6).

Imported at schema-generation time via SPECTACULAR_SETTINGS['PREPROCESSING_HOOKS'],
which also registers the authentication extension below.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class TenantJWTScheme(OpenApiAuthenticationExtension):
    """Teach the schema that our (subclassed) JWT auth is HTTP bearer JWT, so the
    generated spec advertises the auth scheme instead of warning about it."""
    target_class = 'apps.tenants.auth.TenantJWTAuthentication'
    name = 'jwtAuth'

    def get_security_definition(self, auto_schema):
        return {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'}


def only_versioned_paths(endpoints, **kwargs):
    """Document the ``/api/v1/`` space only.

    The API map is mounted twice (``/api/`` for legacy mobile binaries and
    ``/api/v1/`` for new clients). Without filtering, every operation would appear
    twice in the schema. Keep the versioned paths so the generated schema /
    typed clients target the stable, versioned space.
    """
    return [
        (path, path_regex, method, callback)
        for (path, path_regex, method, callback) in endpoints
        if path.startswith("/api/v1/")
    ]
