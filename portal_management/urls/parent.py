# Add to portal_management/urls.py

from django.urls import path

from portal_management.views.parent import *



urlpatterns = [
    # ... existing URLs ...
    
    # Parent URLs
    path('parents/', ParentListView.as_view(), name='parent_list'),
    path('parents/create/', ParentCreateView.as_view(), name='parent_create'),
    path('parents/<int:pk>/', ParentDetailView.as_view(), name='parent_detail'),
    path('parents/<int:pk>/update/', ParentUpdateView.as_view(), name='parent_update'),
    path('parents/<int:pk>/delete/', ParentDeleteView.as_view(), name='parent_delete'),
    path('parents/link/', StudentParentLinkView.as_view(), name='parent_link'),
    path('parents/<int:parent_pk>/link/', StudentParentLinkView.as_view(), name='parent_link_from_parent'),
    path('students/<int:student_pk>/link-parent/', StudentParentLinkView.as_view(), name='student_link_parent'),
    path('parent-relationships/<int:pk>/unlink/', StudentParentUnlinkView.as_view(), name='parent_unlink'),
    path('api/parents/<int:pk>/details/', GetParentDetailsView.as_view(), name='api_parent_details'),
]