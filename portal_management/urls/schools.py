# portal_management/urls/schools.py

from django.urls import path
from portal_management.views import schools

urlpatterns = [
    # School CRUD
    path('schools/', schools.SchoolListView.as_view(), name='school_list'),    
    path('schools/create/', schools.SchoolCreateView.as_view(), name='school_create'),    
    path('schools/<int:pk>/', schools.SchoolDetailView.as_view(), name='school_detail'),    
    path('schools/<int:pk>/update/', schools.SchoolUpdateView.as_view(), name='school_update'),    
    path('schools/<int:pk>/delete/', schools.SchoolDeleteView.as_view(), name='school_delete'),    
    path('schools/<int:pk>/details/', schools.GetSchoolDetailsView.as_view(), name='get_school_details'),    
    # AJAX endpoints
    path('ajax/search-schools/', schools.SearchSchoolsForSelectView.as_view(), name='search_schools'),
]