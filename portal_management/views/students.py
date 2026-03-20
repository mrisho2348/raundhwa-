"""
portal_management/views/students.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All student-related views for the Management portal.

32 views organised into 7 sections:
  ── STUDENT CRUD ──────────────────── StudentListView, StudentCreateView,
                                        StudentDetailView, StudentUpdateView
  ── ENROLLMENT ────────────────────── StudentEnrollView, StudentStreamAssignView
  ── DRAFTS ────────────────────────── StudentDraftListView, StudentDraftCreateView,
                                        StudentDraftEditView, StudentDraftPublishView,
                                        StudentDraftDeleteView
  ── LIFECYCLE ─────────────────────── StudentSuspendView, StudentLiftSuspensionView,
                                        StudentTransferView, StudentWithdrawView
  ── ACCOUNT ───────────────────────── StudentResetPasswordView
  ── PARENT MANAGEMENT ─────────────── StudentParentManagementView,
                                        StudentAddParentView, StudentParentUpdateView,
                                        StudentParentRemoveView, StudentParentSetPrimaryView,
                                        StudentParentBulkAddView, ParentEditView,
                                        ParentDeleteView, GetParentDetailsView,
                                        ParentListView, ParentCreateView, ParentUpdateView
  ── AJAX HELPERS ──────────────────── SearchParentsView, GetStreamsView,
                                        GetCombinationsView
"""

import json
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, View

from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, AuditLog, ClassLevel, Combination,
    Parent, StreamClass, Student, StudentCombinationAssignment, StudentEnrollment,
    StudentParent, StudentStreamAssignment, StudentSubjectAssignment, StudentSuspension, StudentTransferOut, Term,
)
from portal_management.forms.parent_form import ParentForm
from portal_management.forms.student_form import StudentEnrollmentForm, StudentForm
from portal_management.forms.student_parent_form import StudentParentForm

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# STUDENT CRUD
# ════════════════════════════════════════════════════════════════════════════

class StudentListView(ManagementRequiredMixin, TemplateView):
    """Display all students in a DataTable with status summary pills."""
    template_name = 'portal_management/students/list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get('status')
        qs = Student.objects.select_related('user').order_by('registration_number')
        if status_filter:
            qs = qs.filter(status=status_filter)
        ctx['students'] = qs
        ctx['status_counts'] = {
            s: Student.objects.filter(status=s).count()
            for s in ['active', 'suspended', 'withdrawn', 'completed', 'transferred']
        }
        ctx['selected_status'] = status_filter
        return ctx


class StudentCreateView(ManagementRequiredMixin, View):
    """
    Enroll a new student.
    Supports multiple submit actions via POST param 'action':
      save_view    -> redirect to student detail  (default)
      save_list    -> redirect to student list
      save_new     -> redirect back to create form
      save_enroll  -> redirect to enrollment page
      save_parent  -> redirect to parent management page
      save_draft   -> save as draft (session-based)
    Supports AJAX: returns JSON when X-Requested-With header is present.
    """
    template_name = 'portal_management/students/form.html'

    def get(self, request):
        form = StudentForm()
        form.fields['admission_date'].initial = timezone.now().date()

        # Load session draft if requested
        draft_id = request.GET.get('draft')
        if draft_id:
            draft_data = request.session.get(f'draft_{draft_id}', {})
            if draft_data:
                form = StudentForm(initial=draft_data)
                messages.info(request, 'Loading draft data.')

        return render(request, self.template_name, {
            'form': form,
            'title': 'Enroll New Student',
            'action': 'Create',
        })

    def post(self, request):
        form = StudentForm(request.POST, request.FILES)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        next_action = request.POST.get('action', 'save_view')

        # ── Draft save (no DB record created) ────────────────────────────
        if next_action == 'save_draft' and form.is_valid():
            draft_data = {
                k: v for k, v in form.cleaned_data.items()
                if k != 'profile_picture'
            }
            draft_id = int(timezone.now().timestamp())
            request.session[f'draft_{draft_id}'] = {
                'data': draft_data,
                'timestamp': timezone.now().isoformat(),
            }
            # Trim old drafts (keep last 10)
            keys = [k for k in request.session.keys() if k.startswith('draft_')]
            for old in sorted(keys)[:-10]:
                del request.session[old]
            messages.success(request, 'Draft saved. You can continue later.')
            if is_ajax:
                return JsonResponse({'success': True, 'draft_id': draft_id,
                                     'message': 'Draft saved successfully.'})
            return redirect('management:student_draft_list')

        # ── Regular save ──────────────────────────────────────────────────
        if form.is_valid():
            try:
                with transaction.atomic():
                    student = form.save()
                    if not Student.objects.filter(pk=student.pk).exists():
                        raise ValidationError('Student was not properly saved.')

                    # Clear session drafts
                    for k in [k for k in request.session.keys()
                               if k.startswith('draft_')]:
                        del request.session[k]

                    messages.success(
                        request,
                        f'Student {student.full_name} enrolled successfully. '
                        f'Registration Number: {student.registration_number}'
                    )

                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'student_id': student.pk,
                            'registration_number': student.registration_number,
                            'redirect_url': reverse('management:student_detail',
                                                    kwargs={'pk': student.pk}),
                        })

                    if next_action == 'save_list':
                        return redirect('management:student_list')
                    elif next_action == 'save_new':
                        messages.info(request, 'Add another student.')
                        return redirect('management:student_create')
                    elif next_action == 'save_enroll':
                        messages.info(request, f'Complete enrollment for {student.full_name}.')
                        return redirect('management:student_enroll', pk=student.pk)
                    elif next_action == 'save_parent':
                        messages.info(request, f'Add parent/guardian for {student.full_name}.')
                        return redirect('management:student_parent_management', pk=student.pk)
                    else:
                        return redirect('management:student_detail', pk=student.pk)

            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f'Validation error: {error_msg}')
                logger.error('StudentCreate validation error: %s', e, exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': error_msg})

            except Exception as e:
                messages.error(request, f'Error saving student: {e}')
                logger.error('StudentCreate error: %s', e, exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)})
        else:
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} '
                f'error{"s" if error_count > 1 else ""} below.'
            )
            logger.error('StudentCreate form errors: %s', form.errors)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': form.errors,
                    'error_messages': [
                        f'{form.fields[f].label if f in form.fields else f}: '
                        f'{", ".join(errs)}'
                        for f, errs in form.errors.items()
                    ],
                })

        return render(request, self.template_name, {
            'form': form,
            'title': 'Enroll New Student',
            'action': 'Create',
        })


