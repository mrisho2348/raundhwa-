# portal_management/urls/staff.py

from django.urls import path
from portal_management.views.staff_leave_views import StaffLeaveApproveView, StaffLeaveCalendarView, StaffLeaveCancelView, StaffLeaveCreateView, StaffLeaveDeleteView, StaffLeaveDetailView, StaffLeaveListView, StaffLeaveRejectView, StaffLeaveSearchView, StaffLeaveUpdateView
from portal_management.views.staff_views import (
    ClassTeacherAssignmentCreateView,
    ClassTeacherAssignmentDeleteView,
    ClassTeacherAssignmentDetailView,
    ClassTeacherAssignmentEndView,
    ClassTeacherAssignmentListView,
    ClassTeacherAssignmentLoadView,
    ClassTeacherAssignmentSearchView,
    ClassTeacherAssignmentUpdateView,
    StaffDepartmentAssignmentCreateView,
    StaffDepartmentAssignmentDeleteView,
    StaffDepartmentAssignmentDetailView,
    StaffDepartmentAssignmentEndView,
    StaffDepartmentAssignmentListView,
    StaffDepartmentAssignmentSearchView,
    StaffDepartmentAssignmentUpdateView,
    StaffListView,
    StaffCreateView,
    StaffDetailView,
    StaffRoleAssignmentCreateView,
    StaffRoleAssignmentDeleteView,
    StaffRoleAssignmentDetailView,
    StaffRoleAssignmentEndView,
    StaffRoleAssignmentListView,
    StaffRoleAssignmentSearchView,
    StaffRoleAssignmentUpdateView,
    StaffRoleCheckDependenciesView,
    StaffRoleCreateView,
    StaffRoleDeleteView,
    StaffRoleDetailView,
    StaffRoleListView,
    StaffRoleSearchView,
    StaffRoleUpdateView,
    StaffTeachingAssignmentCreateView,
    StaffTeachingAssignmentDeleteView,
    StaffTeachingAssignmentDetailView,
    StaffTeachingAssignmentListView,
    StaffTeachingAssignmentLoadView,
    StaffTeachingAssignmentSearchView,
    StaffTeachingAssignmentUpdateView,
    StaffUpdateView,
    StaffDeleteView,
    StaffCheckDependenciesView,
    StaffSearchView,
)

