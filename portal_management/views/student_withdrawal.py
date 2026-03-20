# portal_management/views/student_withdrawal.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    Student, StudentSuspension, StudentWithdrawal, StudentEnrollment, 
    ClassLevel, AcademicYear, Staff
)
from portal_management.forms.student_withdrawal_form import StudentWithdrawalForm

logger = logging.getLogger(__name__)


class StudentWithdrawalListView(ManagementRequiredMixin, TemplateView):
    """List all student withdrawal records with filtering."""
    template_name = 'portal_management/students/withdrawals/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        academic_year_id = self.request.GET.get('academic_year')
        class_level_id = self.request.GET.get('class_level')
        reason_filter = self.request.GET.get('reason')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset
        withdrawals = StudentWithdrawal.objects.select_related(
            'student',
            'last_class_level',
            'last_academic_year',
            'authorised_by__user'
        ).order_by('-withdrawal_date', '-created_at')
        
        # Apply filters
        if academic_year_id:
            withdrawals = withdrawals.filter(last_academic_year_id=academic_year_id)
        
        if class_level_id:
            withdrawals = withdrawals.filter(last_class_level_id=class_level_id)
        
        if reason_filter:
            withdrawals = withdrawals.filter(reason=reason_filter)
        
        if search_query:
            withdrawals = withdrawals.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query)
            )
        
        ctx['withdrawals'] = withdrawals
        ctx['total_withdrawals'] = withdrawals.count()
        
        # Statistics
        ctx['withdrawals_this_year'] = withdrawals.filter(
            withdrawal_date__year=timezone.now().year
        ).count()
        
        # Get unique reasons count
        ctx['unique_reasons'] = withdrawals.values('reason').distinct().count()
        
        # Get filter options
        ctx['academic_years'] = AcademicYear.objects.all().order_by('-start_date')
        ctx['class_levels'] = ClassLevel.objects.all().order_by('educational_level', 'order')
        ctx['reason_choices'] = StudentWithdrawal.REASON_CHOICES
        
        # Store selected filters
        ctx['selected_academic_year'] = int(academic_year_id) if academic_year_id else None
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['selected_reason'] = reason_filter
        ctx['search_query'] = search_query
        
        return ctx


