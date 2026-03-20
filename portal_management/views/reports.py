"""
portal_management/views/reports.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reporting and audit views for the Management portal.

Covers:
  - Audit log with filtering and pagination
  - Online users and session history
  - Student result reports (Excel export)
  - Session result reports (Excel export)
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from core.mixins import ManagementRequiredMixin
from core.models import AuditLog, ExamSession, Staff, StaffSession, Student


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLogView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/reports/audit_log.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = AuditLog.objects.select_related(
            'user', 'content_type'
        ).order_by('-timestamp')

        # Filters from GET params
        user_id   = self.request.GET.get('user')
        action    = self.request.GET.get('action')
        model     = self.request.GET.get('model')
        date_from = self.request.GET.get('date_from')
        date_to   = self.request.GET.get('date_to')

        if user_id:
            qs = qs.filter(user_id=user_id)
        if action:
            qs = qs.filter(action=action)
        if model:
            qs = qs.filter(content_type__model__icontains=model)
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        paginator = Paginator(qs, 50)
        ctx['logs']           = paginator.get_page(self.request.GET.get('page', 1))
        ctx['action_choices'] = AuditLog.ACTION_CHOICES
        ctx['total_count']    = qs.count()
        return ctx


# ── Online Users ──────────────────────────────────────────────────────────────

class OnlineUsersView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/reports/online_users.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['online_sessions'] = StaffSession.objects.filter(
            is_online=True
        ).select_related('user').order_by('-logged_in_at')
        ctx['recent_sessions'] = StaffSession.objects.select_related(
            'user'
        ).order_by('-logged_in_at')[:100]
        ctx['total_online'] = ctx['online_sessions'].count()
        return ctx


# ── Result Reports ────────────────────────────────────────────────────────────

class StudentResultReportView(ManagementRequiredMixin, TemplateView):
    """
    Overview page showing all students and their result summaries.
    Allows exporting individual student reports to Excel.
    """
    template_name = 'portal_management/reports/student_results.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sessions'] = ExamSession.objects.select_related(
            'class_level', 'academic_year', 'term'
        ).filter(status='published').order_by('-exam_date')
        return ctx


class ExportStudentReportView(ManagementRequiredMixin, TemplateView):
    """Export a single student's results across sessions as Excel."""

    def get(self, request, student_pk):
        from core.models import StudentSubjectResult
        from results.utils import export_student_report

        student = get_object_or_404(Student, pk=student_pk)
        session_ids = StudentSubjectResult.objects.filter(
            student=student
        ).values_list('exam_session_id', flat=True).distinct()
        sessions = ExamSession.objects.filter(
            pk__in=session_ids
        ).order_by('exam_date')

        wb = export_student_report(student, sessions)
        response = HttpResponse(
            content_type=(
                'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet'
            )
        )
        filename = f"results_{student.registration_number or student_pk}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response


class ExportSessionReportView(ManagementRequiredMixin, TemplateView):
    """Export all student results for one exam session as Excel."""

    def get(self, request, session_pk):
        from results.utils import export_session_report

        session = get_object_or_404(ExamSession, pk=session_pk)
        wb = export_session_report(session)
        response = HttpResponse(
            content_type=(
                'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet'
            )
        )
        safe_name = session.name[:30].replace(' ', '_')
        filename = f"session_{session_pk}_{safe_name}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response