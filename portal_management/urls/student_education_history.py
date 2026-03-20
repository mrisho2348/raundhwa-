# portal_management/urls.py (add to existing file)

from django.urls import path


from portal_management.views import student_education_history as education_history_views

urlpatterns = [

    # Student Education History URLs
    path('students/education-history/', education_history_views.StudentEducationHistoryListView.as_view(), name='student_education_history_list'),    
    path('students/education-history/create/', education_history_views.StudentEducationHistoryCreateView.as_view(), name='student_education_history_create'),    
    path('students/education-history/create/<int:student_id>/', education_history_views.StudentEducationHistoryCreateView.as_view(), name='student_education_history_create_for_student'),    
    path('students/education-history/<int:pk>/', education_history_views.StudentEducationHistoryDetailView.as_view(), name='student_education_history_detail'),    
    path('students/education-history/<int:pk>/update/', education_history_views.StudentEducationHistoryUpdateView.as_view(), name='student_education_history_update'),    
    path('students/education-history/<int:pk>/delete/', education_history_views.StudentEducationHistoryDeleteView.as_view(),name='student_education_history_delete'),    
    
]