from django.urls import path
from .views import PrintLabelView, LocationScanView, DashboardView, BatchEntryView, MaterialPrintView, PrintSearchView, RollScanView, StoreView, DispatchView, RootRedirectView, UniversalScanView, LocationViewSet  # once you define it
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
router.register(r'locations', LocationViewSet, basename='location')
urlpatterns = [
    path('', RootRedirectView.as_view(), name='root'),
    path('dashboard/',  DashboardView.as_view(),       name='dashboard'),
    path('entry/', BatchEntryView.as_view(), name='material-entry'),
    path('print/',  PrintSearchView.as_view(),     name='material-print-search'),
    path('print/<uuid:roll_id>/', MaterialPrintView.as_view(), name='material-print'),
    path('print/<uuid:roll_id>/do/', PrintLabelView.as_view(), name='print-roll'),
    path('r/<uuid:roll_id>/', UniversalScanView.as_view(), name='universal-scan'),
    path('scan/qa/', RollScanView.as_view(),    name='roll-scan'),
    path('scan/store/', StoreView.as_view(),    name='store'),
    path('scan/dispatch/', DispatchView.as_view(), name='dispatch'),
    path('loc/<str:location_code>/', LocationScanView.as_view(), name='location-scan'),
    path('scan/view/', UniversalScanView.as_view(), name='scan-view'),
]
