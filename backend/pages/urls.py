from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('', views.home, name='home'),
    path('travel/', views.travel, name='travel'),
    path('registry/', views.registry, name='registry'),
]