class StudentDetailView(ManagementRequiredMixin, DetailView):
    """Full student profile page."""
    model = Student
    template_name = 'portal_management/students/detail.html'
    context_object_name = 'student'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        student = self.object
        
        # Get enrollments with proper select_related (no combination field)
        ctx['enrollments'] = student.enrollments.select_related(
            'academic_year', 
            'class_level'
        ).order_by('-academic_year__start_date')
        
        # For each enrollment, get the combination if applicable (A-Level)
        for enrollment in ctx['enrollments']:
            # Get the current combination for this enrollment
            if enrollment.class_level.educational_level.level_type == 'A_LEVEL':
                combination_assignment = enrollment.combination_assignments.filter(is_active=True).first()
                enrollment.combination = combination_assignment.combination if combination_assignment else None
            else:
                enrollment.combination = None
        
        ctx['parents'] = student.parents.all()
        
        # Get active enrollment
        active_enrollment = student.enrollments.filter(status='active').first()
        ctx['active_enrollment'] = active_enrollment
        
        # Get stream and combination for active enrollment
        ctx['stream'] = None
        ctx['combination'] = None
        
        if active_enrollment:
            if hasattr(active_enrollment, 'stream_assignment'):
                ctx['stream'] = active_enrollment.stream_assignment.stream_class
            
            # Get combination for A-Level
            if active_enrollment.class_level.educational_level.level_type == 'A_LEVEL':
                combination_assignment = active_enrollment.combination_assignments.filter(is_active=True).first()
                ctx['combination'] = combination_assignment.combination if combination_assignment else None
        
        ctx['suspensions'] = student.suspensions.order_by('-suspension_date')
        ctx['active_suspension'] = student.suspensions.filter(is_lifted=False).first()
        ctx['has_transfer'] = hasattr(student, 'transfer_out')
        ctx['has_withdrawal'] = hasattr(student, 'withdrawal')
        ctx['audit_logs'] = AuditLog.objects.filter(
            object_id=student.pk,
        ).select_related('user').order_by('-timestamp')[:20]
        
        return ctx


class StudentUpdateView(ManagementRequiredMixin, View):
    """
    Edit an existing student.
    Same save pattern as StudentCreateView — supports the same action values
    and AJAX responses.
    """
    template_name = 'portal_management/students/form.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if student.status in ['transferred', 'withdrawn']:
            messages.warning(
                request,
                f'This student is {student.get_status_display()}. '
                f'Some fields may be read-only.'
            )
        return render(request, self.template_name, {
            'form': StudentForm(instance=student),
            'student': student,
            'title': f'Edit — {student.full_name}',
            'action': 'Update',
            'is_update': True,
        })

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        form = StudentForm(request.POST, request.FILES, instance=student)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        next_action = request.POST.get('action', 'save_view')

        if form.is_valid():
            try:
                with transaction.atomic():
                    student = form.save()
                    if not Student.objects.filter(pk=student.pk).exists():
                        raise ValidationError('Student was not properly saved.')

                    messages.success(request,
                                     f'Student {student.full_name} updated successfully.')

                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'redirect_url': reverse('management:student_detail',
                                                    kwargs={'pk': student.pk}),
                        })

                    if next_action == 'save_list':
                        return redirect('management:student_list')
                    elif next_action == 'save_new':
                        return redirect('management:student_create')
                    elif next_action == 'save_enroll':
                        return redirect('management:student_enroll', pk=student.pk)
                    elif next_action == 'save_parent':
                        return redirect('management:student_parent_management',
                                        pk=student.pk)
                    else:
                        return redirect('management:student_detail', pk=student.pk)

            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f'Validation error: {error_msg}')
                logger.error('StudentUpdate validation error: %s', e, exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': error_msg})

            except Exception as e:
                messages.error(request, f'Error updating student: {e}')
                logger.error('StudentUpdate error: %s', e, exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)})
        else:
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} '
                f'error{"s" if error_count > 1 else ""} below.'
            )
            logger.error('StudentUpdate form errors: %s', form.errors)
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors})

        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'title': f'Edit — {student.full_name}',
            'action': 'Update',
            'is_update': True,
        })


