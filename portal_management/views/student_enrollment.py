"""
portal_management/views/student_enrollment.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
All enrollment-related views for student enrollment management.

This file contains views for:
  - Listing enrollments with filtering
  - Creating new enrollments
  - Viewing enrollment details
  - Updating enrollments
  - Updating enrollment status
  - Promoting students
  - Deleting enrollments
  - Stream assignment for enrollments
  - Combination assignment for A-Level enrollments
  - AJAX helper views for enrollment forms
"""

import logging
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, OuterRef, Subquery, CharField
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, TemplateView, View

from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, ClassLevel, Combination, StreamClass, 
    Student, StudentEnrollment, StudentStreamAssignment,
    StudentCombinationAssignment, StudentSubjectAssignment
)
from portal_management.forms.student_form import StudentEnrollmentForm

logger = logging.getLogger(__name__)


# ============================================================================
# ENROLLMENT LIST VIEW
# ============================================================================

class StudentEnrollmentListView(ManagementRequiredMixin, TemplateView):
    """List all student enrollments with filtering capabilities."""
    template_name = 'portal_management/students/enrollments.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters from request
        academic_year_id = self.request.GET.get('academic_year')
        class_level_id = self.request.GET.get('class_level')
        status_filter = self.request.GET.get('status')
        student_id = self.request.GET.get('student')
        
        # Subquery to get active combination code
        active_combination_subquery = Combination.objects.filter(
            student_assignments__enrollment=OuterRef('pk'),
            student_assignments__is_active=True
        ).values('code')[:1]
        
        # Subquery to get stream name
        stream_name_subquery = StreamClass.objects.filter(
            stream_assignments__enrollment=OuterRef('pk')
        ).values('name')[:1]
        
        # Base queryset with annotations for efficient querying
        enrollments = StudentEnrollment.objects.select_related(
            'student', 'academic_year', 'class_level'
        ).annotate(
            stream_name=Subquery(stream_name_subquery, output_field=CharField()),
            active_combination_code=Subquery(active_combination_subquery, output_field=CharField())
        ).prefetch_related(
            'stream_assignment__stream_class',
            'combination_assignments__combination'
        ).order_by('-academic_year__start_date', 'class_level__order', 'student__first_name')
        
        # Apply filters if provided
        if academic_year_id:
            enrollments = enrollments.filter(academic_year_id=academic_year_id)
        if class_level_id:
            enrollments = enrollments.filter(class_level_id=class_level_id)
        if status_filter:
            enrollments = enrollments.filter(status=status_filter)
        if student_id:
            enrollments = enrollments.filter(student_id=student_id)
        
        ctx['enrollments'] = enrollments
        ctx['total_enrollments'] = enrollments.count()
        
        # Statistics for dashboard
        ctx['active_count'] = enrollments.filter(status='active').count()
        ctx['promoted_count'] = enrollments.filter(status='promoted').count()
        ctx['completed_count'] = enrollments.filter(status='completed').count()
        
        # Get filter options for dropdowns
        ctx['academic_years'] = AcademicYear.objects.all().order_by('-start_date')
        ctx['class_levels'] = ClassLevel.objects.all().order_by('educational_level', 'order')
        ctx['students'] = Student.objects.filter(status='active').order_by('first_name', 'last_name')
        
        # Store selected filters for template
        ctx['selected_academic_year'] = int(academic_year_id) if academic_year_id else None
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['selected_status'] = status_filter
        ctx['selected_student'] = int(student_id) if student_id else None
        
        return ctx


# ============================================================================
# ENROLLMENT CREATE VIEW
# ============================================================================

