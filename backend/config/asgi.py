import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()


from channels.routing import ProtocolTypeRouter, URLRouter

from apps.conversations.routing import websocket_urlpatterns
from apps.conversations.jwt_middleware import JWTAuthMiddleware


application = ProtocolTypeRouter({
    "http": django_asgi_app,

    "websocket": JWTAuthMiddleware(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})
