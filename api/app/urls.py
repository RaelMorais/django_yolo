from django.urls import path
from .views import *

urlpatterns = [
     path(
        'people-detection/',                 
        PeopleDetectionView.as_view(),
        name='people_detection'
    ),
    path('esp32/status/', ESP32StatusProxyView.as_view(), name='esp32_status'),

]