class StudentEnrollmentCreateView(ManagementRequiredMixin, View):
    """Create a new student enrollment."""
    template_name = 'portal_management/students/enrollment_form.html'
    
    def get(self, request):
        """Display the enrollment creation form."""
        form = StudentEnrollmentForm(initial={
            'enrollment_date': timezone.now().date()
        })
        
        # If student_id is provided in URL, pre-select that student
        student_id = request.GET.get('student')
        if student_id:
            try:
                student = Student.objects.get(pk=student_id)
                form.fields['student'].initial = student
                form.fields['student'].queryset = Student.objects.filter(pk=student_id)
            except Student.DoesNotExist:
                pass
        
        return render(request, self.template_name, {
            'form': form,
            'title': 'New Student Enrollment',
            'action': 'Create'
        })
    
    def post(self, request):
        """Process the enrollment creation form."""
        form = StudentEnrollmentForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save()
                    
                    success_message = (
                        f'{enrollment.student.full_name} enrolled in '
                        f'{enrollment.class_level.name} for {enrollment.academic_year.name}.'
                    )
                    messages.success(request, success_message)
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': 'Enrollment created successfully.',
                            'redirect_url': reverse(
                                'management:student_enrollment_detail', 
                                kwargs={'pk': enrollment.pk}
                            )
                        })
                    
                    # Determine redirect based on submit action
                    next_action = request.POST.get('action', 'save')
                    if next_action == 'save_add_another':
                        return redirect('management:student_enrollment_create')
                    elif next_action == 'save_stream':
                        return redirect('management:student_enrollment_stream', pk=enrollment.pk)
                    else:
                        return redirect('management:student_enrollment_detail', pk=enrollment.pk)
                        
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f'Validation error: {error_msg}')
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': form.errors
                    }, status=400)
                    
            except Exception as e:
                messages.error(request, f'Error creating enrollment: {e}')
                logger.error(f"Enrollment creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
        
        return render(request, self.template_name, {
            'form': form,
            'title': 'New Student Enrollment',
            'action': 'Create'
        })


# ============================================================================
# ENROLLMENT DETAIL VIEW
# ============================================================================

class StudentEnrollmentDetailView(ManagementRequiredMixin, DetailView):
    """View detailed information about a specific enrollment."""
    model = StudentEnrollment
    template_name = 'portal_management/students/enrollment_detail.html'
    context_object_name = 'enrollment'
    
    def get_context_data(self, **kwargs):
        """Add additional context data for the detail view."""
        ctx = super().get_context_data(**kwargs)
        enrollment = self.object
        
        # Get stream information if assigned
        ctx['stream'] = enrollment.stream_assignment.stream_class if hasattr(enrollment, 'stream_assignment') else None
        
        # Get current combination information
        ctx['current_combination'] = enrollment.current_combination
        
        # Get the active combination assignment explicitly
        ctx['active_combination_assignment'] = enrollment.combination_assignments.filter(is_active=True).first()
        
        # Get combination assignment history (last 5)
        ctx['combination_history'] = enrollment.combination_assignments.select_related('combination').order_by('-assigned_date')[:5]
        
        # Get subject assignments for O-Level students
        if enrollment.class_level.educational_level.level_type == 'O_LEVEL':
            ctx['subject_assignments'] = StudentSubjectAssignment.objects.filter(
                enrollment=enrollment
            ).select_related('subject')
        
        return ctx


# ============================================================================
# ENROLLMENT UPDATE VIEW
# ============================================================================

class StudentEnrollmentUpdateView(ManagementRequiredMixin, View):
    """Update an existing enrollment's details and status."""
    template_name = 'portal_management/students/enrollment_form.html'
    
    def get(self, request, pk):
        """Display the enrollment update form."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        form = StudentEnrollmentForm(instance=enrollment)
        
        return render(request, self.template_name, {
            'form': form,
            'enrollment': enrollment,
            'title': f'Update Enrollment - {enrollment.student.full_name}',
            'action': 'Update'
        })
    
    def post(self, request, pk):
        """Process the enrollment update form."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        form = StudentEnrollmentForm(request.POST, instance=enrollment)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    enrollment = form.save()
                    
                    messages.success(request, f'Enrollment updated successfully.')
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': 'Enrollment updated successfully.',
                            'redirect_url': reverse(
                                'management:student_enrollment_detail', 
                                kwargs={'pk': enrollment.pk}
                            )
                        })
                    
                    return redirect('management:student_enrollment_detail', pk=enrollment.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                messages.error(request, f'Validation error: {error_msg}')
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': form.errors
                    }, status=400)
                    
            except Exception as e:
                messages.error(request, f'Error updating enrollment: {e}')
                logger.error(f"Enrollment update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
        
        return render(request, self.template_name, {
            'form': form,
            'enrollment': enrollment,
            'title': f'Update Enrollment - {enrollment.student.full_name}',
            'action': 'Update'
        })


# ============================================================================
# ENROLLMENT STATUS UPDATE VIEW
# ============================================================================

class StudentEnrollmentStatusUpdateView(ManagementRequiredMixin, View):
    """
    Update enrollment status with proper validation and error handling.
    Supports individual status changes without affecting other records.
    """

    def post(self, request, pk):
        """Process the status update request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        new_status = request.POST.get('status')
        remarks = request.POST.get('remarks', '')

        # Validate required fields
        if not new_status:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'status': ['Status is required.']},
                    'message': 'Status is required.'
                }, status=400)
            messages.error(request, 'Status is required.')
            return redirect('management:student_enrollment_detail', pk=pk)

        try:
            old_status = enrollment.status
            enrollment.status = new_status
            if remarks:
                enrollment.remarks = remarks

            enrollment.full_clean()
            enrollment.save()

            message = f'Enrollment status updated from {old_status} to {new_status}.'

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'enrollment': {
                        'id': enrollment.pk,
                        'status': enrollment.status,
                        'status_display': enrollment.get_status_display(),
                        'remarks': enrollment.remarks,
                    }
                })

            messages.success(request, message)
            return redirect('management:student_enrollment_detail', pk=pk)

        except ValidationError as e:
            logger.error(f"Status update validation error: {e}", exc_info=True)
            if is_ajax:
                error_dict = {}
                if hasattr(e, 'message_dict'):
                    error_dict = e.message_dict
                elif hasattr(e, 'messages'):
                    error_dict = {'__all__': e.messages}
                else:
                    error_dict = {'__all__': [str(e)]}
                
                return JsonResponse({
                    'success': False,
                    'errors': error_dict,
                    'message': '; '.join([msg for msgs in error_dict.values() for msg in msgs])
                }, status=400)
            
            for error in e.messages if hasattr(e, 'messages') else [str(e)]:
                messages.error(request, error)
            return redirect('management:student_enrollment_detail', pk=pk)

        except Exception as e:
            logger.error(f"Status update error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)
            
            messages.error(request, f'Error updating status: {e}')
            return redirect('management:student_enrollment_detail', pk=pk)


# ============================================================================
# ENROLLMENT PROMOTE VIEW
# ============================================================================

class StudentEnrollmentPromoteView(ManagementRequiredMixin, View):
    """
    Promote a student to the next class level.
    Creates a new enrollment for the next academic year and class level
    while marking the current enrollment as promoted.
    """

    def post(self, request, pk):
        """Process the promotion request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Get next class level within the same educational level
        current_level = enrollment.class_level
        next_level = ClassLevel.objects.filter(
            educational_level=current_level.educational_level,
            order__gt=current_level.order
        ).order_by('order').first()

        if not next_level:
            message = 'No higher class level available. Consider marking as completed.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [message]},
                    'message': message
                }, status=400)
            messages.error(request, message)
            return redirect('management:student_enrollment_detail', pk=pk)

        # Get next academic year
        current_year = enrollment.academic_year
        next_year = AcademicYear.objects.filter(
            start_date__gt=current_year.start_date
        ).order_by('start_date').first()

        if not next_year:
            message = 'No future academic year available.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [message]},
                    'message': message
                }, status=400)
            messages.error(request, message)
            return redirect('management:student_enrollment_detail', pk=pk)

        try:
            with transaction.atomic():
                # Mark current enrollment as promoted
                enrollment.status = 'promoted'
                enrollment.save()

                # Create new enrollment for next year
                new_enrollment = StudentEnrollment.objects.create(
                    student=enrollment.student,
                    academic_year=next_year,
                    class_level=next_level,
                    enrollment_date=timezone.now().date(),
                    status='active',
                    remarks=f'Promoted from {enrollment.class_level.name} ({enrollment.academic_year.name})'
                )

                # Copy stream assignment if exists
                if hasattr(enrollment, 'stream_assignment') and enrollment.stream_assignment:
                    # Find appropriate stream in new class level (same letter)
                    stream_letter = enrollment.stream_assignment.stream_class.stream_letter
                    new_stream = StreamClass.objects.filter(
                        class_level=next_level,
                        stream_letter=stream_letter
                    ).first()
                    
                    if new_stream:
                        StudentStreamAssignment.objects.create(
                            enrollment=new_enrollment,
                            stream_class=new_stream,
                            assigned_date=timezone.now().date(),
                            remarks='Auto-assigned from promotion'
                        )

                # Copy combination assignment if A-Level
                if enrollment.class_level.educational_level.level_type == 'A_LEVEL':
                    active_combination = enrollment.combination_assignments.filter(is_active=True).first()
                    if active_combination:
                        StudentCombinationAssignment.objects.create(
                            student=enrollment.student,
                            enrollment=new_enrollment,
                            combination=active_combination.combination,
                            assigned_date=timezone.now().date(),
                            remarks='Carried over from previous enrollment',
                            is_active=True
                        )

                message = f'{enrollment.student.full_name} promoted to {next_level.name} for {next_year.name}.'

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'new_enrollment_id': new_enrollment.pk
                    })

                messages.success(request, message)
                return redirect('management:student_enrollment_detail', pk=new_enrollment.pk)

        except ValidationError as e:
            logger.error(f"Promotion validation error: {e}", exc_info=True)
            if is_ajax:
                error_dict = {}
                if hasattr(e, 'message_dict'):
                    error_dict = e.message_dict
                elif hasattr(e, 'messages'):
                    error_dict = {'__all__': e.messages}
                else:
                    error_dict = {'__all__': [str(e)]}
                
                return JsonResponse({
                    'success': False,
                    'errors': error_dict,
                    'message': '; '.join([msg for msgs in error_dict.values() for msg in msgs])
                }, status=400)
            
            for error in e.messages if hasattr(e, 'messages') else [str(e)]:
                messages.error(request, error)
            return redirect('management:student_enrollment_detail', pk=pk)

        except Exception as e:
            logger.error(f"Promotion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)
            
            messages.error(request, f'Error promoting student: {e}')
            return redirect('management:student_enrollment_detail', pk=pk)


# ============================================================================
# ENROLLMENT DELETE VIEW
# ============================================================================

class StudentEnrollmentDeleteView(ManagementRequiredMixin, View):
    """
    Delete an enrollment only if no dependencies exist.
    Prevents deletion if the enrollment has associated records.
    """

    def post(self, request, pk):
        """Process the deletion request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Check for dependencies that would prevent deletion
        dependency_errors = []

        if hasattr(enrollment, 'stream_assignment'):
            dependency_errors.append('stream assignment')

        if enrollment.combination_assignments.exists():
            dependency_errors.append('combination assignments')

        if enrollment.subject_assignments.exists():
            dependency_errors.append('subject assignments')

        if enrollment.paper_scores.exists():
            dependency_errors.append('exam scores')

        if dependency_errors:
            error_msg = f'Cannot delete enrollment that has: {", ".join(dependency_errors)}.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [error_msg]},
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:student_enrollment_detail', pk=pk)

        try:
            student_name = enrollment.student.full_name
            class_name = enrollment.class_level.name
            year_name = enrollment.academic_year.name
            enrollment.delete()

            message = f'Enrollment for {student_name} in {class_name} ({year_name}) deleted.'

            if is_ajax:
                return JsonResponse({'success': True, 'message': message})

            messages.success(request, message)
            return redirect('management:student_enrollment_list')

        except Exception as e:
            logger.error(f"Enrollment deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)
            
            messages.error(request, f'Error deleting enrollment: {e}')
            return redirect('management:student_enrollment_detail', pk=pk)


# ============================================================================
# STREAM ASSIGNMENT VIEWS
# ============================================================================

class StudentEnrollmentStreamView(ManagementRequiredMixin, View):
    """
    Assign or update a stream for an enrollment.
    Handles both creation and update of stream assignments with capacity validation.
    Returns JSON response with clear error messages.
    """

    def post(self, request, pk):
        """Process stream assignment request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        try:
            with transaction.atomic():
                stream_id = request.POST.get('stream_id')
                assigned_date = request.POST.get('assigned_date', timezone.now().date())
                remarks = request.POST.get('remarks', '')

                if not stream_id:
                    raise ValidationError({'stream_id': ['Please select a stream.']})

                stream = get_object_or_404(StreamClass, pk=stream_id)

                # Validate stream belongs to the enrollment's class level
                if stream.class_level_id != enrollment.class_level_id:
                    raise ValidationError({
                        'stream_id': [f'Stream "{stream}" does not belong to the class level "{enrollment.class_level.name}".']
                    })

                # Check stream capacity
                current_count = StudentStreamAssignment.objects.filter(
                    stream_class=stream,
                    enrollment__academic_year=enrollment.academic_year
                ).count()

                # If updating an existing assignment, exclude current student from count
                if hasattr(enrollment, 'stream_assignment'):
                    if enrollment.stream_assignment.stream_class_id == stream.id:
                        # Same stream - no capacity change
                        current_count -= 1

                if current_count >= stream.capacity:
                    raise ValidationError({
                        'stream_id': [f'Stream "{stream.name}" has reached maximum capacity ({stream.capacity} students). Available: 0']
                    })

                # Create or update assignment
                if hasattr(enrollment, 'stream_assignment'):
                    assignment = enrollment.stream_assignment
                    old_stream = assignment.stream_class.name
                    assignment.stream_class = stream
                    assignment.assigned_date = assigned_date
                    assignment.remarks = remarks
                    assignment.save()
                    message = f'Stream assignment updated from {old_stream} to {stream.name}.'
                else:
                    assignment = StudentStreamAssignment.objects.create(
                        enrollment=enrollment,
                        stream_class=stream,
                        assigned_date=assigned_date,
                        remarks=remarks
                    )
                    message = f'{enrollment.student.full_name} assigned to stream {stream.name}.'

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'data': {
                            'stream_id': stream.id,
                            'stream_name': stream.name,
                            'assigned_date': assigned_date,
                            'remarks': remarks
                        }
                    })

                messages.success(request, message)
                return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except ValidationError as e:
            logger.error(f"Stream assignment validation error: {e}", exc_info=True)
            if is_ajax:
                # Format errors for JSON response
                error_dict = {}
                if hasattr(e, 'message_dict'):
                    error_dict = e.message_dict
                elif hasattr(e, 'messages'):
                    error_dict = {'__all__': e.messages}
                else:
                    error_dict = {'__all__': [str(e)]}
                
                return JsonResponse({
                    'success': False,
                    'errors': error_dict,
                    'message': '; '.join([msg for msgs in error_dict.values() for msg in msgs])
                }, status=400)
            
            for field, errors in e.message_dict.items():
                for error in errors:
                    messages.error(request, error)
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except Exception as e:
            logger.error(f"Stream assignment error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)
            
            messages.error(request, f'Error assigning stream: {e}')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)


