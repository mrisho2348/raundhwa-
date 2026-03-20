"""
portal_management/views/staff.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All staff-related views for the Management portal.

Covers:
  - Staff list, detail, create, update
  - Role assignment and management
  - Department assignment
  - Teaching assignment
  - Class teacher assignment
  - Leave management (apply, approve, reject)
  - Staff qualification (placeholder)
"""
from django.contrib import messages
from django.db.models import Count, Q
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, TemplateView, View

from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, ClassLevel, CustomUser, Department,
    Staff, StaffDepartmentAssignment, StaffLeave,
    StaffRole, StaffRoleAssignment, StaffTeachingAssignment,
    ClassTeacherAssignment, StreamClass, Subject, UserType,
)
from portal_management.forms.staff_form import StaffForm, StaffRoleAssignmentForm, StaffRoleForm



# ── List ──────────────────────────────────────────────────────────────────────

class StaffListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/staff/list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['staff_list'] = Staff.objects.select_related('user').prefetch_related(
            'role_assignments__role'
        ).order_by('first_name', 'last_name')
        ctx['total'] = ctx['staff_list'].count()
        ctx['with_login'] = Staff.objects.filter(user__isnull=False).count()
        ctx['without_login'] = Staff.objects.filter(user__isnull=True).count()
        return ctx


# ── Create ────────────────────────────────────────────────────────────────────

class StaffCreateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/staff/form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': StaffForm(),
            'title': 'Add Staff Member',
            'action': 'Create',
        })

    def post(self, request):
        form = StaffForm(request.POST, request.FILES)
        if form.is_valid():
            staff = form.save(commit=False)
            create_user = form.cleaned_data.get('create_user', False)
            if create_user:
                username = (
                    form.cleaned_data.get('username') or
                    f"{form.cleaned_data['first_name'].lower()}"
                    f".{form.cleaned_data['last_name'].lower()}"
                ).replace(' ', '')
                email = form.cleaned_data.get('email', '')
                if not CustomUser.objects.filter(username=username).exists():
                    user = CustomUser.objects.create_user(
                        username=username,
                        email=email,
                        password=username,
                        user_type=UserType.STAFF,
                        first_name=form.cleaned_data.get('user_first_name', ''),
                        last_name=form.cleaned_data.get('user_last_name', ''),
                    )
                    staff.user = user
                else:
                    messages.warning(
                        request,
                        f'Username "{username}" already exists. '
                        f'Staff saved without a login account.'
                    )
            staff.save()
            messages.success(
                request,
                f'Staff member {staff.get_full_name()} added successfully.'
                + (f' Login: {staff.user.username}' if staff.user else '')
            )
            return redirect('management:staff_detail', pk=staff.pk)
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add Staff Member',
            'action': 'Create',
        })


# ── Detail ────────────────────────────────────────────────────────────────────

class StaffDetailView(ManagementRequiredMixin, DetailView):
    model = Staff
    template_name = 'portal_management/staff/detail.html'
    context_object_name = 'staff'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff = self.object
        ctx['role_assignments'] = staff.role_assignments.select_related(
            'role'
        ).order_by('-start_date')
        ctx['department_assignments'] = staff.department_assignments.select_related(
            'department'
        ).order_by('-start_date')
        ctx['teaching_assignments'] = staff.teaching_assignments.select_related(
            'subject', 'class_level', 'stream_class', 'academic_year'
        ).order_by('-academic_year__start_date')
        ctx['class_teacher_assignments'] = staff.class_teacher_assignments.select_related(
            'class_level', 'stream_class', 'academic_year'
        ).order_by('-academic_year__start_date')
        ctx['leaves'] = staff.leaves.order_by('-start_date')
        ctx['pending_leaves'] = staff.leaves.filter(status='pending').count()
        ctx['role_form'] = StaffRoleAssignmentForm(initial={'staff': staff})
        ctx['dept_form'] = _dept_assignment_form(staff)
        ctx['teaching_form'] = _teaching_assignment_form()
        return ctx


def _dept_assignment_form(staff):
    from portal_management.forms import StaffDepartmentAssignmentForm
    return StaffDepartmentAssignmentForm(initial={'staff': staff})


def _teaching_assignment_form():
    from portal_management.forms import StaffTeachingAssignmentForm
    return StaffTeachingAssignmentForm()


# ── Update ────────────────────────────────────────────────────────────────────

class StaffUpdateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/staff/form.html'

    def get(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        return render(request, self.template_name, {
            'form': StaffForm(instance=staff),
            'staff': staff,
            'title': f'Edit — {staff.get_full_name()}',
            'action': 'Update',
        })

    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        form = StaffForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff member updated successfully.')
            return redirect('management:staff_detail', pk=staff.pk)
        return render(request, self.template_name, {
            'form': form,
            'staff': staff,
            'title': f'Edit — {staff.get_full_name()}',
            'action': 'Update',
        })


# ── Role assignment ───────────────────────────────────────────────────────────

class StaffRoleAssignView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        form = StaffRoleAssignmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Role assigned to {staff.get_full_name()} successfully.'
            )
        else:
            messages.error(request, f'Error assigning role: {form.errors}')
        return redirect('management:staff_detail', pk=pk)


