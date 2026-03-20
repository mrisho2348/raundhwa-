"""
portal_management/views/dashboard.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Management portal main dashboard view.
"""
from django.views.generic import TemplateView

from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, AuditLog, ClassLevel,
    Staff, StaffSession, Student, Subject,
)


class DashboardView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_students'] = Student.objects.filter(status='active').count()
        ctx['total_staff']    = Staff.objects.count()
        ctx['total_classes']  = ClassLevel.objects.count()
        ctx['total_subjects'] = Subject.objects.count()
        ctx['online_users']   = StaffSession.objects.filter(is_online=True).count()
        ctx['recent_audit']   = AuditLog.objects.select_related(
            'user', 'content_type'
        ).order_by('-timestamp')[:10]
        ctx['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        ctx['active_term'] = None
        if ctx['active_year']:
            ctx['active_term'] = (
                ctx['active_year'].terms.filter(is_active=True).first()
            )
        return ctx