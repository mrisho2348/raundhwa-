"""school_project/urls.py"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls', namespace='accounts')),
    path('management/', include('portal_management.urls', namespace='management')),
    path('academic/', include('portal_academic.urls', namespace='academic')),
    path('administration/', include('portal_administration.urls', namespace='administration')),
    path('finance/', include('portal_finance.urls', namespace='finance')),
    path('transport/', include('portal_transport.urls', namespace='transport')),
    path('library/', include('portal_library.urls', namespace='library')),
    path('health/', include('portal_health.urls', namespace='health')),
    path('results/', include('results.urls', namespace='results')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