class StaffRoleDeactivateView(ManagementRequiredMixin, View):
    """Deactivate an existing role assignment."""
    def post(self, request, pk, assignment_pk):
        assignment = get_object_or_404(
            StaffRoleAssignment, pk=assignment_pk, staff_id=pk
        )
        assignment.is_active = False
        assignment.end_date = timezone.now().date()
        assignment.save()
        messages.success(request, 'Role assignment deactivated.')
        return redirect('management:staff_detail', pk=pk)


# ── Roles CRUD ────────────────────────────────────────────────────────────────

class StaffRoleListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/staff/roles.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['roles'] = StaffRole.objects.select_related('group').annotate(
            staff_count=Count(
                'staff_assignments',
                filter=Q(staff_assignments__is_active=True)
            )
        ).order_by('name')
        ctx['form'] = StaffRoleForm()
        ctx['groups'] = Group.objects.all()
        return ctx


class StaffRoleCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = StaffRoleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Role created successfully.')
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:staff_role_list')


class StaffRoleUpdateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/staff/role_form.html'

    def get(self, request, pk):
        role = get_object_or_404(StaffRole, pk=pk)
        return render(request, self.template_name, {
            'form': StaffRoleForm(instance=role),
            'role': role,
        })

    def post(self, request, pk):
        role = get_object_or_404(StaffRole, pk=pk)
        form = StaffRoleForm(request.POST, instance=role)
        if form.is_valid():
            form.save()
            messages.success(request, 'Role updated.')
            return redirect('management:staff_role_list')
        return render(request, self.template_name, {
            'form': form, 'role': role,
        })


# ── Department assignment ─────────────────────────────────────────────────────

class StaffDeptAssignView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        from portal_management.forms import StaffDepartmentAssignmentForm
        form = StaffDepartmentAssignmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Department assigned to {staff.get_full_name()}.'
            )
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:staff_detail', pk=pk)


# ── Teaching assignment ───────────────────────────────────────────────────────

class StaffTeachingAssignView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        from portal_management.forms import StaffTeachingAssignmentForm
        form = StaffTeachingAssignmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Teaching assignment added for {staff.get_full_name()}.'
            )
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:staff_detail', pk=pk)


# ── Leave management ──────────────────────────────────────────────────────────

class StaffLeaveListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/staff/leave_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_leaves'] = StaffLeave.objects.filter(
            status='pending'
        ).select_related('staff', 'reviewed_by').order_by('-start_date')
        ctx['all_leaves'] = StaffLeave.objects.select_related(
            'staff', 'reviewed_by'
        ).order_by('-start_date')[:100]
        return ctx


class StaffLeaveCreateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/staff/leave_form.html'

    def get(self, request):
        from portal_management.forms import StaffLeaveForm
        return render(request, self.template_name, {
            'form': StaffLeaveForm(),
            'title': 'Apply for Leave',
        })

    def post(self, request):
        from portal_management.forms import StaffLeaveForm
        form = StaffLeaveForm(request.POST)
        if form.is_valid():
            leave = form.save()
            messages.success(
                request,
                f'Leave application for {leave.staff.get_full_name()} submitted.'
            )
            return redirect('management:staff_leave_list')
        return render(request, self.template_name, {
            'form': form, 'title': 'Apply for Leave',
        })


class StaffLeaveApproveView(ManagementRequiredMixin, View):
    """Approve a pending leave application."""
    def post(self, request, pk):
        leave = get_object_or_404(StaffLeave, pk=pk, status='pending')
        reviewer = getattr(request.user, 'staff_profile', None)
        if not reviewer:
            messages.error(
                request,
                'Only staff members with a profile can approve leave.'
            )
            return redirect('management:staff_leave_list')
        leave.status = 'approved'
        leave.reviewed_by = reviewer
        leave.reviewed_at = timezone.now()
        leave.review_remarks = request.POST.get('remarks', 'Approved.')
        leave.save()
        messages.success(
            request,
            f'Leave for {leave.staff.get_full_name()} approved.'
        )
        return redirect('management:staff_leave_list')


class StaffLeaveRejectView(ManagementRequiredMixin, View):
    """Reject a pending leave application."""
    def post(self, request, pk):
        leave = get_object_or_404(StaffLeave, pk=pk, status='pending')
        reviewer = getattr(request.user, 'staff_profile', None)
        remarks = request.POST.get('remarks', '').strip()
        if not remarks:
            messages.error(
                request,
                'Rejection remarks are required. Please explain why.'
            )
            return redirect('management:staff_leave_list')
        leave.status = 'rejected'
        leave.reviewed_by = reviewer
        leave.reviewed_at = timezone.now()
        leave.review_remarks = remarks
        leave.save()
        messages.warning(
            request,
            f'Leave for {leave.staff.get_full_name()} rejected.'
        )
        return redirect('management:staff_leave_list')