# ════════════════════════════════════════════════════════════════════════════
# ENROLLMENT
# ════════════════════════════════════════════════════════════════════════════

class StudentEnrollView(ManagementRequiredMixin, View):
    """
    Enroll an existing student into a class level for an academic year.
    Validates: no duplicate enrollment, A-Level combination required,
    stream capacity, and validates Term belongs to academic year.
    """
    template_name = 'portal_management/students/enroll.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if student.status not in ['active', 'completed']:
            messages.warning(
                request,
                f'Student is {student.get_status_display()}. '
                f'Only active or completed students can be enrolled.'
            )
            return redirect('management:student_detail', pk=pk)

        active_year = AcademicYear.objects.filter(is_active=True).first()
        current_enrollment = student.enrollments.filter(status='active').first()
        form = StudentEnrollmentForm(initial={
            'student': student,
            'academic_year': active_year,
            'enrollment_date': timezone.now().date(),
        })
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'current_enrollment': current_enrollment,
            'active_year': active_year,
            'title': f'Enroll {student.full_name}',
        })

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        form = StudentEnrollmentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save(commit=False)
                    enrollment.student = student
                    self._validate_enrollment(enrollment)
                    enrollment.save()

                    # Optional stream assignment
                    stream_id = request.POST.get('stream')
                    if stream_id:
                        from core.models import StudentStreamAssignment
                        stream = get_object_or_404(StreamClass, pk=stream_id)
                        current_count = StudentStreamAssignment.objects.filter(
                            stream_class=stream,
                            enrollment__academic_year=enrollment.academic_year
                        ).count()
                        if current_count >= stream.capacity:
                            raise ValidationError(
                                f'Stream {stream.name} has reached maximum '
                                f'capacity ({stream.capacity}).'
                            )
                        StudentStreamAssignment.objects.create(
                            enrollment=enrollment,
                            stream_class=stream,
                            assigned_date=timezone.now().date()
                        )

                    messages.success(
                        request,
                        f'{student.full_name} enrolled in {enrollment.class_level.name} '
                        f'for {enrollment.academic_year.name}.'
                    )
                    action = request.POST.get('action', 'save')
                    if action == 'save_add_another':
                        return redirect('management:student_enroll', pk=pk)
                    return redirect('management:student_detail', pk=pk)

            except ValidationError as e:
                messages.error(request, str(e))
                logger.error('Enrollment validation error: %s', e, exc_info=True)
            except Exception as e:
                messages.error(request, f'Error enrolling student: {e}')
                logger.error('Enrollment error: %s', e, exc_info=True)
        else:
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} '
                f'error{"s" if error_count > 1 else ""} below.'
            )
            logger.error('Enrollment form errors: %s', form.errors)

        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'title': f'Enroll {student.full_name}',
        })

    @staticmethod
    def _validate_enrollment(enrollment):
        # Duplicate check
        if StudentEnrollment.objects.filter(
            student=enrollment.student,
            academic_year=enrollment.academic_year
        ).exists():
            raise ValidationError(
                f'{enrollment.student.full_name} is already enrolled '
                f'in {enrollment.academic_year.name}.'
            )
        level_type = enrollment.class_level.educational_level.level_type
        # A-Level must have combination
        if level_type == 'A_LEVEL' and not enrollment.combination:
            raise ValidationError('Combination is required for A-Level enrollment.')
        # Non-A-Level must not have combination
        if level_type != 'A_LEVEL' and enrollment.combination:
            raise ValidationError(
                'Combination can only be set for A-Level students.'
            )


