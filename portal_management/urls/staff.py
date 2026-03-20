"""
portal_management/urls/staff.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Staff-related URL patterns.

Covers:
  - Staff CRUD
  - Role assignment and deactivation
  - Staff roles CRUD
  - Department assignment
  - Teaching assignment
  - Leave management
"""
from django.urls import path
from portal_management.views.staff import (
    StaffListView,
    StaffCreateView,
    StaffDetailView,
    StaffUpdateView,
    StaffRoleAssignView,
    StaffRoleDeactivateView,
    StaffRoleListView,
    StaffRoleCreateView,
    StaffRoleUpdateView,
    StaffDeptAssignView,
    StaffTeachingAssignView,
    StaffLeaveListView,
    StaffLeaveCreateView,
    StaffLeaveApproveView,
    StaffLeaveRejectView,
)
app_name = 'management'
urlpatterns = [
    # ── Staff CRUD ────────────────────────────────────────────────────────────
    path(
        'staff/',
        StaffListView.as_view(),
        name='staff_list',
    ),
    path(
        'staff/create/',
        StaffCreateView.as_view(),
        name='staff_create',
    ),
    path(
        'staff/<int:pk>/',
        StaffDetailView.as_view(),
        name='staff_detail',
    ),
    path(
        'staff/<int:pk>/edit/',
        StaffUpdateView.as_view(),
        name='staff_update',
    ),

    # ── Role assignment ───────────────────────────────────────────────────────
    path(
        'staff/<int:pk>/assign-role/',
        StaffRoleAssignView.as_view(),
        name='staff_assign_role',
    ),
    path(
        'staff/<int:pk>/deactivate-role/<int:assignment_pk>/',
        StaffRoleDeactivateView.as_view(),
        name='staff_deactivate_role',
    ),

    # ── Department assignment ─────────────────────────────────────────────────
    path(
        'staff/<int:pk>/assign-department/',
        StaffDeptAssignView.as_view(),
        name='staff_assign_dept',
    ),

    # ── Teaching assignment ───────────────────────────────────────────────────
    path(
        'staff/<int:pk>/assign-teaching/',
        StaffTeachingAssignView.as_view(),
        name='staff_assign_teaching',
    ),

    # ── Staff Roles CRUD ──────────────────────────────────────────────────────
    path(
        'staff/roles/',
        StaffRoleListView.as_view(),
        name='staff_role_list',
    ),
    path(
        'staff/roles/create/',
        StaffRoleCreateView.as_view(),
        name='staff_role_create',
    ),
    path(
        'staff/roles/<int:pk>/edit/',
        StaffRoleUpdateView.as_view(),
        name='staff_role_update',
    ),

    # ── Leave management ──────────────────────────────────────────────────────
    path(
        'staff/leave/',
        StaffLeaveListView.as_view(),
        name='staff_leave_list',
    ),
    path(
        'staff/leave/create/',
        StaffLeaveCreateView.as_view(),
        name='staff_leave_create',
    ),
    path(
        'staff/leave/<int:pk>/approve/',
        StaffLeaveApproveView.as_view(),
        name='staff_leave_approve',
    ),
    path(
        'staff/leave/<int:pk>/reject/',
        StaffLeaveRejectView.as_view(),
        name='staff_leave_reject',
    ),
]