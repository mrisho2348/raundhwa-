# portal_management/views/student_combination_assignment.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    StudentCombinationAssignment, Student, StudentEnrollment,
    Combination, AcademicYear, ClassLevel
)
from portal_management.forms.student_combination_assignment_form import (
    StudentCombinationAssignmentForm, StudentCombinationAssignmentQuickForm
)

logger = logging.getLogger(__name__)


class StudentCombinationAssignmentListView(ManagementRequiredMixin, TemplateView):
    """List all student combination assignments with filtering."""
    template_name = 'portal_management/students/combinations/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        student_id = self.request.GET.get('student')
        combination_id = self.request.GET.get('combination')
        status_filter = self.request.GET.get('status')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset
        assignments = StudentCombinationAssignment.objects.select_related(
            'student',
            'enrollment',
            'enrollment__class_level',
            'combination'
        ).order_by('-assigned_date', '-created_at')
        
        # Apply filters
        if student_id:
            assignments = assignments.filter(student_id=student_id)
        
        if combination_id:
            assignments = assignments.filter(combination_id=combination_id)
        
        if status_filter == 'active':
            assignments = assignments.filter(is_active=True)
        elif status_filter == 'inactive':
            assignments = assignments.filter(is_active=False)
        
        if search_query:
            assignments = assignments.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query) |
                Q(combination__code__icontains=search_query)
            )
        
        ctx['assignments'] = assignments
        ctx['total_assignments'] = assignments.count()
        ctx['active_count'] = assignments.filter(is_active=True).count()
        ctx['inactive_count'] = assignments.filter(is_active=False).count()
        
        # Get filter options
        ctx['students'] = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL'
        ).distinct().order_by('first_name', 'last_name')
        
        ctx['combinations'] = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        # Store selected filters
        ctx['selected_student'] = int(student_id) if student_id else None
        ctx['selected_combination'] = int(combination_id) if combination_id else None
        ctx['selected_status'] = status_filter
        ctx['search_query'] = search_query
        
        return ctx


class StudentCombinationAssignmentCreateView(ManagementRequiredMixin, View):
    """Create a new student combination assignment."""
    template_name = 'portal_management/students/combinations/form.html'
    
    def get_eligible_enrollments(self, student):
        """Get eligible enrollments for a student."""
        if not student:
            return StudentEnrollment.objects.none()
        
        return student.enrollments.filter(
            class_level__educational_level__level_type='A_LEVEL'
        ).select_related('class_level', 'academic_year')
    
    def get(self, request, student_id=None):
        initial = {}
        student = None
        pre_selected_student_data = None
        
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            initial['student'] = student
            
            # Get active enrollment for this student
            enrollments = self.get_eligible_enrollments(student)
            if enrollments.exists():
                # Try to get active enrollment, otherwise get the first one
                active_enrollment = enrollments.filter(status='active').first()
                if active_enrollment:
                    initial['enrollment'] = active_enrollment
                else:
                    initial['enrollment'] = enrollments.first()
            
            pre_selected_student_data = {
                'id': student.pk,
                'full_name': student.full_name,
                'registration_number': student.registration_number,
            }
        
        form = StudentCombinationAssignmentForm(initial=initial)
        
        # Get all data for dropdowns
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL'
        ).distinct().order_by('first_name', 'last_name')
        
        combinations = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'pre_selected_student': pre_selected_student_data,
            'students': students,
            'combinations': combinations,
            'title': 'Assign Student Combination',
            'is_update': False
        })
    
    def post(self, request):
        # Get the student ID from POST data
        student_id = request.POST.get('student')
        
        # If student is selected, dynamically update the enrollment queryset
        if student_id:
            try:
                student = Student.objects.get(pk=student_id)
                # Create a dynamic form with student-specific enrollment choices
                form = StudentCombinationAssignmentForm(request.POST)
                # Set the enrollment queryset for this student
                form.fields['enrollment'].queryset = student.enrollments.filter(
                    class_level__educational_level__level_type='A_LEVEL'
                ).select_related('class_level', 'academic_year')
            except Student.DoesNotExist:
                form = StudentCombinationAssignmentForm(request.POST)
        else:
            form = StudentCombinationAssignmentForm(request.POST)
        
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save()
                    
                    message = f'Combination {assignment.combination.code} assigned to {assignment.student.full_name} successfully.'
                    
                    if hasattr(form, 'warnings') and form.warnings:
                        message += f' Note: {form.warnings[0]}'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_combination_assignment_detail', kwargs={'pk': assignment.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_combination_assignment_detail', pk=assignment.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Combination assignment error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating assignment: {e}')
        else:
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
        
        # Get data for re-render
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL'
        ).distinct().order_by('first_name', 'last_name')
        
        combinations = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        # Get the selected student for re-render
        selected_student = None
        if student_id:
            try:
                selected_student = Student.objects.get(pk=student_id)
            except Student.DoesNotExist:
                pass
        
        return render(request, self.template_name, {
            'form': form,
            'student': selected_student,
            'pre_selected_student': {'id': selected_student.pk, 'full_name': selected_student.full_name, 'registration_number': selected_student.registration_number} if selected_student else None,
            'students': students,
            'combinations': combinations,
            'title': 'Assign Student Combination',
            'is_update': False
        })



class StudentCombinationAssignmentDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a combination assignment."""
    template_name = 'portal_management/students/combinations/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        assignment = get_object_or_404(
            StudentCombinationAssignment.objects.select_related(
                'student',
                'enrollment',
                'enrollment__class_level',
                'enrollment__academic_year',
                'combination'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['assignment'] = assignment
        ctx['student'] = assignment.student
        
        # Get other assignments for the same student
        ctx['other_assignments'] = StudentCombinationAssignment.objects.filter(
            student=assignment.student
        ).exclude(pk=assignment.pk).select_related(
            'combination'
        ).order_by('-assigned_date')[:5]
        
        # Get enrollment details
        ctx['enrollment'] = assignment.enrollment
        
        return ctx


class StudentCombinationAssignmentUpdateView(ManagementRequiredMixin, View):
    """Update an existing combination assignment."""
    template_name = 'portal_management/students/combinations/form.html'
    
    def get_eligible_enrollments(self, student):
        """Get eligible enrollments for a student."""
        if not student:
            return StudentEnrollment.objects.none()
        
        return student.enrollments.filter(
            class_level__educational_level__level_type='A_LEVEL'
        ).select_related('class_level', 'academic_year')
    
    def get(self, request, pk):
        assignment = get_object_or_404(StudentCombinationAssignment, pk=pk)
        form = StudentCombinationAssignmentForm(instance=assignment)
        
        # Disable student and enrollment fields (cannot change)
        form.fields['student'].disabled = True
        form.fields['student'].widget.attrs['disabled'] = True
        form.fields['enrollment'].disabled = True
        form.fields['enrollment'].widget.attrs['disabled'] = True
        
        # Set display fields
        form.initial['student_full_name'] = assignment.student.full_name
        form.initial['student_registration'] = assignment.student.registration_number
        form.initial['current_class'] = assignment.enrollment.class_level.name
        
        # Get data for dropdowns
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL'
        ).distinct().order_by('first_name', 'last_name')
        
        combinations = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        return render(request, self.template_name, {
            'form': form,
            'assignment': assignment,
            'student': assignment.student,
            'students': students,
            'combinations': combinations,
            'title': f'Edit Combination Assignment - {assignment.student.full_name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        assignment = get_object_or_404(StudentCombinationAssignment, pk=pk)
        form = StudentCombinationAssignmentForm(request.POST, instance=assignment)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    assignment = form.save()
                    
                    message = f'Combination assignment updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_combination_assignment_detail', kwargs={'pk': assignment.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_combination_assignment_detail', pk=assignment.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Combination assignment update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating assignment: {e}')
        else:
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
        
        # Get data for re-render
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL'
        ).distinct().order_by('first_name', 'last_name')
        
        combinations = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        return render(request, self.template_name, {
            'form': form,
            'assignment': assignment,
            'student': assignment.student,
            'students': students,
            'combinations': combinations,
            'title': f'Edit Combination Assignment - {assignment.student.full_name}',
            'is_update': True
        })


class StudentCombinationAssignmentDeleteView(ManagementRequiredMixin, View):
    """Delete a combination assignment."""
    
    def post(self, request, pk):
        assignment = get_object_or_404(StudentCombinationAssignment, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = assignment.student.full_name
            combination_code = assignment.combination.code
            
            with transaction.atomic():
                assignment.delete()
            
            message = f'Combination {combination_code} assignment for {student_name} deleted successfully.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:student_combination_assignment_list')
                })
            
            messages.success(request, message)
            return redirect('management:student_combination_assignment_list')
            
        except Exception as e:
            logger.error(f"Combination assignment deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting assignment: {e}')
            return redirect('management:student_combination_assignment_detail', pk=pk)


class GetStudentEnrollmentsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get student enrollments for combination assignment."""
    
    def get(self, request):
        student_id = request.GET.get('student_id')
        
        if not student_id:
            return JsonResponse({'enrollments': []})
        
        try:
            student = get_object_or_404(Student, pk=student_id)
            
            # Get all A-Level enrollments for this student
            enrollments = student.enrollments.filter(
                class_level__educational_level__level_type='A_LEVEL'
            ).select_related('class_level', 'academic_year')
            
            enrollment_data = []
            for enrollment in enrollments:
                enrollment_data.append({
                    'id': enrollment.pk,
                    'class_level': enrollment.class_level.name,
                    'academic_year': enrollment.academic_year.name,
                    'status': enrollment.status,
                    'has_active_assignment': enrollment.combination_assignments.filter(is_active=True).exists(),
                    'active_assignment': enrollment.current_combination.code if enrollment.current_combination else None,
                })
            
            return JsonResponse({
                'enrollments': enrollment_data,
                'has_active_assignments': any(e['has_active_assignment'] for e in enrollment_data)
            })
            
        except Exception as e:
            logger.error(f"Error fetching student enrollments: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)