class StudentStreamAssignView(ManagementRequiredMixin, View):
    """Assign or change stream for an enrolled student."""
    template_name = 'portal_management/students/stream_assign.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        active_enrollment = student.enrollments.filter(status='active').first()
        if not active_enrollment:
            messages.warning(request, f'{student.full_name} is not currently enrolled.')
            return redirect('management:student_detail', pk=pk)
        current_stream = None
        if hasattr(active_enrollment, 'stream_assignment'):
            current_stream = active_enrollment.stream_assignment.stream_class
        return render(request, self.template_name, {
            'student': student,
            'enrollment': active_enrollment,
            'streams': StreamClass.objects.filter(
                class_level=active_enrollment.class_level
            ).order_by('stream_letter'),
            'current_stream': current_stream,
            'title': f'Assign Stream — {student.full_name}',
        })

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        active_enrollment = student.enrollments.filter(status='active').first()
        if not active_enrollment:
            messages.error(request, 'No active enrollment found.')
            return redirect('management:student_detail', pk=pk)
        try:
            with transaction.atomic():
                from core.models import StudentStreamAssignment
                stream_id = request.POST.get('stream')
                if not stream_id:
                    if hasattr(active_enrollment, 'stream_assignment'):
                        active_enrollment.stream_assignment.delete()
                        messages.success(
                            request, f'Stream assignment removed for {student.full_name}.'
                        )
                else:
                    stream = get_object_or_404(StreamClass, pk=stream_id)
                    count = StudentStreamAssignment.objects.filter(
                        stream_class=stream,
                        enrollment__academic_year=active_enrollment.academic_year
                    ).exclude(enrollment=active_enrollment).count()
                    if count >= stream.capacity:
                        raise ValidationError(
                            f'Stream {stream.name} has reached maximum capacity.'
                        )
                    if hasattr(active_enrollment, 'stream_assignment'):
                        sa = active_enrollment.stream_assignment
                        sa.stream_class = stream
                        sa.assigned_date = timezone.now().date()
                        sa.save()
                    else:
                        StudentStreamAssignment.objects.create(
                            enrollment=active_enrollment,
                            stream_class=stream,
                            assigned_date=timezone.now().date()
                        )
                    messages.success(
                        request, f'{student.full_name} assigned to stream {stream.name}.'
                    )
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error assigning stream: {e}')
            logger.error('Stream assignment error: %s', e, exc_info=True)
        return redirect('management:student_detail', pk=pk)


# ════════════════════════════════════════════════════════════════════════════
# DRAFTS
# ════════════════════════════════════════════════════════════════════════════

class StudentDraftListView(ManagementRequiredMixin, ListView):
    """List all students with draft status."""
    template_name = 'portal_management/students/drafts/list.html'
    context_object_name = 'drafts'
    paginate_by = 20

    def get_queryset(self):
        return Student.objects.filter(status='draft').order_by('-updated_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_drafts'] = self.get_queryset().count()
        return ctx


class StudentDraftCreateView(ManagementRequiredMixin, View):
    """Save partial student data as a draft via AJAX (JSON body)."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            with transaction.atomic():
                student = Student.objects.create(
                    first_name=data.get('first_name', ''),
                    middle_name=data.get('middle_name', ''),
                    last_name=data.get('last_name', ''),
                    gender=data.get('gender', ''),
                    date_of_birth=data.get('date_of_birth') or None,
                    address=data.get('address', ''),
                    national_id=data.get('national_id', ''),
                    physical_disability=data.get('physical_disability', ''),
                    admission_date=data.get('admission_date') or timezone.now().date(),
                    status='draft',
                )
                request.session[f'draft_{student.pk}'] = data
                return JsonResponse({
                    'success': True,
                    'draft_id': student.pk,
                    'message': 'Draft saved successfully.'
                })
        except Exception as e:
            logger.error('Draft create error: %s', e, exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class StudentDraftEditView(ManagementRequiredMixin, View):
    """Edit an existing draft student."""
    template_name = 'portal_management/students/drafts/edit.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk, status='draft')
        draft_data = request.session.get(f'draft_{student.pk}', {})
        return render(request, self.template_name, {
            'student': student,
            'draft_data': draft_data,
            'title': f'Edit Draft — {student.full_name or "New Student"}',
        })


class StudentDraftPublishView(ManagementRequiredMixin, View):
    """Promote a draft student to active status."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk, status='draft')
        try:
            with transaction.atomic():
                student.status = 'active'
                student.save()
                request.session.pop(f'draft_{student.pk}', None)
                messages.success(
                    request,
                    f'Draft published. Registration: {student.registration_number}'
                )
                return redirect('management:student_detail', pk=pk)
        except Exception as e:
            messages.error(request, f'Error publishing draft: {e}')
            logger.error('Draft publish error: %s', e, exc_info=True)
            return redirect('management:student_draft_edit', pk=pk)


class StudentDraftDeleteView(ManagementRequiredMixin, View):
    """Permanently delete a draft student record."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk, status='draft')
        try:
            student.delete()
            request.session.pop(f'draft_{pk}', None)
            messages.success(request, 'Draft deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting draft: {e}')
            logger.error('Draft delete error: %s', e, exc_info=True)
        return redirect('management:student_draft_list')


# ════════════════════════════════════════════════════════════════════════════
# LIFECYCLE
# ════════════════════════════════════════════════════════════════════════════

class StudentSuspendView(ManagementRequiredMixin, View):
    """Suspend a student. Model.save() auto-sets status='suspended'."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        try:
            with transaction.atomic():
                StudentSuspension.objects.create(
                    student=student,
                    suspension_date=request.POST.get('suspension_date'),
                    expected_return_date=request.POST.get(
                        'expected_return_date'
                    ) or None,
                    reason=request.POST.get('reason'),
                    remarks=request.POST.get('remarks', ''),
                    authorised_by=getattr(request.user, 'staff_profile', None),
                )
                messages.success(request, f'{student.full_name} has been suspended.')
        except Exception as e:
            messages.error(request, f'Error suspending student: {e}')
            logger.error('Suspend error: %s', e, exc_info=True)
        return redirect('management:student_detail', pk=pk)