class StudentEnrollmentStreamRemoveView(ManagementRequiredMixin, View):
    """
    Remove a student from their stream assignment.
    Deletes the stream assignment record.
    """

    def post(self, request, pk):
        """Process stream removal request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Validate that a stream assignment exists
        if not hasattr(enrollment, 'stream_assignment'):
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': ['No stream assignment exists for this enrollment.']}
                }, status=400)
            
            messages.warning(request, 'No stream assignment exists for this enrollment.')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        try:
            stream_name = enrollment.stream_assignment.stream_class.name
            enrollment.stream_assignment.delete()

            message = f'{enrollment.student.full_name} removed from stream {stream_name}.'

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })

            messages.success(request, message)
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except Exception as e:
            logger.error(f"Stream removal error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)

            messages.error(request, f'Error removing stream: {e}')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)


# ============================================================================
# COMBINATION ASSIGNMENT VIEWS (A-Level only)
# ============================================================================

class StudentEnrollmentCombinationView(ManagementRequiredMixin, View):
    """
    Assign or update a combination for an A-Level enrollment.
    Handles both creation and update of combination assignments.
    Returns JSON response with clear error messages.
    """

    def post(self, request, pk):
        """Process combination assignment request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # Verify this is an A-Level enrollment
        if enrollment.class_level.educational_level.level_type != 'A_LEVEL':
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': ['Combination assignments are only applicable to A-Level students.']}
                }, status=400)
            
            messages.error(request, 'Combination assignments are only applicable to A-Level students.')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        try:
            with transaction.atomic():
                combination_id = request.POST.get('combination_id')
                assigned_date = request.POST.get('assigned_date', timezone.now().date())
                remarks = request.POST.get('remarks', '')

                if not combination_id:
                    raise ValidationError({'combination_id': ['Please select a combination.']})

                combination = get_object_or_404(Combination, pk=combination_id)

                # Verify combination belongs to the same educational level
                if combination.educational_level_id != enrollment.class_level.educational_level_id:
                    raise ValidationError({
                        'combination_id': [f'Combination "{combination.code}" does not belong to the educational level "{enrollment.class_level.educational_level.name}".']
                    })

                # Check if there's already an active assignment
                existing_active = StudentCombinationAssignment.objects.filter(
                    enrollment=enrollment,
                    is_active=True
                ).first()

                if existing_active:
                    # If the same combination is being assigned again, just update the existing one
                    if existing_active.combination_id == combination.id:
                        existing_active.assigned_date = assigned_date
                        existing_active.remarks = remarks
                        existing_active.save()
                        
                        message = f'Combination assignment updated for {combination.code}.'
                        
                        if is_ajax:
                            return JsonResponse({
                                'success': True,
                                'message': message,
                                'data': {
                                    'combination_id': combination.id,
                                    'combination_code': combination.code,
                                    'assigned_date': assigned_date,
                                    'remarks': remarks,
                                    'is_update': True
                                }
                            })
                        
                        messages.success(request, message)
                        return redirect('management:student_enrollment_detail', pk=enrollment.pk)
                    
                    # Deactivate the existing active assignment first
                    # This is done explicitly to avoid constraint violation during validation
                    existing_active.is_active = False
                    existing_active.save()

                # Create new assignment (now there's no active assignment)
                assignment = StudentCombinationAssignment.objects.create(
                    student=enrollment.student,
                    enrollment=enrollment,
                    combination=combination,
                    assigned_date=assigned_date,
                    remarks=remarks,
                    is_active=True
                )

                if existing_active:
                    message = f'Combination updated from {existing_active.combination.code} to {combination.code}.'
                else:
                    message = f'{enrollment.student.full_name} assigned to combination {combination.code}.'

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'data': {
                            'combination_id': combination.id,
                            'combination_code': combination.code,
                            'assigned_date': assigned_date,
                            'remarks': remarks,
                            'is_update': bool(existing_active)
                        }
                    })

                messages.success(request, message)
                return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except ValidationError as e:
            logger.error(f"Combination assignment validation error: {e}", exc_info=True)
            if is_ajax:
                error_dict = {}
                if hasattr(e, 'message_dict'):
                    error_dict = e.message_dict
                elif hasattr(e, 'messages'):
                    error_dict = {'__all__': e.messages}
                else:
                    error_dict = {'__all__': [str(e)]}
                
                # Format error message nicely
                error_messages = []
                for field, msgs in error_dict.items():
                    if field == '__all__':
                        error_messages.extend(msgs)
                    else:
                        field_name = field.replace('_', ' ').title()
                        error_messages.extend([f"{field_name}: {msg}" for msg in msgs])
                
                return JsonResponse({
                    'success': False,
                    'errors': error_dict,
                    'message': '; '.join(error_messages) if error_messages else str(e)
                }, status=400)
            
            for field, errors in e.message_dict.items():
                for error in errors:
                    messages.error(request, error)
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except Exception as e:
            logger.error(f"Combination assignment error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)
            
            messages.error(request, f'Error assigning combination: {e}')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)


