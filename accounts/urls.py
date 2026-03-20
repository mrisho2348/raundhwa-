from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('redirect/', views.RedirectView.as_view(), name='redirect'),
    path('change-password/', views.change_password, name='change_password'),
    path('student/', views.student_portal, name='student_portal'),
    path('no-permission/', views.no_permission, name='no_permission'),
    path('no-portal/', views.no_portal, name='no_portal'),
]