class StudentLiftSuspensionView(ManagementRequiredMixin, View):
    """Lift an active suspension. Model.save() restores status='active'."""

    def post(self, request, pk, suspension_pk):
        student = get_object_or_404(Student, pk=pk)
        suspension = get_object_or_404(
            StudentSuspension, pk=suspension_pk, student=student
        )
        try:
            suspension.is_lifted = True
            suspension.lifted_date = timezone.now().date()
            suspension.lifted_by = getattr(request.user, 'staff_profile', None)
            suspension.save()
            messages.success(
                request,
                f'Suspension lifted. {student.full_name} is now active.'
            )
        except Exception as e:
            messages.error(request, f'Error lifting suspension: {e}')
            logger.error('Lift suspension error: %s', e, exc_info=True)
        return redirect('management:student_detail', pk=pk)


class StudentTransferView(ManagementRequiredMixin, View):
    """Transfer student out. Model.save() auto-sets status='transferred'."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if hasattr(student, 'transfer_out'):
            messages.warning(
                request, f'{student.full_name} already has a transfer record.'
            )
            return redirect('management:student_detail', pk=pk)
        try:
            with transaction.atomic():
                ae = student.enrollments.filter(
                    status='active'
                ).select_related('class_level', 'academic_year').first()
                StudentTransferOut.objects.create(
                    student=student,
                    transfer_date=request.POST.get('transfer_date'),
                    destination_school_name=request.POST.get('destination_school', ''),
                    reason=request.POST.get('reason', 'voluntary'),
                    last_class_level=ae.class_level if ae else None,
                    last_academic_year=ae.academic_year if ae else None,
                    transfer_letter_issued=(
                        request.POST.get('transfer_letter_issued') == 'on'
                    ),
                    transcript_issued=(
                        request.POST.get('transcript_issued') == 'on'
                    ),
                    remarks=request.POST.get('remarks', ''),
                    authorised_by=getattr(request.user, 'staff_profile', None),
                )
                messages.success(
                    request,
                    f'{student.full_name} transferred out. Status updated.'
                )
        except Exception as e:
            messages.error(request, f'Error transferring student: {e}')
            logger.error('Transfer error: %s', e, exc_info=True)
        return redirect('management:student_detail', pk=pk)


class StudentWithdrawView(ManagementRequiredMixin, View):
    """Record withdrawal. Model.save() auto-sets status='withdrawn'."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if hasattr(student, 'withdrawal'):
            messages.warning(
                request, f'{student.full_name} already has a withdrawal record.'
            )
            return redirect('management:student_detail', pk=pk)
        try:
            with transaction.atomic():
                from core.models import StudentWithdrawal
                ae = student.enrollments.filter(
                    status='active'
                ).select_related('class_level', 'academic_year').first()
                StudentWithdrawal.objects.create(
                    student=student,
                    withdrawal_date=request.POST.get('withdrawal_date'),
                    reason=request.POST.get('reason', 'other'),
                    last_class_level=ae.class_level if ae else None,
                    last_academic_year=ae.academic_year if ae else None,
                    transcript_issued=(
                        request.POST.get('transcript_issued') == 'on'
                    ),
                    remarks=request.POST.get('remarks', ''),
                    authorised_by=getattr(request.user, 'staff_profile', None),
                )
                messages.success(
                    request,
                    f'{student.full_name} withdrawal recorded. Status updated.'
                )
        except Exception as e:
            messages.error(request, f'Error recording withdrawal: {e}')
            logger.error('Withdrawal error: %s', e, exc_info=True)
        return redirect('management:student_detail', pk=pk)


# ════════════════════════════════════════════════════════════════════════════
# ACCOUNT
# ════════════════════════════════════════════════════════════════════════════