urlpatterns = [
    # Main CRUD URLs
    path('staff/', StaffListView.as_view(), name='staff_list'),
    path('staff/create/', StaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff_detail'),
    path('staff/<int:pk>/update/', StaffUpdateView.as_view(), name='staff_update'),
    path('staff/<int:pk>/delete/', StaffDeleteView.as_view(), name='staff_delete'),
    
    # AJAX helper URLs
    path('staff/<int:pk>/check-dependencies/', StaffCheckDependenciesView.as_view(), name='staff_check_dependencies'),
    path('staff/search/', StaffSearchView.as_view(), name='staff_search'),

    path('staff-roles/', StaffRoleListView.as_view(), name='staff_role_list'),
    path('staff-roles/create/', StaffRoleCreateView.as_view(), name='staff_role_create'),
    path('staff-roles/<int:pk>/', StaffRoleDetailView.as_view(), name='staff_role_detail'),
    path('staff-roles/<int:pk>/update/', StaffRoleUpdateView.as_view(), name='staff_role_update'),
    path('staff-roles/<int:pk>/delete/', StaffRoleDeleteView.as_view(), name='staff_role_delete'),
    
    # AJAX helper URLs
    path('staff-roles/<int:pk>/check-dependencies/', StaffRoleCheckDependenciesView.as_view(), name='staff_role_check_dependencies'),
    path('staff-roles/search/', StaffRoleSearchView.as_view(), name='staff_role_search'),

    # Main CRUD URLs
    path('role-assignments/', StaffRoleAssignmentListView.as_view(), name='staff_role_assignment_list'),
    path('role-assignments/create/', StaffRoleAssignmentCreateView.as_view(), name='staff_role_assignment_create'),
    path('role-assignments/<int:pk>/', StaffRoleAssignmentDetailView.as_view(), name='staff_role_assignment_detail'),
    path('role-assignments/<int:pk>/update/', StaffRoleAssignmentUpdateView.as_view(), name='staff_role_assignment_update'),
    path('role-assignments/<int:pk>/delete/', StaffRoleAssignmentDeleteView.as_view(), name='staff_role_assignment_delete'),
    path('role-assignments/<int:pk>/end/', StaffRoleAssignmentEndView.as_view(), name='staff_role_assignment_end'),
    
    # AJAX helper URLs
    path('role-assignments/search/', StaffRoleAssignmentSearchView.as_view(), name='staff_role_assignment_search'),

        # Main CRUD URLs
    path('department-assignments/', StaffDepartmentAssignmentListView.as_view(), name='staff_department_assignment_list'),
    path('department-assignments/create/', StaffDepartmentAssignmentCreateView.as_view(), name='staff_department_assignment_create'),
    path('department-assignments/<int:pk>/', StaffDepartmentAssignmentDetailView.as_view(), name='staff_department_assignment_detail'),
    path('department-assignments/<int:pk>/update/', StaffDepartmentAssignmentUpdateView.as_view(), name='staff_department_assignment_update'),
    path('department-assignments/<int:pk>/delete/', StaffDepartmentAssignmentDeleteView.as_view(), name='staff_department_assignment_delete'),
    path('department-assignments/<int:pk>/end/', StaffDepartmentAssignmentEndView.as_view(), name='staff_department_assignment_end'),
    
    # AJAX helper URLs
    path('department-assignments/search/', StaffDepartmentAssignmentSearchView.as_view(), name='staff_department_assignment_search'),


     # Main CRUD URLs
    path('teaching-assignments/', StaffTeachingAssignmentListView.as_view(), name='staff_teaching_assignment_list'),
    path('teaching-assignments/create/', StaffTeachingAssignmentCreateView.as_view(), name='staff_teaching_assignment_create'),
    path('teaching-assignments/<int:pk>/', StaffTeachingAssignmentDetailView.as_view(), name='staff_teaching_assignment_detail'),
    path('teaching-assignments/<int:pk>/update/', StaffTeachingAssignmentUpdateView.as_view(), name='staff_teaching_assignment_update'),
    path('teaching-assignments/<int:pk>/delete/', StaffTeachingAssignmentDeleteView.as_view(), name='staff_teaching_assignment_delete'),
    
    # AJAX helper URLs
    path('teaching-assignments/search/', StaffTeachingAssignmentSearchView.as_view(), name='staff_teaching_assignment_search'),
    
    # Special views
    path('teaching-assignments/load/', StaffTeachingAssignmentLoadView.as_view(), name='staff_teaching_assignment_load'),

         # Main CRUD URLs
    path('class-teacher-assignments/', ClassTeacherAssignmentListView.as_view(), name='class_teacher_assignment_list'),
    path('class-teacher-assignments/create/', ClassTeacherAssignmentCreateView.as_view(), name='class_teacher_assignment_create'),
    path('class-teacher-assignments/<int:pk>/', ClassTeacherAssignmentDetailView.as_view(), name='class_teacher_assignment_detail'),
    path('class-teacher-assignments/<int:pk>/update/', ClassTeacherAssignmentUpdateView.as_view(), name='class_teacher_assignment_update'),
    path('class-teacher-assignments/<int:pk>/delete/', ClassTeacherAssignmentDeleteView.as_view(), name='class_teacher_assignment_delete'),
    path('class-teacher-assignments/<int:pk>/end/', ClassTeacherAssignmentEndView.as_view(), name='class_teacher_assignment_end'),
    
    # AJAX helper URLs
    path('class-teacher-assignments/search/', ClassTeacherAssignmentSearchView.as_view(), name='class_teacher_assignment_search'),
    
    # Special views
    path('class-teacher-assignments/load/', ClassTeacherAssignmentLoadView.as_view(), name='class_teacher_assignment_load'),

     # Main CRUD URLs
    path('leaves/', StaffLeaveListView.as_view(), name='staff_leave_list'),
    path('leaves/create/', StaffLeaveCreateView.as_view(), name='staff_leave_create'),
    path('leaves/<int:pk>/', StaffLeaveDetailView.as_view(), name='staff_leave_detail'),
    path('leaves/<int:pk>/update/', StaffLeaveUpdateView.as_view(), name='staff_leave_update'),
    path('leaves/<int:pk>/delete/', StaffLeaveDeleteView.as_view(), name='staff_leave_delete'),
    
    # Approval URLs
    path('leaves/<int:pk>/approve/', StaffLeaveApproveView.as_view(), name='staff_leave_approve'),
    path('leaves/<int:pk>/reject/', StaffLeaveRejectView.as_view(), name='staff_leave_reject'),
    path('leaves/<int:pk>/cancel/', StaffLeaveCancelView.as_view(), name='staff_leave_cancel'),
    
    # AJAX helper URLs
    path('leaves/search/', StaffLeaveSearchView.as_view(), name='staff_leave_search'),
    
    # Special views
    path('leaves/calendar/', StaffLeaveCalendarView.as_view(), name='staff_leave_calendar'),

]