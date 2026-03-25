# portal_management/urls/school_profile_urls.py

from django.urls import path
from portal_management.views.school_profile_views import (
    SchoolProfileListView,
    SchoolProfileCreateView,
    SchoolProfileDetailView,
    SchoolProfileUpdateView,
    SchoolProfileDeleteView,
    SchoolProfileToggleActiveView,
    SchoolProfileSetDefaultView,
)

urlpatterns = [
    path('school-profiles/', SchoolProfileListView.as_view(),name='school_profile_list'),    
    path('school-profiles/create/',SchoolProfileCreateView.as_view(),name='school_profile_create'),    
    path('school-profiles/<int:pk>/', SchoolProfileDetailView.as_view(),name='school_profile_detail'),    
    path('school-profiles/<int:pk>/edit/',SchoolProfileUpdateView.as_view(),name='school_profile_edit'),    
    path('school-profiles/<int:pk>/delete/',SchoolProfileDeleteView.as_view(),name='school_profile_delete'),    
    path('school-profiles/<int:pk>/toggle-active/',SchoolProfileToggleActiveView.as_view(),name='school_profile_toggle_active'),    
    path('school-profiles/<int:pk>/set-default/',SchoolProfileSetDefaultView.as_view(),name='school_profile_set_default'),
]