"""
core/mixins.py
══════════════
Portal access mixins. Each mixin guards a portal by checking
whether the logged-in user belongs to any of the groups
configured in settings for that portal category.

Usage:
    class MyView(ManagementRequiredMixin, TemplateView):
        template_name = 'portal_management/dashboard.html'
"""
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy


class _PortalMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Base mixin — subclasses set portal_groups_setting."""
    portal_groups_setting: str = ''
    login_url = reverse_lazy('accounts:login')

    def test_func(self):
        user = self.request.user
        groups = getattr(settings, self.portal_groups_setting, [])
        return (
            user.is_superuser or
            user.groups.filter(name__in=groups).exists()
        )

    def handle_no_permission(self):
        from django.shortcuts import redirect
        if not self.request.user.is_authenticated:
            return redirect(self.login_url)
        return redirect('accounts:no_permission')


class ManagementRequiredMixin(_PortalMixin):
    portal_groups_setting = 'MANAGEMENT_PORTAL_GROUPS'


class AcademicRequiredMixin(_PortalMixin):
    portal_groups_setting = 'ACADEMIC_PORTAL_GROUPS'


class AdministrationRequiredMixin(_PortalMixin):
    portal_groups_setting = 'ADMINISTRATION_PORTAL_GROUPS'


class FinanceRequiredMixin(_PortalMixin):
    portal_groups_setting = 'FINANCE_PORTAL_GROUPS'


class TransportRequiredMixin(_PortalMixin):
    portal_groups_setting = 'TRANSPORT_PORTAL_GROUPS'


class LibraryRequiredMixin(_PortalMixin):
    portal_groups_setting = 'LIBRARY_PORTAL_GROUPS'


class HealthRequiredMixin(_PortalMixin):
    portal_groups_setting = 'HEALTH_PORTAL_GROUPS'
