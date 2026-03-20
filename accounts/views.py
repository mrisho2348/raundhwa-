"""accounts/views.py"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View


def _get_portal_for_user(user):
    """Return the portal URL name for a user based on their group membership."""
    from django.conf import settings
    groups = set(user.groups.values_list('name', flat=True))
    mapping = [
        ('MANAGEMENT_PORTAL_GROUPS',      'management:dashboard'),
        ('ACADEMIC_PORTAL_GROUPS',         'academic:dashboard'),
        ('ADMINISTRATION_PORTAL_GROUPS',   'administration:dashboard'),
        ('FINANCE_PORTAL_GROUPS',          'finance:dashboard'),
        ('TRANSPORT_PORTAL_GROUPS',        'transport:dashboard'),
        ('LIBRARY_PORTAL_GROUPS',          'library:dashboard'),
        ('HEALTH_PORTAL_GROUPS',           'health:dashboard'),
    ]
    for setting_key, url_name in mapping:
        allowed = getattr(settings, setting_key, [])
        if groups & set(allowed):
            return url_name

    # Student portal
    if hasattr(user, 'student_profile'):
        return 'accounts:student_portal'

    # Superuser → management
    if user.is_superuser:
        return 'management:dashboard'

    return None


class LoginView(View):
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return self._redirect_user(request.user)
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user and user.is_active:
            login(request, user)
            return self._redirect_user(user)

        messages.error(request, 'Invalid username or password.')
        return render(request, self.template_name, {'username': username})

    def _redirect_user(self, user):
        portal = _get_portal_for_user(user)
        if portal:
            return redirect(reverse(portal))
        return redirect(reverse('accounts:no_portal'))


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect(reverse('accounts:login'))


class RedirectView(View):
    """POST-login redirect — used as LOGIN_REDIRECT_URL."""
    def get(self, request):
        if request.user.is_authenticated:
            portal = _get_portal_for_user(request.user)
            if portal:
                return redirect(reverse(portal))
        return redirect(reverse('accounts:login'))


@login_required
def change_password(request):
    """Shared password change view — used by all portals."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        # Clear must_change_password flag if student
        if hasattr(user, 'student_profile'):
            user.student_profile.__class__.objects.filter(
                pk=user.student_profile.pk
            ).update(must_change_password=False)
        messages.success(request, 'Password changed successfully.')
        portal = _get_portal_for_user(user)
        return redirect(reverse(portal) if portal else reverse('accounts:login'))

    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def student_portal(request):
    """Student portal landing page."""
    student = getattr(request.user, 'student_profile', None)
    if not student:
        return redirect(reverse('accounts:no_permission'))
    if student.must_change_password:
        messages.warning(request, 'Please change your default password before continuing.')
        return redirect(reverse('accounts:change_password'))
    return render(request, 'accounts/student_portal.html', {'student': student})


def no_permission(request):
    return render(request, 'accounts/no_permission.html', status=403)


def no_portal(request):
    return render(request, 'accounts/no_portal.html', status=200)
