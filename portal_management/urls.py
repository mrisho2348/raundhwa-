"""
portal_management/urls.py
━━━━━━━━━━━━━━━━━━━━━━━━━
Root URL configuration for the Management portal.
"""
from .urls import all_urlpatterns

app_name = 'management'

# all_urlpatterns is already a list
urlpatterns = all_urlpatterns