class StudentResetPasswordView(ManagementRequiredMixin, View):
    """Reset student portal password back to their registration number (AJAX)."""

    def post(self, request, user_id):
        try:
            from core.models import CustomUser, UserType
            user = get_object_or_404(
                CustomUser, pk=user_id, user_type=UserType.STUDENT
            )
            user.set_password(user.username)
            user.save(update_fields=['password'])
            logger.info(
                'Password reset: student=%s by=%s', user.username, request.user
            )
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error('Password reset error: %s', e, exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# PARENT MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

class StudentParentManagementView(ManagementRequiredMixin, View):
    """Comprehensive parent management page for a student."""
    template_name = 'portal_management/students/parent_management.html'

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        relationships = StudentParent.objects.filter(
            student=student
        ).select_related('parent').order_by(
            '-is_primary_contact', 'parent__full_name'
        )
        
        # Calculate counts in the view
        total_parents = relationships.count()
        primary_count = relationships.filter(is_primary_contact=True).count()
        fee_responsible_count = relationships.filter(is_fee_responsible=True).count()
        
        recent_parents = Parent.objects.order_by('-id')[:5]
        
        return render(request, self.template_name, {
            'student': student,
            'relationships': relationships,
            'recent_parents': recent_parents,
            'parent_form': StudentParentForm(),
            'title': f'Manage Parents — {student.full_name}',
            'relationship_choices': Parent.RELATIONSHIP_CHOICES,
            # Add these counts
            'total_parents': total_parents,
            'primary_count': primary_count,
            'fee_responsible_count': fee_responsible_count,
        })
    

class StudentAddParentView(ManagementRequiredMixin, View):
    """Add a new parent or link an existing parent to a student."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        action = request.POST.get('parent_action', 'create_new')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        try:
            with transaction.atomic():
                if action == 'link_existing':
                    result = self._link_existing(request, student)
                else:
                    result = self._create_new(request, student)

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': result['message'],
                        'redirect_url': reverse(
                            'management:student_parent_management',
                            kwargs={'pk': student.pk}
                        ),
                    })
                messages.success(request, result['message'])
                return redirect('management:student_parent_management', pk=pk)

        except ValidationError as e:
            error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
            logger.error('AddParent validation error student=%s: %s', pk, e,
                         exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg,
                                     'errors': getattr(e, 'message_dict',
                                                       {'__all__': [error_msg]})})
            messages.error(request, f'Error: {error_msg}')
            return redirect('management:student_parent_management', pk=pk)

        except Exception as e:
            logger.error('AddParent error student=%s: %s', pk, e, exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)},
                                    status=500)
            messages.error(request, f'Error adding parent: {e}')
            return redirect('management:student_parent_management', pk=pk)

    # ── Private helpers ───────────────────────────────────────────────────

    def _link_existing(self, request, student):
        parent_id = request.POST.get('parent_id')
        if not parent_id:
            raise ValidationError('Please select a parent to link.')
        parent = get_object_or_404(Parent, pk=parent_id)
        relationship, created = StudentParent.objects.get_or_create(
            student=student, parent=parent,
            defaults={
                'is_primary_contact': (
                    request.POST.get('is_primary_contact_link') == 'on'
                ),
                'is_fee_responsible': (
                    request.POST.get('is_fee_responsible_link') == 'on'
                ),
                'fee_responsible_from': (
                    request.POST.get('fee_responsible_from_link') or None
                ),
            }
        )
        if not created:
            relationship.is_primary_contact = (
                request.POST.get('is_primary_contact_link') == 'on'
            )
            relationship.is_fee_responsible = (
                request.POST.get('is_fee_responsible_link') == 'on'
            )
            if request.POST.get('fee_responsible_from_link'):
                relationship.fee_responsible_from = (
                    request.POST.get('fee_responsible_from_link')
                )
            relationship.save()
        if relationship.is_primary_contact:
            StudentParent.objects.filter(
                student=student
            ).exclude(pk=relationship.pk).update(is_primary_contact=False)
        msg = (
            f'{parent.full_name} linked to student successfully.'
            if created else
            f'{parent.full_name}\'s relationship updated successfully.'
        )
        return {'message': msg}

    def _create_new(self, request, student):
        form = StudentParentForm(request.POST)
        if not form.is_valid():
            raise ValidationError(form.errors)
        parent = form.save()
        relationship = StudentParent.objects.create(
            student=student, parent=parent,
            is_primary_contact=request.POST.get('is_primary_contact') == 'on',
            is_fee_responsible=request.POST.get('is_fee_responsible') == 'on',
            fee_responsible_from=request.POST.get('fee_responsible_from') or None,
        )
        if relationship.is_primary_contact:
            StudentParent.objects.filter(
                student=student
            ).exclude(pk=relationship.pk).update(is_primary_contact=False)
        return {'message': f'Parent {parent.full_name} added and linked successfully.'}


class StudentParentUpdateView(ManagementRequiredMixin, View):
    """Update the is_primary_contact / is_fee_responsible flags on a relationship."""

    def post(self, request, pk, relationship_pk):
        relationship = get_object_or_404(
            StudentParent, pk=relationship_pk, student_id=pk
        )
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            with transaction.atomic():
                # Handle is_primary_contact - accepts 'on', 'true', True, '1', 1
                primary_val = request.POST.get('is_primary_contact')
                if primary_val is not None:
                    relationship.is_primary_contact = self._to_boolean(primary_val)
                
                # Handle is_fee_responsible - accepts 'on', 'true', True, '1', 1
                fee_val = request.POST.get('is_fee_responsible')
                if fee_val is not None:
                    relationship.is_fee_responsible = self._to_boolean(fee_val)
                
                # Handle fee_responsible_from date
                fee_from = request.POST.get('fee_responsible_from')
                if fee_from:
                    relationship.fee_responsible_from = fee_from
                
                relationship.save()
                
                # Handle primary contact logic
                if relationship.is_primary_contact:
                    StudentParent.objects.filter(
                        student_id=pk
                    ).exclude(pk=relationship_pk).update(is_primary_contact=False)
                
                msg = f'{relationship.parent.full_name}\'s relationship updated.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True, 
                        'message': msg,
                        'data': {
                            'is_primary_contact': relationship.is_primary_contact,
                            'is_fee_responsible': relationship.is_fee_responsible,
                            'fee_responsible_from': relationship.fee_responsible_from,
                        }
                    })
                messages.success(request, msg)
                
        except Exception as e:
            logger.error('ParentUpdate error: %s', e, exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'Error: {e}')
            
        return redirect('management:student_parent_management', pk=pk)
    
    def _to_boolean(self, value):
        """Convert various truthy values to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, str)):
            if str(value).lower() in ('true', '1', 'on', 'yes'):
                return True
        return False
    

