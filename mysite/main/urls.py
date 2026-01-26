from django.urls import path
from . import views

app_name = 'slow_moving'

urlpatterns = [
    path('', views.home, name='home'),                      #Slow moving cho hàng Raw 
    path('submit/', views.home_post, name='home_post'),     #Post cho hàng Raw

    path('FG/', views.FG, name='FG'),                       #Slow moving cho hàng FG
    path('FG/submit/', views.FG_post, name='FG_post'),      #Slow moving cho hàng FG
]