# portal_management/urls/suspensions.py

from django.urls import path
from portal_management.views import suspensions

urlpatterns = [
    # Suspension CRUD
    path('suspensions/',suspensions.StudentSuspensionListView.as_view(), name='suspension_list'),    
    path('suspensions/create/', suspensions.StudentSuspensionCreateView.as_view(), name='suspension_create'),    
    path('suspensions/create/<int:student_id>/', suspensions.StudentSuspensionCreateView.as_view(), name='suspension_create_for_student'),    
    path('suspensions/<int:pk>/', suspensions.StudentSuspensionDetailView.as_view(), name='suspension_detail'),    
    path('suspensions/<int:pk>/update/', suspensions.StudentSuspensionUpdateView.as_view(), name='suspension_update'),    
    path('suspensions/<int:pk>/delete/', suspensions.StudentSuspensionDeleteView.as_view(), name='suspension_delete'),    
    path('suspensions/<int:pk>/lift/', suspensions.StudentSuspensionLiftView.as_view(),name='suspension_lift'),    
    # AJAX endpoints
  
    path('ajax/get-student-suspension-info/', suspensions.GetStudentSuspensionInfoView.as_view(), name='get_student_suspension_info'),
]