class StudentWithdrawalCreateView(ManagementRequiredMixin, View):
    """Create a new student withdrawal record."""
    template_name = 'portal_management/students/withdrawals/form.html'
    
    def get_eligible_students(self):
        """Get all students eligible for withdrawal with their enrollment info."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return Student.objects.none()
        
        # Get students with active enrollment in current academic year
        # and no existing withdrawal or transfer record
        eligible_students = Student.objects.filter(
            status='active',
            enrollments__status='active',
            enrollments__academic_year=current_academic_year,
            withdrawal__isnull=True,
            transfer_out__isnull=True
        ).select_related(
            'user'
        ).prefetch_related(
            'enrollments__class_level',
            'enrollments__academic_year',
            'enrollments__stream_assignment__stream_class'
        ).distinct().order_by('first_name', 'last_name')
        
        # Annotate each student with their current enrollment info
        for student in eligible_students:
            # Get the active enrollment for current academic year
            active_enrollment = None
            for enrollment in student.enrollments.all():
                if (enrollment.status == 'active' and 
                    enrollment.academic_year_id == current_academic_year.pk):
                    active_enrollment = enrollment
                    break
            
            student.current_class_name = active_enrollment.class_level.name if active_enrollment else 'No class'
            student.current_class_id = active_enrollment.class_level_id if active_enrollment else None
            student.current_academic_year_name = active_enrollment.academic_year.name if active_enrollment else current_academic_year.name
            student.current_academic_year_id = active_enrollment.academic_year_id if active_enrollment else current_academic_year.pk
            
            # Get stream info
            if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment:
                student.current_stream = active_enrollment.stream_assignment.stream_class.name
            else:
                student.current_stream = 'Not assigned'
        
        return eligible_students
    
    def get_staff_members(self):
        """Get all active staff members for the authorised_by dropdown."""
        return Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
    
    def get(self, request, student_id=None):
        initial = {}
        student = None
        active_enrollment = None
        pre_selected_student_data = None
        
        # If student_id is provided, pre-fill student data
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            
            # Check if student already has a withdrawal record
            if hasattr(student, 'withdrawal'):
                messages.warning(
                    request, 
                    f'{student.full_name} already has a withdrawal record. You can edit it instead.'
                )
                return redirect('management:student_withdrawal_update', pk=student.withdrawal.pk)
            
            # Check if student has a transfer record (mutually exclusive)
            if hasattr(student, 'transfer_out'):
                messages.error(
                    request,
                    f'{student.full_name} already has a transfer out record. '
                    f'A student cannot be both transferred and withdrawn.'
                )
                return redirect('management:student_detail', pk=student.pk)
            
            # Get current active academic year
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            if not current_academic_year:
                messages.error(
                    request,
                    'No active academic year configured. Please set an active academic year before processing withdrawals.'
                )
                return redirect('management:student_detail', pk=student.pk)
            
            # Check if student has active enrollment in current academic year
            active_enrollment = student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).select_related(
                'class_level', 'academic_year'
            ).prefetch_related(
                'stream_assignment__stream_class'
            ).first()
            
            if not active_enrollment:
                messages.error(
                    request,
                    f'{student.full_name} does not have an active enrollment in {current_academic_year.name}. '
                    f'Only actively enrolled students can be withdrawn.'
                )
                return redirect('management:student_detail', pk=student.pk)
            
            # Prepare pre-selected student data for the template
            pre_selected_student_data = {
                'id': student.pk,
                'full_name': student.full_name,
                'registration_number': student.registration_number,
                'current_class': active_enrollment.class_level.name,
                'current_class_id': active_enrollment.class_level_id,
                'current_academic_year': active_enrollment.academic_year.name,
                'current_academic_year_id': active_enrollment.academic_year_id,
                'current_stream': active_enrollment.stream_assignment.stream_class.name if hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
            }
            
            initial = {
                'student': student,
                'withdrawal_date': timezone.now().date(),
                'authorised_by': getattr(request.user, 'staff_profile', None),
            }
        
        form = StudentWithdrawalForm(initial=initial)
        
        # If student is pre-selected, set the display fields
        if student and active_enrollment:
            form.initial['current_class'] = active_enrollment.class_level.name
            form.initial['last_class_level'] = active_enrollment.class_level_id
            form.initial['last_academic_year'] = active_enrollment.academic_year_id
            
            stream_name = active_enrollment.stream_assignment.stream_class.name if hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned'
            form.initial['current_stream'] = stream_name
            
            form.initial['current_academic_year'] = active_enrollment.academic_year.name
        
        # Get all data for dropdowns
        eligible_students = self.get_eligible_students()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'eligible_students': eligible_students,
            'staff_members': staff_members,
            'title': 'Record Student Withdrawal',
            'is_update': False
        })
    
    def post(self, request):
        form = StudentWithdrawalForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Withdrawal creation POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    withdrawal = form.save(commit=False)
                    
                    # Set authorised_by to current staff if not provided
                    if not withdrawal.authorised_by and hasattr(request.user, 'staff_profile'):
                        withdrawal.authorised_by = request.user.staff_profile
                    
                    withdrawal.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # Update student status to withdrawn
                    student = withdrawal.student
                    student.status = 'withdrawn'
                    student.save(update_fields=['status'])
                    
                    # Update all active enrollments for current academic year to 'withdrawn'
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year,
                            status='active'
                        ).update(status='withdrawn')
                    
                    message = f'Withdrawal record for {withdrawal.student.full_name} created successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_withdrawal_detail', kwargs={'pk': withdrawal.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_withdrawal_detail', pk=withdrawal.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Withdrawal creation validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Withdrawal creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating withdrawal record: {e}')
        else:
            logger.debug(f"Form errors: {form.errors}")
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} error{"s" if error_count > 1 else ""} below.'
            )
        
        # Get all data for dropdowns for re-render
        eligible_students = self.get_eligible_students()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'eligible_students': eligible_students,
            'staff_members': staff_members,
            'title': 'Record Student Withdrawal',
            'is_update': False
        })


class StudentWithdrawalDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a student withdrawal."""
    template_name = 'portal_management/students/withdrawals/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        withdrawal = get_object_or_404(
            StudentWithdrawal.objects.select_related(
                'student',
                'last_class_level__educational_level',
                'last_academic_year',
                'authorised_by__user'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['withdrawal'] = withdrawal
        ctx['student'] = withdrawal.student
        
        # Get student's enrollment history
        ctx['enrollments'] = withdrawal.student.enrollments.select_related(
            'academic_year', 'class_level'
        ).order_by('-academic_year__start_date')[:5]
        
        return ctx


class StudentWithdrawalUpdateView(ManagementRequiredMixin, View):
    """Update an existing student withdrawal record."""
    template_name = 'portal_management/students/withdrawals/form.html'
    
    def get_staff_members(self):
        """Get all active staff members for the authorised_by dropdown."""
        return Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
    
    def get(self, request, pk):
        withdrawal = get_object_or_404(StudentWithdrawal, pk=pk)
        form = StudentWithdrawalForm(instance=withdrawal)
        
        # Disable student field (cannot change student for existing withdrawal)
        form.fields['student'].disabled = True
        form.fields['student'].widget.attrs['disabled'] = True
        form.fields['student'].queryset = Student.objects.filter(pk=withdrawal.student_id)
        
        # Get active enrollment for display
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        active_enrollment = None
        
        if current_academic_year:
            active_enrollment = withdrawal.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).select_related(
                'class_level', 'academic_year'
            ).prefetch_related(
                'stream_assignment__stream_class'
            ).first()
        
        # Prepare pre-selected student data for the template
        pre_selected_student_data = {
            'id': withdrawal.student.pk,
            'full_name': withdrawal.student.full_name,
            'registration_number': withdrawal.student.registration_number,
            'current_class': active_enrollment.class_level.name if active_enrollment else withdrawal.last_class_level.name if withdrawal.last_class_level else 'N/A',
            'current_academic_year': active_enrollment.academic_year.name if active_enrollment else withdrawal.last_academic_year.name if withdrawal.last_academic_year else 'N/A',
            'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
        }
        
        # Get all data for dropdowns
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'withdrawal': withdrawal,
            'student': withdrawal.student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'staff_members': staff_members,
            'title': f'Edit Withdrawal - {withdrawal.student.full_name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        withdrawal = get_object_or_404(StudentWithdrawal, pk=pk)
        form = StudentWithdrawalForm(request.POST, instance=withdrawal)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Withdrawal update POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Store student reference before save
                    student = withdrawal.student
                    
                    # Save the withdrawal
                    withdrawal = form.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # Check if student still has a withdrawal record (they do, it's this one)
                    # No need to update status as it should remain 'withdrawn'
                    
                    # Update enrollment status to ensure consistency
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year,
                            status='active'
                        ).update(status='withdrawn')
                    
                    message = f'Withdrawal record updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_withdrawal_detail', kwargs={'pk': withdrawal.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_withdrawal_detail', pk=withdrawal.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Withdrawal update validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Withdrawal update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating withdrawal record: {e}')
        else:
            logger.debug(f"Form errors: {form.errors}")
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} error{"s" if error_count > 1 else ""} below.'
            )
        
        # Re-disable student field
        form.fields['student'].disabled = True
        form.fields['student'].widget.attrs['disabled'] = True
        form.fields['student'].queryset = Student.objects.filter(pk=withdrawal.student_id)
        
        # Get active enrollment for display
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        active_enrollment = None
        
        if current_academic_year:
            active_enrollment = withdrawal.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).first()
        
        # Get all data for dropdowns
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'withdrawal': withdrawal,
            'student': withdrawal.student,
            'active_enrollment': active_enrollment,
            'staff_members': staff_members,
            'title': f'Edit Withdrawal - {withdrawal.student.full_name}',
            'is_update': True
        })