class StudentParentRemoveView(ManagementRequiredMixin, View):
    """Unlink a parent from a student (StudentParent junction record deleted)."""

    def post(self, request, pk, relationship_pk):
        relationship = get_object_or_404(
            StudentParent, pk=relationship_pk, student_id=pk
        )
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            parent_name = relationship.parent.full_name
            was_primary = relationship.is_primary_contact
            with transaction.atomic():
                relationship.delete()
                new_primary = None
                if was_primary:
                    next_rel = StudentParent.objects.filter(
                        student_id=pk
                    ).first()
                    if next_rel:
                        next_rel.is_primary_contact = True
                        next_rel.save()
                        new_primary = {
                            'id': next_rel.pk,
                            'name': next_rel.parent.full_name,
                        }
                msg = f'{parent_name} removed from student\'s record.'
                if is_ajax:
                    return JsonResponse({
                        'success': True, 'message': msg,
                        'removed_id': relationship_pk,
                        'was_primary': was_primary,
                        'new_primary': new_primary,
                    })
                messages.success(request, msg)
        except Exception as e:
            logger.error('ParentRemove error: %s', e, exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'Error removing parent: {e}')
        return redirect('management:student_parent_management', pk=pk)


class StudentParentSetPrimaryView(ManagementRequiredMixin, View):
    """Set one parent as the primary contact, clearing all others."""

    def post(self, request, pk, relationship_pk):
        relationship = get_object_or_404(
            StudentParent, pk=relationship_pk, student_id=pk
        )
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            with transaction.atomic():
                StudentParent.objects.filter(
                    student_id=pk
                ).update(is_primary_contact=False)
                relationship.is_primary_contact = True
                relationship.save()
                msg = (
                    f'{relationship.parent.full_name} is now the primary contact.'
                )
                if is_ajax:
                    return JsonResponse({
                        'success': True, 'message': msg,
                        'relationship_id': relationship.pk,
                        'parent_name': relationship.parent.full_name,
                    })
                messages.success(request, msg)
        except Exception as e:
            logger.error('SetPrimary error: %s', e, exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'Error: {e}')
        return redirect('management:student_parent_management', pk=pk)


