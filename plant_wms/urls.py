from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from warehouse.views import (
    MaterialViewSet, BatchViewSet, CustomerViewSet,
    RollViewSet, LocationViewSet, TransactionViewSet, SignUpView
)
from django.conf import settings
from django.conf.urls.static import static

from django.http import JsonResponse

def debug_ssl(request):
    return JsonResponse({
        "is_secure": request.is_secure(),
        "scheme": request.scheme,
        "headers": {k: v for k, v in request.headers.items()},
    })


router = DefaultRouter()
router.register(r'materials',  MaterialViewSet)
router.register(r'batches',    BatchViewSet)
router.register(r'customers',  CustomerViewSet)
router.register(r'rolls',      RollViewSet)
router.register(r'locations',  LocationViewSet)
router.register(r'transactions', TransactionViewSet)

urlpatterns = [
    path("debug_ssl/", debug_ssl),

    path('admin/', admin.site.urls),
    # built‑in auth views: login, logout, password reset, etc.
    path('accounts/', include('django.contrib.auth.urls')),
    # your signup view (we’ll add shortly)
    path('accounts/signup/', SignUpView.as_view(), name='signup'),
    path('api/', include(router.urls)),
    path('', include('warehouse.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
