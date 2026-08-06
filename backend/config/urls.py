from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from api.views import IndexView

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]

# Servir archivos estáticos del admin y media en producción (gunicorn)
if not settings.DEBUG:
    from django.views.static import serve as static_serve

    urlpatterns += [
        path("static/<path:path>", static_serve, kwargs={"document_root": settings.STATIC_ROOT}),
        path("media/<path:path>", static_serve, kwargs={"document_root": settings.MEDIA_ROOT}),
    ]
else:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