class StudentEnrollmentCombinationRemoveView(ManagementRequiredMixin, View):
    """
    Remove/delete a combination assignment.
    Note: This hard-deletes the assignment. For soft-deactivation,
    assign a new combination instead.
    """

    def post(self, request, pk):
        """Process combination removal request."""
        enrollment = get_object_or_404(StudentEnrollment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        active_assignment = enrollment.combination_assignments.filter(is_active=True).first()

        if not active_assignment:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': ['No active combination assignment exists for this enrollment.']}
                }, status=400)
            
            messages.warning(request, 'No active combination assignment exists for this enrollment.')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        try:
            combination_code = active_assignment.combination.code
            active_assignment.delete()

            message = f'Combination {combination_code} removed from {enrollment.student.full_name}.'

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })

            messages.success(request, message)
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)

        except Exception as e:
            logger.error(f"Combination removal error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': [str(e)]},
                    'message': str(e)
                }, status=500)

            messages.error(request, f'Error removing combination: {e}')
            return redirect('management:student_enrollment_detail', pk=enrollment.pk)


# ============================================================================
# AJAX HELPER VIEWS
# ============================================================================

class GetAvailableClassLevelsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get available class levels for an educational level."""
    
    def get(self, request):
        """Return class levels filtered by educational level."""
        educational_level_id = request.GET.get('educational_level_id')
        exclude_final = request.GET.get('exclude_final') == 'true'
        
        if not educational_level_id:
            return JsonResponse({'class_levels': []})
        
        class_levels = ClassLevel.objects.filter(
            educational_level_id=educational_level_id
        ).order_by('order')
        
        if exclude_final:
            class_levels = class_levels.filter(is_final=False)
        
        data = [{
            'id': c.pk,
            'name': c.name,
            'code': c.code,
            'order': c.order,
            'is_final': c.is_final,
        } for c in class_levels]
        
        return JsonResponse({'class_levels': data})


class GetStudentEnrollmentHistoryView(ManagementRequiredMixin, View):
    """AJAX endpoint to get enrollment history for a student."""
    
    def get(self, request):
        """Return enrollment history for a specific student."""
        student_id = request.GET.get('student_id')
        
        if not student_id:
            return JsonResponse({'enrollments': []})
        
        enrollments = StudentEnrollment.objects.filter(
            student_id=student_id
        ).select_related(
            'academic_year', 'class_level'
        ).order_by('-academic_year__start_date')
        
        data = [{
            'id': e.pk,
            'academic_year': e.academic_year.name,
            'class_level': e.class_level.name,
            'status': e.get_status_display(),
            'status_code': e.status,
            'enrollment_date': e.enrollment_date.strftime('%Y-%m-%d'),
            'has_stream': hasattr(e, 'stream_assignment'),
            'has_combination': e.current_combination is not None,
            'combination_code': e.current_combination.code if e.current_combination else None,
        } for e in enrollments]
        
        return JsonResponse({'enrollments': data})


class SearchStudentsForEnrollmentView(ManagementRequiredMixin, View):
    """AJAX endpoint for Select2 to search students for enrollment."""
    
    def get(self, request):
        """Return paginated student search results for Select2."""
        search = request.GET.get('term', '')
        page = int(request.GET.get('page', 1))
        page_size = 20
        
        students = Student.objects.filter(status='active')
        
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(registration_number__icontains=search)
            )
        
        total = students.count()
        students = students[(page - 1) * page_size:page * page_size]
        
        results = [{
            'id': s.pk,
            'text': f"{s.full_name} ({s.registration_number})",
        } for s in students]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': total > page * page_size
            }
        })


class GetClassLevelsByAcademicYearView(ManagementRequiredMixin, View):
    """AJAX endpoint to get class levels based on selected academic year."""
    
    def get(self, request):
        """Return class levels for the selected academic year."""
        academic_year_id = request.GET.get('academic_year_id')
        
        if not academic_year_id:
            return JsonResponse({'results': []})
        
        try:
            academic_year = AcademicYear.objects.get(pk=academic_year_id)
        except AcademicYear.DoesNotExist:
            return JsonResponse({'results': []})
        
        # Get all class levels with educational level info
        class_levels = ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order')
        
        results = [{
            'id': c.pk,
            'text': f"{c.name} ({c.educational_level.name})",
        } for c in class_levels]
        
        return JsonResponse({'results': results})