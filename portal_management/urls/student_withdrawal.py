# Add to portal_management/urls/student_withdrawal.py

from django.urls import path
from portal_management.views import student_withdrawal as withdrawal_views

urlpatterns = [
    # ... existing URLs ...
    
    # Student Withdrawal URLs
    path('withdrawals/', withdrawal_views.StudentWithdrawalListView.as_view(), name='student_withdrawal_list'),
    path('withdrawals/create/', withdrawal_views.StudentWithdrawalCreateView.as_view(), name='student_withdrawal_create'),
    path('withdrawals/create/<int:student_id>/', withdrawal_views.StudentWithdrawalCreateView.as_view(), name='student_withdrawal_create_for_student'),
    path('withdrawals/<int:pk>/', withdrawal_views.StudentWithdrawalDetailView.as_view(), name='student_withdrawal_detail'),
    path('withdrawals/<int:pk>/update/', withdrawal_views.StudentWithdrawalUpdateView.as_view(), name='student_withdrawal_update'),
    path('withdrawals/<int:pk>/delete/', withdrawal_views.StudentWithdrawalDeleteView.as_view(), name='student_withdrawal_delete'),
    
    # AJAX endpoints
    path('ajax/get-student-withdrawal-info/', withdrawal_views.GetStudentWithdrawalInfoView.as_view(), name='get_student_withdrawal_info'),
]