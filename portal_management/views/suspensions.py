# portal_management/views/suspensions.py

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
    Student, StudentEnrollment, StudentSuspension, Staff, 
    AcademicYear, ClassLevel
)
from portal_management.forms.suspension_form import StudentSuspensionForm

logger = logging.getLogger(__name__)


class StudentSuspensionListView(ManagementRequiredMixin, TemplateView):
    """List all student suspensions with filtering."""
    template_name = 'portal_management/students/suspensions/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        status_filter = self.request.GET.get('status', '')
        reason_filter = self.request.GET.get('reason', '')
        academic_year_id = self.request.GET.get('academic_year')
        class_level_id = self.request.GET.get('class_level')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset with optimized selects
        suspensions = StudentSuspension.objects.select_related(
            'student',
            'authorised_by__user',
            'lifted_by__user'
        ).order_by('-suspension_date', '-created_at')
        
        # Apply filters
        if status_filter == 'active':
            suspensions = suspensions.filter(is_lifted=False)
        elif status_filter == 'lifted':
            suspensions = suspensions.filter(is_lifted=True)
        
        if reason_filter:
            suspensions = suspensions.filter(reason=reason_filter)
        
        if academic_year_id:
            suspensions = suspensions.filter(
                suspension_date__year=academic_year_id
            )
        
        if class_level_id:
            suspensions = suspensions.filter(
                student__enrollments__class_level_id=class_level_id,
                student__enrollments__status='active'
            ).distinct()
        
        if search_query:
            suspensions = suspensions.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query)
            )
        
        ctx['suspensions'] = suspensions
        ctx['total_suspensions'] = suspensions.count()
        
        # Statistics
        ctx['active_suspensions'] = suspensions.filter(is_lifted=False).count()
        ctx['lifted_suspensions'] = suspensions.filter(is_lifted=True).count()
        
        # Get filter options
        ctx['academic_years'] = AcademicYear.objects.all().order_by('-start_date')
        ctx['class_levels'] = ClassLevel.objects.all().order_by('educational_level', 'order')
        ctx['reason_choices'] = StudentSuspension.REASON_CHOICES
        
        # Store selected filters
        ctx['selected_status'] = status_filter
        ctx['selected_reason'] = reason_filter
        ctx['selected_academic_year'] = int(academic_year_id) if academic_year_id else None
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['search_query'] = search_query
        
        return ctx


