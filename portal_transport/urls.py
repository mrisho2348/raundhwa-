from django.urls import path
from . import views

app_name = 'transport'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    # TODO: add more URLs as features are built
]
