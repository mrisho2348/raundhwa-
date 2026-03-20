"""
portal_management/urls/dashboard.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dashboard URL patterns.
"""
from django.urls import path
from portal_management.views.dashboard import DashboardView
app_name = 'management'
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
]