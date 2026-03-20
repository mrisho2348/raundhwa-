"""
portal_management/urls/reports.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reporting and audit URL patterns.

Covers:
  - Audit log
  - Online users / session history
  - Student result reports
  - Session result export
"""
from django.urls import path
from portal_management.views.reports import (
    AuditLogView,
    ExportSessionReportView,
    ExportStudentReportView,
    OnlineUsersView,
    StudentResultReportView,
)
app_name = 'management'
urlpatterns = [
    # ── Audit Log ─────────────────────────────────────────────────────────────
    path(
        'reports/audit/',
        AuditLogView.as_view(),
        name='audit_log',
    ),

    # ── Online Users ──────────────────────────────────────────────────────────
    path(
        'reports/online/',
        OnlineUsersView.as_view(),
        name='online_users',
    ),

    # ── Result Reports ────────────────────────────────────────────────────────
    path(
        'reports/results/',
        StudentResultReportView.as_view(),
        name='result_reports',
    ),
    path(
        'reports/results/student/<int:student_pk>/export/',
        ExportStudentReportView.as_view(),
        name='export_student_report',
    ),
    path(
        'reports/results/session/<int:session_pk>/export/',
        ExportSessionReportView.as_view(),
        name='export_session_report',
    ),
]