class StudentSuspensionCreateView(ManagementRequiredMixin, View):
    """Create a new student suspension."""
    template_name = 'portal_management/students/suspensions/form.html'
    
    def get_eligible_students(self):
        """Get all students eligible for suspension."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return Student.objects.none()
        
        # Get students with active enrollment in current academic year
        # and no active suspensions
        eligible_student_ids = StudentEnrollment.objects.filter(
            status='active',
            academic_year=current_academic_year
        ).exclude(
            student__suspensions__is_lifted=False
        ).values_list('student_id', flat=True).distinct()
        
        return Student.objects.filter(
            id__in=eligible_student_ids,
            status='active'
        ).order_by('first_name', 'last_name')
    
    def get(self, request, student_id=None):
        initial = {}
        student = None
        active_enrollment = None
        
        # If student_id is provided, pre-fill student data
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            
            # Get current active academic year
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            if not current_academic_year:
                messages.error(
                    request,
                    'No active academic year configured. Please set an active academic year before suspending students.'
                )
                return redirect('management:student_detail', pk=student.pk)
            
            # Check if student has active enrollment in current academic year
            active_enrollment = student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).first()
            
            if not active_enrollment:
                messages.error(
                    request,
                    f'{student.full_name} does not have an active enrollment in {current_academic_year.name}. '
                    f'Only enrolled students can be suspended.'
                )
                return redirect('management:student_detail', pk=student.pk)
            
            # Check for existing active suspension
            active_suspension = student.suspensions.filter(is_lifted=False).first()
            if active_suspension:
                messages.warning(
                    request,
                    f'{student.full_name} already has an active suspension from {active_suspension.suspension_date}. '
                    f'Please lift it before creating a new one.'
                )
                return redirect('management:suspension_detail', pk=active_suspension.pk)
            
            initial = {
                'student': student,
                'suspension_date': timezone.now().date(),
                'authorised_by': getattr(request.user, 'staff_profile', None),
            }
        
        form = StudentSuspensionForm(initial=initial)
        
        # If student is pre-selected, set the display fields
        if student and active_enrollment:
            form.initial['enrollment_status'] = 'Active'
            form.initial['current_class'] = active_enrollment.class_level.name
            form.initial['current_academic_year'] = active_enrollment.academic_year.name
        
        # Get all eligible students for the dropdown
        eligible_students = self.get_eligible_students()
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'active_enrollment': active_enrollment,
            'eligible_students': eligible_students,
            'title': 'Suspend Student',
            'action': 'Create',
            'is_update': False
        })
    
    def post(self, request):
        form = StudentSuspensionForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Log for debugging
        logger.debug(f"Suspension creation POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    suspension = form.save(commit=False)
                    
                    # Set authorised_by to current staff if not provided
                    if not suspension.authorised_by and hasattr(request.user, 'staff_profile'):
                        suspension.authorised_by = request.user.staff_profile
                    
                    suspension.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # Update student status
                    student = suspension.student
                    student.status = 'suspended'
                    student.save(update_fields=['status'])
                    
                    # Update all active enrollments for current academic year to 'suspended'
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year,
                            status='active'
                        ).update(status='suspended')
                    
                    message = f'{suspension.student.full_name} has been suspended successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:suspension_detail', kwargs={'pk': suspension.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:suspension_detail', pk=suspension.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Suspension creation validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Suspension creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating suspension: {e}')
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
        
        # Get eligible students for re-render
        eligible_students = self.get_eligible_students()
        
        return render(request, self.template_name, {
            'form': form,
            'eligible_students': eligible_students,
            'title': 'Suspend Student',
            'action': 'Create',
            'is_update': False
        })


# In your StudentSuspensionDetailView, add staff_members to context

class StudentSuspensionDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a student suspension."""
    template_name = 'portal_management/students/suspensions/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        suspension = get_object_or_404(
            StudentSuspension.objects.select_related(
                'student',
                'authorised_by__user',
                'lifted_by__user'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['suspension'] = suspension
        ctx['student'] = suspension.student
        
        # Get current date for the lift modal
        ctx['current_date'] = timezone.now().date()
        
        # Get staff members for the lift modal dropdown
        ctx['staff_members'] = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        
        # Get suspension history for this student (excluding current)
        ctx['suspension_history'] = StudentSuspension.objects.filter(
            student=suspension.student
        ).exclude(pk=suspension.pk).order_by('-suspension_date')[:5]
        
        # Get current enrollment info
        ctx['active_enrollment'] = suspension.student.enrollments.filter(
            status='active',
            academic_year__is_active=True
        ).first()
        
        # Get statistics
        ctx['total_suspensions'] = StudentSuspension.objects.filter(
            student=suspension.student
        ).count()
        
        return ctx


class StudentSuspensionUpdateView(ManagementRequiredMixin, View):
    """Update an existing student suspension."""
    template_name = 'portal_management/students/suspensions/form.html'
    
    def get(self, request, pk):
        suspension = get_object_or_404(StudentSuspension, pk=pk)
        form = StudentSuspensionForm(instance=suspension)
        
        # Get current enrollment info
        active_enrollment = suspension.student.enrollments.filter(
            status='active',
            academic_year__is_active=True
        ).first()
        
        # Get suspension history for this student (excluding current)
        suspension_history = StudentSuspension.objects.filter(
            student=suspension.student
        ).exclude(pk=suspension.pk).order_by('-suspension_date')[:5]
        
        # Get staff members for the lift modal dropdown
        staff_members = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        
        # Get current date for the lift modal
        current_date = timezone.now().date()
        
        return render(request, self.template_name, {
            'form': form,
            'suspension': suspension,
            'student': suspension.student,
            'active_enrollment': active_enrollment,
            'suspension_history': suspension_history,
            'staff_members': staff_members,
            'current_date': current_date,
            'title': f'Edit Suspension - {suspension.student.full_name}',
            'action': 'Update',
            'is_update': True
        })
    
    def post(self, request, pk):
        suspension = get_object_or_404(StudentSuspension, pk=pk)
        form = StudentSuspensionForm(request.POST, instance=suspension)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Suspension update POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Store old lifted status to detect changes
                    was_lifted = suspension.is_lifted
                    suspension = form.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # If suspension was just lifted (changed from False to True)
                    if not was_lifted and suspension.is_lifted:
                        # Check if there are any other active suspensions
                        other_active = StudentSuspension.objects.filter(
                            student=suspension.student,
                            is_lifted=False
                        ).exclude(pk=suspension.pk).exists()
                        
                        if not other_active:
                            # Update student status to active
                            suspension.student.status = 'active'
                            suspension.student.save(update_fields=['status'])
                            
                            # Update enrollment status back to active for current academic year
                            if current_academic_year:
                                StudentEnrollment.objects.filter(
                                    student=suspension.student,
                                    academic_year=current_academic_year
                                ).update(status='active')
                    
                    # If suspension was made active (changed from True to False)
                    elif was_lifted and not suspension.is_lifted:
                        # Student is being suspended again
                        suspension.student.status = 'suspended'
                        suspension.student.save(update_fields=['status'])
                        
                        # Update enrollment status to suspended
                        if current_academic_year:
                            StudentEnrollment.objects.filter(
                                student=suspension.student,
                                academic_year=current_academic_year
                            ).update(status='suspended')
                    
                    message = f'Suspension record updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:suspension_detail', kwargs={'pk': suspension.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:suspension_detail', pk=suspension.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Suspension update validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Suspension update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating suspension: {e}')
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
        
        # Get current enrollment info for re-render
        active_enrollment = suspension.student.enrollments.filter(
            status='active',
            academic_year__is_active=True
        ).first()
        
        # Get suspension history for this student (excluding current)
        suspension_history = StudentSuspension.objects.filter(
            student=suspension.student
        ).exclude(pk=suspension.pk).order_by('-suspension_date')[:5]
        
        # Get staff members for the lift modal dropdown
        staff_members = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        
        # Get current date for the lift modal
        current_date = timezone.now().date()
        
        return render(request, self.template_name, {
            'form': form,
            'suspension': suspension,
            'student': suspension.student,
            'active_enrollment': active_enrollment,
            'suspension_history': suspension_history,
            'staff_members': staff_members,
            'current_date': current_date,
            'title': f'Edit Suspension - {suspension.student.full_name}',
            'action': 'Update',
            'is_update': True
        })


class StudentSuspensionDeleteView(ManagementRequiredMixin, View):
    """Delete a student suspension record."""
    
    def post(self, request, pk):
        suspension = get_object_or_404(StudentSuspension, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = suspension.student.full_name
            was_active = not suspension.is_lifted
            
            with transaction.atomic():
                # Store student reference before deletion
                student = suspension.student
                
                # Delete the suspension
                suspension.delete()
                
                # Get current active academic year
                current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                
                # Check if student has any other active suspensions
                other_active = StudentSuspension.objects.filter(
                    student=student,
                    is_lifted=False
                ).exists()
                
                if not other_active:
                    # If no active suspensions, restore student status to active
                    student.status = 'active'
                    student.save(update_fields=['status'])
                    
                    # Restore enrollment status to active for current academic year
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year
                        ).update(status='active')
                else:
                    # Student still has active suspensions, ensure status is suspended
                    student.status = 'suspended'
                    student.save(update_fields=['status'])
                    
                    # Ensure enrollment status is suspended
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year
                        ).update(status='suspended')
            
            message = f'Suspension record for {student_name} deleted successfully.'
            if was_active:
                message += ' Student status has been restored to active.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:suspension_list')
                })
            
            messages.success(request, message)
            return redirect('management:suspension_list')
            
        except Exception as e:
            logger.error(f"Suspension deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting suspension: {e}')
            return redirect('management:suspension_detail', pk=pk)


class StudentSuspensionLiftView(ManagementRequiredMixin, View):
    """Quick action to lift a suspension."""
    
    def post(self, request, pk):
        suspension = get_object_or_404(StudentSuspension, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check if already lifted
        if suspension.is_lifted:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'This suspension has already been lifted.'
                }, status=400)
            messages.warning(request, 'This suspension is already lifted.')
            return redirect('management:suspension_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Get form data from request (for modal with date and staff)
                lifted_date = request.POST.get('lifted_date')
                lifted_by_id = request.POST.get('lifted_by')
                
                # Validate lifted_date if provided
                if lifted_date:
                    try:
                        # Parse the date string
                        from datetime import datetime
                        lifted_date_obj = datetime.strptime(lifted_date, '%Y-%m-%d').date()
                        
                        # Validate that lifted date is not before suspension date
                        if lifted_date_obj < suspension.suspension_date:
                            error_msg = 'Lift date cannot be before the suspension date.'
                            if is_ajax:
                                return JsonResponse({
                                    'success': False,
                                    'message': error_msg
                                }, status=400)
                            messages.error(request, error_msg)
                            return redirect('management:suspension_detail', pk=pk)
                        
                        suspension.lifted_date = lifted_date_obj
                    except (ValueError, TypeError):
                        # If date parsing fails, default to today
                        suspension.lifted_date = timezone.now().date()
                else:
                    # Default to today if not provided
                    suspension.lifted_date = timezone.now().date()
                
                # Set lifted_by from form or default to current staff
                if lifted_by_id:
                    try:
                        suspension.lifted_by = Staff.objects.get(pk=lifted_by_id)
                    except Staff.DoesNotExist:
                        # If staff not found, use current staff as fallback
                        if hasattr(request.user, 'staff_profile'):
                            suspension.lifted_by = request.user.staff_profile
                elif hasattr(request.user, 'staff_profile'):
                    suspension.lifted_by = request.user.staff_profile
                
                # Mark as lifted
                suspension.is_lifted = True
                suspension.save()
                
                # Get current active academic year
                current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                
                # Check if there are any other active suspensions for this student
                other_active_suspensions = StudentSuspension.objects.filter(
                    student=suspension.student,
                    is_lifted=False
                ).exclude(pk=suspension.pk).exists()
                
                student = suspension.student
                
                if not other_active_suspensions:
                    # No other active suspensions - restore student to active
                    student.status = 'active'
                    student.save(update_fields=['status'])
                    
                    # Update enrollment status back to active for current academic year
                    if current_academic_year:
                        # Update all enrollments for current academic year to active
                        updated_count = StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year
                        ).update(status='active')
                        
                        logger.info(f"Restored {updated_count} enrollments to active for {student.full_name}")
                else:
                    # Student still has active suspensions - keep status as suspended
                    student.status = 'suspended'
                    student.save(update_fields=['status'])
                    
                    # Keep enrollment status as suspended for current academic year
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year
                        ).update(status='suspended')
                    
                    logger.info(f"Student {student.full_name} still has other active suspensions, status remains suspended")
                
                # Log the action
                logger.info(
                    f"Suspension {suspension.pk} lifted by {request.user} "
                    f"for student {student.full_name} on {suspension.lifted_date}"
                )
            
            # Prepare success message
            if other_active_suspensions:
                message = f'Suspension for {student.full_name} has been lifted, but student still has other active suspensions.'
            else:
                message = f'Suspension for {student.full_name} has been lifted. Student status restored to active.'
            
            # Return JSON response for AJAX requests
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'suspension': {
                        'id': suspension.pk,
                        'is_lifted': True,
                        'lifted_date': suspension.lifted_date.strftime('%Y-%m-%d'),
                        'lifted_by': str(suspension.lifted_by) if suspension.lifted_by else None,
                        'lifted_by_id': suspension.lifted_by.pk if suspension.lifted_by else None,
                        'student_status': student.status
                    }
                })
            
            messages.success(request, message)
            return redirect('management:suspension_detail', pk=pk)
            
        except ValidationError as e:
            error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
            logger.error(f"Suspension lift validation error: {error_msg}")
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:suspension_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Suspension lift error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error lifting suspension: {e}')
            return redirect('management:suspension_detail', pk=pk)


