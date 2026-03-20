# portal_management/views/student_transfer.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    Student, StudentTransferOut, School, StudentEnrollment,
    ClassLevel, AcademicYear, Staff
)
from portal_management.forms.student_transfer_form import StudentTransferOutForm

logger = logging.getLogger(__name__)


class StudentTransferListView(ManagementRequiredMixin, TemplateView):
    """List all student transfer records with filtering."""
    template_name = 'portal_management/students/transfers/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        academic_year_id = self.request.GET.get('academic_year')
        class_level_id = self.request.GET.get('class_level')
        reason_filter = self.request.GET.get('reason')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset
        transfers = StudentTransferOut.objects.select_related(
            'student',
            'destination_school',
            'last_class_level',
            'last_academic_year',
            'authorised_by__user'
        ).order_by('-transfer_date', '-created_at')
        
        # Apply filters
        if academic_year_id:
            transfers = transfers.filter(last_academic_year_id=academic_year_id)
        
        if class_level_id:
            transfers = transfers.filter(last_class_level_id=class_level_id)
        
        if reason_filter:
            transfers = transfers.filter(reason=reason_filter)
        
        if search_query:
            transfers = transfers.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query) |
                Q(destination_school_name__icontains=search_query) |
                Q(destination_school__name__icontains=search_query)
            )
        
        ctx['transfers'] = transfers
        ctx['total_transfers'] = transfers.count()
        
        # Statistics
        ctx['transfers_this_year'] = transfers.filter(
            transfer_date__year=timezone.now().year
        ).count()
        
        # Get filter options
        ctx['academic_years'] = AcademicYear.objects.all().order_by('-start_date')
        ctx['class_levels'] = ClassLevel.objects.all().order_by('educational_level', 'order')
        ctx['reason_choices'] = StudentTransferOut.REASON_CHOICES
        
        # Store selected filters
        ctx['selected_academic_year'] = int(academic_year_id) if academic_year_id else None
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['selected_reason'] = reason_filter
        ctx['search_query'] = search_query
        
        return ctx


class StudentTransferCreateView(ManagementRequiredMixin, View):
    """Create a new student transfer out record."""
    template_name = 'portal_management/students/transfers/form.html'
    
    def get_eligible_students(self):
        """Get all students eligible for transfer with their enrollment info."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return Student.objects.none()
        
        # Get students with active enrollment in current academic year
        # and no existing transfer record
        eligible_students = Student.objects.filter(
            status='active',
            enrollments__status='active',
            enrollments__academic_year=current_academic_year,
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
    
    def get_schools(self):
        """Get all registered schools for the dropdown."""
        return School.objects.all().order_by('name')
    
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
            
            # Check if student already has a transfer record
            if hasattr(student, 'transfer_out'):
                messages.warning(
                    request, 
                    f'{student.full_name} already has a transfer record. You can edit it instead.'
                )
                return redirect('management:student_transfer_update', pk=student.transfer_out.pk)
            
            # Get current active academic year
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            if not current_academic_year:
                messages.error(
                    request,
                    'No active academic year configured. Please set an active academic year before processing transfers.'
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
                    f'Only actively enrolled students can be transferred.'
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
                'transfer_date': timezone.now().date(),
                'authorised_by': getattr(request.user, 'staff_profile', None),
            }
        
        form = StudentTransferOutForm(initial=initial)
        
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
        schools = self.get_schools()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'eligible_students': eligible_students,
            'schools': schools,
            'staff_members': staff_members,
            'title': 'Record Student Transfer',
            'is_update': False
        })
    
    def post(self, request):
        form = StudentTransferOutForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Transfer creation POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    transfer = form.save(commit=False)
                    
                    # Set authorised_by to current staff if not provided
                    if not transfer.authorised_by and hasattr(request.user, 'staff_profile'):
                        transfer.authorised_by = request.user.staff_profile
                    
                    transfer.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # Update student status to transferred
                    student = transfer.student
                    student.status = 'transferred'
                    student.save(update_fields=['status'])
                    
                    # Update all active enrollments for current academic year to 'transferred'
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year,
                            status='active'
                        ).update(status='transferred')
                    
                    message = f'Transfer record for {transfer.student.full_name} created successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_transfer_detail', kwargs={'pk': transfer.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_transfer_detail', pk=transfer.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Transfer creation validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Transfer creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating transfer record: {e}')
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
        schools = self.get_schools()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'eligible_students': eligible_students,
            'schools': schools,
            'staff_members': staff_members,
            'title': 'Record Student Transfer',
            'is_update': False
        })


class StudentTransferDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a student transfer."""
    template_name = 'portal_management/students/transfers/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        transfer = get_object_or_404(
            StudentTransferOut.objects.select_related(
                'student',
                'destination_school',
                'last_class_level__educational_level',
                'last_academic_year',
                'authorised_by__user'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['transfer'] = transfer
        ctx['student'] = transfer.student
        
        # Get student's enrollment history
        ctx['enrollments'] = transfer.student.enrollments.select_related(
            'academic_year', 'class_level'
        ).order_by('-academic_year__start_date')[:5]
        
        return ctx


class StudentTransferUpdateView(ManagementRequiredMixin, View):
    """Update an existing student transfer record."""
    template_name = 'portal_management/students/transfers/form.html'
    
    def get_schools(self):
        """Get all registered schools for the dropdown."""
        return School.objects.all().order_by('name')
    
    def get_staff_members(self):
        """Get all active staff members for the authorised_by dropdown."""
        return Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
    
    def get(self, request, pk):
        transfer = get_object_or_404(StudentTransferOut, pk=pk)
        form = StudentTransferOutForm(instance=transfer)
        
        # Disable student field (cannot change student for existing transfer)
        form.fields['student'].disabled = True
        form.fields['student'].widget.attrs['disabled'] = True
        form.fields['student'].queryset = Student.objects.filter(pk=transfer.student_id)
        
        # Get active enrollment for display
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        active_enrollment = None
        
        if current_academic_year:
            active_enrollment = transfer.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).select_related(
                'class_level', 'academic_year'
            ).prefetch_related(
                'stream_assignment__stream_class'
            ).first()
        
        # Prepare pre-selected student data for the template
        pre_selected_student_data = {
            'id': transfer.student.pk,
            'full_name': transfer.student.full_name,
            'registration_number': transfer.student.registration_number,
            'current_class': active_enrollment.class_level.name if active_enrollment else transfer.last_class_level.name if transfer.last_class_level else 'N/A',
            'current_academic_year': active_enrollment.academic_year.name if active_enrollment else transfer.last_academic_year.name if transfer.last_academic_year else 'N/A',
            'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
        }
        
        # Get all data for dropdowns
        schools = self.get_schools()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'transfer': transfer,
            'student': transfer.student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'schools': schools,
            'staff_members': staff_members,
            'title': f'Edit Transfer - {transfer.student.full_name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        transfer = get_object_or_404(StudentTransferOut, pk=pk)
        form = StudentTransferOutForm(request.POST, instance=transfer)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Transfer update POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Store student reference before save
                    student = transfer.student
                    
                    # Save the transfer
                    transfer = form.save()
                    
                    # Get current active academic year
                    current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                    
                    # Check if student still has a transfer record (they do, it's this one)
                    # No need to update status as it should remain 'transferred'
                    
                    # Update enrollment status to ensure consistency
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year,
                            status='active'
                        ).update(status='transferred')
                    
                    message = f'Transfer record updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_transfer_detail', kwargs={'pk': transfer.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_transfer_detail', pk=transfer.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Transfer update validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Transfer update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating transfer record: {e}')
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
        form.fields['student'].queryset = Student.objects.filter(pk=transfer.student_id)
        
        # Get active enrollment for display
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        active_enrollment = None
        
        if current_academic_year:
            active_enrollment = transfer.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).first()
        
        # Get all data for dropdowns
        schools = self.get_schools()
        staff_members = self.get_staff_members()
        
        return render(request, self.template_name, {
            'form': form,
            'transfer': transfer,
            'student': transfer.student,
            'active_enrollment': active_enrollment,
            'schools': schools,
            'staff_members': staff_members,
            'title': f'Edit Transfer - {transfer.student.full_name}',
            'is_update': True
        })