# portal_management/views/student_withdrawal.py

class StudentWithdrawalDeleteView(ManagementRequiredMixin, View):
    """Delete a student withdrawal record."""
    
    def _calculate_student_status(self, student):
        """
        Calculate the appropriate status for a student based on their records.
        Returns a tuple of (student_status, enrollment_status)
        """
        # Check for transfer (highest priority)
        if hasattr(student, 'transfer_out'):
            return 'transferred', 'transferred'
        
        # Check for active suspensions
        has_active_suspension = StudentSuspension.objects.filter(
            student=student,
            is_lifted=False
        ).exists()
        
        if has_active_suspension:
            return 'suspended', 'suspended'
        
        # Check for active enrollments
        has_active_enrollment = StudentEnrollment.objects.filter(
            student=student,
            status='active'
        ).exists()
        
        if has_active_enrollment:
            return 'active', 'active'
        
        # Default to active (can be re-enrolled)
        return 'active', 'active'
    
    def post(self, request, pk):
        withdrawal = get_object_or_404(StudentWithdrawal, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = withdrawal.student.full_name
            student = withdrawal.student
            
            with transaction.atomic():
                # Store the last class level and academic year before deletion
                # (for logging purposes if needed)
                last_class = withdrawal.last_class_level
                last_year = withdrawal.last_academic_year
                
                # Delete the withdrawal record
                withdrawal.delete()
                
                # Get current active academic year
                current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                
                # Calculate new status
                new_status, enrollment_status = self._calculate_student_status(student)
                
                # Update student status
                student.status = new_status
                student.save(update_fields=['status'])
                
                # Update enrollment status for current academic year
                if current_academic_year:
                    StudentEnrollment.objects.filter(
                        student=student,
                        academic_year=current_academic_year
                    ).update(status=enrollment_status)
                
                # Log the status change
                logger.info(
                    f"Student {student.full_name} status updated to '{new_status}' "
                    f"after withdrawal deletion"
                )
            
            # Prepare appropriate message
            if new_status == 'transferred':
                message = f'Withdrawal record for {student_name} deleted successfully. Student remains transferred.'
            elif new_status == 'suspended':
                message = f'Withdrawal record for {student_name} deleted successfully. Student remains suspended.'
            else:
                message = f'Withdrawal record for {student_name} deleted successfully. Student status restored to active.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:student_withdrawal_list')
                })
            
            messages.success(request, message)
            return redirect('management:student_withdrawal_list')
            
        except Exception as e:
            logger.error(f"Withdrawal deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting withdrawal record: {e}')
            return redirect('management:student_withdrawal_detail', pk=pk)


class GetStudentWithdrawalInfoView(ManagementRequiredMixin, View):
    """AJAX endpoint to get student info for withdrawal."""
    
    def get(self, request):
        student_id = request.GET.get('student_id')
        
        if not student_id:
            return JsonResponse({})
        
        try:
            student = get_object_or_404(Student, pk=student_id)
            
            # Get current active academic year
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            # Get active enrollment
            active_enrollment = None
            if current_academic_year:
                active_enrollment = student.enrollments.filter(
                    status='active',
                    academic_year=current_academic_year
                ).select_related('class_level', 'academic_year').first()
            
            # Get stream info if available
            stream_name = None
            if active_enrollment and hasattr(active_enrollment, 'stream_assignment'):
                stream_name = active_enrollment.stream_assignment.stream_class.name
            
            return JsonResponse({
                'student_id': student.pk,
                'student_name': student.full_name,
                'student_reg': student.registration_number,
                'has_active_enrollment': active_enrollment is not None,
                'current_class': active_enrollment.class_level.name if active_enrollment else None,
                'current_class_id': active_enrollment.class_level_id if active_enrollment else None,
                'current_stream': stream_name,
                'current_academic_year': active_enrollment.academic_year.name if active_enrollment else None,
                'current_academic_year_id': active_enrollment.academic_year_id if active_enrollment else None,
                'has_existing_withdrawal': hasattr(student, 'withdrawal'),
                'existing_withdrawal_id': student.withdrawal.pk if hasattr(student, 'withdrawal') else None,
                'has_existing_transfer': hasattr(student, 'transfer_out'),
                'student_status': student.status,
                'student_status_display': student.get_status_display(),
            })
            
        except Exception as e:
            logger.error(f"Error in GetStudentWithdrawalInfoView: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)