class GetStudentSuspensionInfoView(ManagementRequiredMixin, View):
    """AJAX endpoint to get student info for suspension."""
    
    def get(self, request):
        student_id = request.GET.get('student_id')
        
        if not student_id:
            return JsonResponse({})
        
        try:
            student = get_object_or_404(Student, pk=student_id)
            
            # Get current active academic year
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            # Get active enrollment in current academic year
            active_enrollment = None
            enrollment_status = None
            if current_academic_year:
                active_enrollment = student.enrollments.filter(
                    academic_year=current_academic_year
                ).select_related('class_level', 'academic_year').first()
                
                if active_enrollment:
                    enrollment_status = active_enrollment.status
            
            # Check for existing active suspension
            active_suspension = student.suspensions.filter(is_lifted=False).first()
            
            return JsonResponse({
                'student_id': student.pk,
                'student_name': student.full_name,
                'student_reg': student.registration_number,
                'student_status': student.status,
                'student_status_display': student.get_status_display(),
                'enrollment_status': enrollment_status,
                'has_active_enrollment': active_enrollment is not None and active_enrollment.status == 'active',
                'current_class': active_enrollment.class_level.name if active_enrollment else None,
                'current_class_id': active_enrollment.class_level_id if active_enrollment else None,
                'current_academic_year': active_enrollment.academic_year.name if active_enrollment else None,
                'has_active_suspension': active_suspension is not None,
                'active_suspension_id': active_suspension.pk if active_suspension else None,
                'active_suspension_date': active_suspension.suspension_date.strftime('%Y-%m-%d') if active_suspension else None,
            })
            
        except Exception as e:
            logger.error(f"Error in GetStudentSuspensionInfoView: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)