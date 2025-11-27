from django.urls import path
from .views import PeopleDetectionView, ESP32StatusProxyView

urlpatterns = [
    path('people-detection/', PeopleDetectionView.as_view(), name='people_detection'),
    path('status/', ESP32StatusProxyView.as_view(), name='esp32_status'),
]
