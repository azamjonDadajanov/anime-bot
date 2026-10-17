from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    # Django's own admin lives under /django-admin/, not /admin/. The React
    # administrator panel is a SPA served at /admin (see frontend/nginx.conf and
    # App.jsx), so keeping Django on /admin/ would shadow every panel route:
    # a refresh or a direct link to /admin/game-ratings reached Django's login
    # page instead of the panel.
    path('django-admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/auth/', include('users.urls')),
    path('api/', include('movies.urls')),
    path('api/game/', include('games.urls')),
    path('api/admin/', include('adminpanel.urls')),
] + static(settings.MEDIA_URL,
            document_root=settings.MEDIA_ROOT)