class StudentParentBulkAddView(ManagementRequiredMixin, View):
    """Link multiple existing parents to a student at once."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        parent_ids = request.POST.getlist('parent_ids')
        if not parent_ids:
            messages.warning(request, 'No parents selected.')
            return redirect('management:student_parent_management', pk=pk)
        try:
            with transaction.atomic():
                added = 0
                for pid in parent_ids:
                    parent = get_object_or_404(Parent, pk=pid)
                    _, created = StudentParent.objects.get_or_create(
                        student=student, parent=parent,
                        defaults={
                            'is_primary_contact': False,
                            'is_fee_responsible': False,
                        }
                    )
                    if created:
                        added += 1
                if added:
                    messages.success(
                        request,
                        f'Successfully added {added} parent(s) to {student.full_name}.'
                    )
                else:
                    messages.info(request, 'Selected parents were already linked.')
        except Exception as e:
            messages.error(request, f'Error adding parents: {e}')
            logger.error('BulkAdd error: %s', e, exc_info=True)
        return redirect('management:student_parent_management', pk=pk)


class ParentEditView(ManagementRequiredMixin, View):
    """Edit a Parent record. Returns JSON on AJAX, redirects on normal POST."""
    template_name = 'portal_management/students/edit_parent_modal.html'

    def get(self, request, parent_pk):
        parent = get_object_or_404(Parent, pk=parent_pk)
        return render(request, self.template_name, {
            'parent': parent,
            'form': ParentForm(instance=parent),
        })

    def post(self, request, parent_pk):
        parent = get_object_or_404(Parent, pk=parent_pk)
        form = ParentForm(request.POST, instance=parent)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if form.is_valid():
            try:
                parent = form.save()
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': f'{parent.full_name} updated successfully.',
                        'parent': {
                            'id': parent.pk,
                            'full_name': parent.full_name,
                            'phone_number': parent.phone_number,
                            'email': parent.email or '',
                            'relationship': parent.get_relationship_display(),
                        }
                    })
                messages.success(request, f'{parent.full_name} updated successfully.')
                return redirect(request.META.get('HTTP_REFERER',
                                                  'management:student_list'))
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)},
                                        status=500)
                messages.error(request, f'Error updating parent: {e}')
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': form.errors},
                                    status=400)
        return render(request, self.template_name, {
            'parent': parent, 'form': form,
        })


class ParentDeleteView(ManagementRequiredMixin, View):
    """Delete a parent only if not linked to any students. AJAX only."""

    def delete(self, request, parent_pk):
        parent = get_object_or_404(Parent, pk=parent_pk)
        linked = parent.students.count()
        if linked:
            return JsonResponse({
                'success': False,
                'error': (
                    f'Cannot delete {parent.full_name} — '
                    f'linked to {linked} student(s).'
                )
            }, status=400)
        try:
            name = parent.full_name
            parent.delete()
            return JsonResponse({'success': True,
                                  'message': f'{name} deleted successfully.'})
        except Exception as e:
            logger.error('ParentDelete error: %s', e, exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class GetParentDetailsView(ManagementRequiredMixin, View):
    """AJAX — return parent details as JSON for the edit modal."""

    def get(self, request, parent_pk):
        parent = get_object_or_404(Parent, pk=parent_pk)
        return JsonResponse({
            'id': parent.pk,
            'full_name': parent.full_name,
            'relationship': parent.relationship,
            'phone_number': parent.phone_number,
            'alternate_phone': parent.alternate_phone or '',
            'email': parent.email or '',
            'address': parent.address or '',
        })


class ParentListView(ManagementRequiredMixin, ListView):
    """List all parents/guardians with search support."""
    model = Parent
    template_name = 'portal_management/students/parent_list.html'
    context_object_name = 'parents'
    paginate_by = 20

    def get_queryset(self):
        qs = Parent.objects.prefetch_related('students').order_by('full_name')
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(email__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total'] = Parent.objects.count()
        ctx['search'] = self.request.GET.get('search', '')
        return ctx


class ParentCreateView(ManagementRequiredMixin, View):
    """Create a standalone parent record (not yet linked to any student)."""
    template_name = 'portal_management/students/parent_form.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form': ParentForm(),
            'title': 'Add Parent / Guardian',
        })

    def post(self, request):
        form = ParentForm(request.POST)
        if form.is_valid():
            parent = form.save()
            messages.success(request, f'Parent {parent.full_name} added.')
            return redirect('management:parent_list')
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add Parent / Guardian',
        })


class ParentUpdateView(ManagementRequiredMixin, View):
    """Update a parent/guardian record."""
    template_name = 'portal_management/parents/form.html'

    def get(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        return render(request, self.template_name, {
            'form': ParentForm(instance=parent),
            'parent': parent,
            'title': f'Edit — {parent.full_name}',
            'action': 'Update',
        })

    def post(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        form = ParentForm(request.POST, instance=parent)
        if form.is_valid():
            try:
                parent = form.save()
                messages.success(
                    request, f'Parent {parent.full_name} updated successfully.'
                )
                return redirect('management:parent_list')
            except Exception as e:
                messages.error(request, f'Error updating parent: {e}')
                logger.error('ParentUpdate error: %s', e, exc_info=True)
        else:
            messages.error(request, 'Please correct the errors below.')
        return render(request, self.template_name, {
            'form': form,
            'parent': parent,
            'title': f'Edit — {parent.full_name}',
            'action': 'Update',
        })


# ════════════════════════════════════════════════════════════════════════════
# AJAX HELPERS
# ════════════════════════════════════════════════════════════════════════════

class SearchParentsView(ManagementRequiredMixin, View):
    """AJAX — search parents by name or phone. Requires ?q= (min 2 chars)."""

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse([], safe=False)
        parents = Parent.objects.filter(
            Q(full_name__icontains=query) |
            Q(phone_number__icontains=query)
        ).order_by('full_name')[:10]
        return JsonResponse([{
            'id': p.pk,
            'full_name': p.full_name,
            'phone_number': p.phone_number,
            'email': p.email or '',
            'relationship': p.get_relationship_display(),
            'initials': p.full_name[:2].upper(),
        } for p in parents], safe=False)


class GetStreamsView(ManagementRequiredMixin, View):
    """AJAX — return streams for a class level. Requires ?class_level_id=."""

    def get(self, request):
        class_level_id = request.GET.get('class_level_id')
        if not class_level_id:
            return JsonResponse([], safe=False)
        streams = StreamClass.objects.filter(
            class_level_id=class_level_id
        ).order_by('stream_letter')
        return JsonResponse([{
            'id': s.pk,
            'name': s.name or str(s),
            'capacity': s.capacity,
            'student_count': s.student_count,
            'available': s.capacity - s.student_count,
        } for s in streams], safe=False)


class GetCombinationsView(ManagementRequiredMixin, View):
    """AJAX — return A-Level combinations for a class level. Requires ?class_level_id=."""

    def get(self, request):
        class_level_id = request.GET.get('class_level_id')
        if not class_level_id:
            return JsonResponse([], safe=False)
        cl = get_object_or_404(
            ClassLevel.objects.select_related('educational_level'),
            pk=class_level_id
        )
        if cl.educational_level.level_type != 'A_LEVEL':
            return JsonResponse([], safe=False)
        combos = Combination.objects.filter(
            educational_level=cl.educational_level
        ).order_by('code')
        return JsonResponse([{
            'id': c.pk,
            'name': c.name,
            'code': c.code,
            'display': f'{c.code} — {c.name}',
        } for c in combos], safe=False)