class StudentTransferDeleteView(ManagementRequiredMixin, View):
    """Delete a student transfer record."""
    
    def post(self, request, pk):
        transfer = get_object_or_404(StudentTransferOut, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = transfer.student.full_name
            student = transfer.student
            
            with transaction.atomic():
                # Delete the transfer record
                transfer.delete()
                
                # Get current active academic year
                current_academic_year = AcademicYear.objects.filter(is_active=True).first()
                
                # Check if student has any other reason to be transferred
                # If not, set status back to active
                if not hasattr(student, 'transfer_out'):
                    student.status = 'active'
                    student.save(update_fields=['status'])
                    
                    # Update enrollment status back to active
                    if current_academic_year:
                        StudentEnrollment.objects.filter(
                            student=student,
                            academic_year=current_academic_year
                        ).update(status='active')
            
            message = f'Transfer record for {student_name} deleted successfully.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:student_transfer_list')
                })
            
            messages.success(request, message)
            return redirect('management:student_transfer_list')
            
        except Exception as e:
            logger.error(f"Transfer deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting transfer record: {e}')
            return redirect('management:student_transfer_detail', pk=pk)


class GetStudentTransferDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get transfer details for editing in modal."""
    
    def get(self, request, pk):
        try:
            transfer = get_object_or_404(
                StudentTransferOut.objects.select_related(
                    'student', 'destination_school', 'last_class_level', 
                    'last_academic_year', 'authorised_by'
                ),
                pk=pk
            )
            
            return JsonResponse({
                'id': transfer.pk,
                'student_id': transfer.student_id,
                'student_name': transfer.student.full_name,
                'student_reg': transfer.student.registration_number,
                'transfer_date': transfer.transfer_date.strftime('%Y-%m-%d'),
                'destination_school_id': transfer.destination_school_id,
                'destination_school_name': transfer.destination_school_name or '',
                'reason': transfer.reason,
                'last_class_level_id': transfer.last_class_level_id,
                'last_class_level_name': transfer.last_class_level.name if transfer.last_class_level else None,
                'last_academic_year_id': transfer.last_academic_year_id,
                'last_academic_year_name': transfer.last_academic_year.name if transfer.last_academic_year else None,
                'transfer_letter_issued': transfer.transfer_letter_issued,
                'transcript_issued': transfer.transcript_issued,
                'authorised_by_id': transfer.authorised_by_id,
                'authorised_by_name': transfer.authorised_by.get_full_name() if transfer.authorised_by else None,
                'remarks': transfer.remarks or '',
            })
            
        except Exception as e:
            logger.error(f"Error in GetStudentTransferDetailsView: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)