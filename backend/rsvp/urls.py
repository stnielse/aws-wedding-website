from django.urls import path

from . import views

app_name = 'rsvp'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('<str:code>/', views.party, name='party'),
    path('<str:code>/submit/', views.submit, name='submit'),
]
