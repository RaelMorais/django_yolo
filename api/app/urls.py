from django.urls import path
from . import views

urlpatterns = [
    # Environment status
    path('environment/', views.EnvironmentView.as_view(), name='environment'),

    # LEDs
    path('led_branco/', views.PresenceLEDView.as_view(), name='led_branco'),
    path('led_azul/', views.BlueLEDView.as_view(), name='led_azul'),
    path('led_rfid/', views.GreenRedLEDView.as_view(), name='led_rfid'),

    # RFID
    path('rfid_validation/', views.RFIDValidationView.as_view(), name='rfid_validation'),
    path('last_rfid/', views.LastRFIDView.as_view(), name='last_rfid'),

    # Users
    path('users/', views.UsersView.as_view(), name='users'),
]
