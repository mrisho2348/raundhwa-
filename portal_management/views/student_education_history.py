# portal_management/views/student_education_history.py

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
    Student, StudentEducationHistory, School, EducationalLevel,
    Combination, DivisionScale, AcademicYear, StudentEnrollment, ClassLevel
)
from portal_management.forms.student_education_history_form import StudentEducationHistoryForm

logger = logging.getLogger(__name__)


class StudentEducationHistoryListView(ManagementRequiredMixin, TemplateView):
    """List all student education history records with filtering."""
    template_name = 'portal_management/students/education_history/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        student_id = self.request.GET.get('student')
        school_id = self.request.GET.get('school')
        level_type = self.request.GET.get('level_type')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset
        histories = StudentEducationHistory.objects.select_related(
            'student',
            'school',
            'school__educational_level',
            'combination'
        ).order_by('-completion_year', '-created_at')
        
        # Apply filters
        if student_id:
            histories = histories.filter(student_id=student_id)
        
        if school_id:
            histories = histories.filter(school_id=school_id)
        
        if level_type:
            histories = histories.filter(school__educational_level__level_type=level_type)
        
        if search_query:
            histories = histories.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query) |
                Q(school__name__icontains=search_query) |
                Q(class_completed__icontains=search_query) |
                Q(examination_number__icontains=search_query)
            )
        
        ctx['histories'] = histories
        ctx['total_histories'] = histories.count()
        
        # Statistics
        ctx['primary_count'] = histories.filter(school__educational_level__level_type='PRIMARY').count()
        ctx['olevel_count'] = histories.filter(school__educational_level__level_type='O_LEVEL').count()
        ctx['alevel_count'] = histories.filter(school__educational_level__level_type='A_LEVEL').count()
        ctx['transfer_count'] = histories.filter(is_transfer=True).count()
        
        # Get filter options
        ctx['students'] = Student.objects.all().order_by('first_name', 'last_name')
        ctx['schools'] = School.objects.select_related('educational_level').all().order_by('name')
        ctx['level_types'] = EducationalLevel.LEVEL_TYPE_CHOICES
        ctx['class_levels'] = ClassLevel.objects.select_related('educational_level').all().order_by('educational_level__level_type', 'order')
        
        # Store selected filters
        ctx['selected_student'] = int(student_id) if student_id else None
        ctx['selected_school'] = int(school_id) if school_id else None
        ctx['selected_level_type'] = level_type
        ctx['search_query'] = search_query
        
        return ctx


class StudentEducationHistoryCreateView(ManagementRequiredMixin, View):
    """Create a new student education history record."""
    template_name = 'portal_management/students/education_history/form.html'
    
    def get_schools(self):
        """Get all schools for the dropdown."""
        return School.objects.select_related('educational_level').all().order_by('name')
    
    def get_combinations(self):
        """Get all combinations for the dropdown."""
        return Combination.objects.select_related('educational_level').all().order_by('code')
    
    def get_class_levels(self):
        """Get all class levels for the dropdown."""
        return ClassLevel.objects.select_related('educational_level').all().order_by('educational_level__level_type', 'order')
    
    def get_student_current_enrollment(self, student):
        """Get the student's current active enrollment."""
        if not student:
            return None
        
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_academic_year:
            return None
        
        return student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).select_related('class_level__educational_level', 'academic_year').first()
    
    def get_students_with_enrollment_data(self):
        """Get all students with their enrollment data as data attributes."""
        students = Student.objects.all().order_by('first_name', 'last_name')
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        student_options = []
        for student in students:
            enrollment = None
            if current_academic_year:
                enrollment = student.enrollments.filter(
                    status='active',
                    academic_year=current_academic_year
                ).select_related('class_level', 'academic_year').first()
            
            student_options.append({
                'id': student.pk,
                'name': student.full_name,
                'reg_number': student.registration_number,
                'has_enrollment': enrollment is not None,
                'current_class': enrollment.class_level.name if enrollment else '',
                'current_class_order': enrollment.class_level.order if enrollment else '',
                'current_academic_year': enrollment.academic_year.name if enrollment else '',
                'enrollment_year': enrollment.academic_year.start_date.year if enrollment else '',
            })
        
        return student_options
    
    def get(self, request, student_id=None):
        initial = {}
        student = None
        active_enrollment = None
        pre_selected_student_data = None
        
        # If student_id is provided, pre-fill student data
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            initial['student'] = student
            
            # Get current active enrollment
            active_enrollment = self.get_student_current_enrollment(student)
            
            # Prepare pre-selected student data for the template
            pre_selected_student_data = {
                'id': student.pk,
                'full_name': student.full_name,
                'registration_number': student.registration_number,
                'current_class': active_enrollment.class_level.name if active_enrollment else 'Not enrolled',
                'current_class_order': active_enrollment.class_level.order if active_enrollment else None,
                'current_academic_year': active_enrollment.academic_year.name if active_enrollment else 'Not enrolled',
                'current_academic_year_start': active_enrollment.academic_year.start_date.year if active_enrollment else None,
                'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
                'has_active_enrollment': active_enrollment is not None,
            }
        
        form = StudentEducationHistoryForm(initial=initial)
        
        # Get all data for dropdowns
        student_options = self.get_students_with_enrollment_data()
        schools = self.get_schools()
        combinations = self.get_combinations()
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'student_options': student_options,
            'schools': schools,
            'combinations': combinations,
            'class_levels': class_levels,
            'title': 'Add Education History',
            'is_update': False
        })
    
    def post(self, request):
        form = StudentEducationHistoryForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Education history creation POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    history = form.save()
                    
                    message = f'Education history for {history.student.full_name} added successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_education_history_detail', kwargs={'pk': history.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_education_history_detail', pk=history.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Education history creation validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Education history creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating education history record: {e}')
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
        student_options = self.get_students_with_enrollment_data()
        schools = self.get_schools()
        combinations = self.get_combinations()
        class_levels = self.get_class_levels()
        
        # Get the selected student if available
        student_id = request.POST.get('student')
        student = None
        active_enrollment = None
        pre_selected_student_data = None
        
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            active_enrollment = self.get_student_current_enrollment(student)
            
            pre_selected_student_data = {
                'id': student.pk,
                'full_name': student.full_name,
                'registration_number': student.registration_number,
                'current_class': active_enrollment.class_level.name if active_enrollment else 'Not enrolled',
                'current_class_order': active_enrollment.class_level.order if active_enrollment else None,
                'current_academic_year': active_enrollment.academic_year.name if active_enrollment else 'Not enrolled',
                'current_academic_year_start': active_enrollment.academic_year.start_date.year if active_enrollment else None,
                'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
                'has_active_enrollment': active_enrollment is not None,
            }
        
        return render(request, self.template_name, {
            'form': form,
            'student': student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'student_options': student_options,
            'schools': schools,
            'combinations': combinations,
            'class_levels': class_levels,
            'title': 'Add Education History',
            'is_update': False
        })


class StudentEducationHistoryDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a student's education history."""
    template_name = 'portal_management/students/education_history/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        history = get_object_or_404(
            StudentEducationHistory.objects.select_related(
                'student',
                'school',
                'school__educational_level',
                'combination'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['history'] = history
        ctx['student'] = history.student
        
        # Get other education history records for the same student
        ctx['other_histories'] = StudentEducationHistory.objects.filter(
            student=history.student
        ).exclude(pk=history.pk).select_related(
            'school', 'combination'
        ).order_by('-completion_year')[:5]
        
        # Get current enrollment for warning display
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if current_academic_year:
            ctx['current_enrollment'] = history.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).select_related('class_level', 'academic_year').first()
        
        return ctx


class StudentEducationHistoryUpdateView(ManagementRequiredMixin, View):
    """Update an existing student education history record."""
    template_name = 'portal_management/students/education_history/form.html'
    
    def get_schools(self):
        """Get all schools for the dropdown."""
        return School.objects.select_related('educational_level').all().order_by('name')
    
    def get_combinations(self):
        """Get all combinations for the dropdown."""
        return Combination.objects.select_related('educational_level').all().order_by('code')
    
    def get_class_levels(self):
        """Get all class levels for the dropdown."""
        return ClassLevel.objects.select_related('educational_level').all().order_by('educational_level__level_type', 'order')
    
    def get_student_current_enrollment(self, student):
        """Get the student's current active enrollment."""
        if not student:
            return None
        
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_academic_year:
            return None
        
        return student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).select_related('class_level__educational_level', 'academic_year').first()
    
    def get_students_with_enrollment_data(self):
        """Get all students with their enrollment data as data attributes."""
        students = Student.objects.all().order_by('first_name', 'last_name')
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        student_options = []
        for student in students:
            enrollment = None
            if current_academic_year:
                enrollment = student.enrollments.filter(
                    status='active',
                    academic_year=current_academic_year
                ).select_related('class_level', 'academic_year').first()
            
            student_options.append({
                'id': student.pk,
                'name': student.full_name,
                'reg_number': student.registration_number,
                'has_enrollment': enrollment is not None,
                'current_class': enrollment.class_level.name if enrollment else '',
                'current_class_order': enrollment.class_level.order if enrollment else '',
                'current_academic_year': enrollment.academic_year.name if enrollment else '',
                'enrollment_year': enrollment.academic_year.start_date.year if enrollment else '',
            })
        
        return student_options
    
    def get(self, request, pk):
        history = get_object_or_404(StudentEducationHistory, pk=pk)
        form = StudentEducationHistoryForm(instance=history)
        
        # Disable student field (cannot change student for existing history)
        form.fields['student'].disabled = True
        form.fields['student'].widget.attrs['disabled'] = True
        form.fields['student'].queryset = Student.objects.filter(pk=history.student_id)
        
        # Get current active enrollment for the student
        active_enrollment = self.get_student_current_enrollment(history.student)
        
        # Prepare pre-selected student data for the template
        pre_selected_student_data = {
            'id': history.student.pk,
            'full_name': history.student.full_name,
            'registration_number': history.student.registration_number,
            'current_class': active_enrollment.class_level.name if active_enrollment else history.class_completed,
            'current_class_order': active_enrollment.class_level.order if active_enrollment else None,
            'current_academic_year': active_enrollment.academic_year.name if active_enrollment else 'Not enrolled',
            'current_academic_year_start': active_enrollment.academic_year.start_date.year if active_enrollment else None,
            'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
            'has_active_enrollment': active_enrollment is not None,
        }
        
        # Get all data for dropdowns
        student_options = self.get_students_with_enrollment_data()
        schools = self.get_schools()
        combinations = self.get_combinations()
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'history': history,
            'student': history.student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'student_options': student_options,
            'schools': schools,
            'combinations': combinations,
            'class_levels': class_levels,
            'title': f'Edit Education History - {history.student.full_name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        history = get_object_or_404(StudentEducationHistory, pk=pk)
        form = StudentEducationHistoryForm(request.POST, instance=history)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Education history update POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    history = form.save()
                    
                    message = f'Education history updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:student_education_history_detail', kwargs={'pk': history.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:student_education_history_detail', pk=history.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Education history update validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Education history update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating education history record: {e}')
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
        form.fields['student'].queryset = Student.objects.filter(pk=history.student_id)
        
        # Get current active enrollment
        active_enrollment = self.get_student_current_enrollment(history.student)
        
        # Prepare pre-selected student data
        pre_selected_student_data = {
            'id': history.student.pk,
            'full_name': history.student.full_name,
            'registration_number': history.student.registration_number,
            'current_class': active_enrollment.class_level.name if active_enrollment else history.class_completed,
            'current_class_order': active_enrollment.class_level.order if active_enrollment else None,
            'current_academic_year': active_enrollment.academic_year.name if active_enrollment else 'Not enrolled',
            'current_academic_year_start': active_enrollment.academic_year.start_date.year if active_enrollment else None,
            'current_stream': active_enrollment.stream_assignment.stream_class.name if active_enrollment and hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment else 'Not assigned',
            'has_active_enrollment': active_enrollment is not None,
        }
        
        # Get all data for dropdowns
        student_options = self.get_students_with_enrollment_data()
        schools = self.get_schools()
        combinations = self.get_combinations()
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'history': history,
            'student': history.student,
            'pre_selected_student': pre_selected_student_data,
            'active_enrollment': active_enrollment,
            'student_options': student_options,
            'schools': schools,
            'combinations': combinations,
            'class_levels': class_levels,
            'title': f'Edit Education History - {history.student.full_name}',
            'is_update': True
        })


class StudentEducationHistoryDeleteView(ManagementRequiredMixin, View):
    """Delete a student education history record."""
    
    def post(self, request, pk):
        history = get_object_or_404(StudentEducationHistory, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = history.student.full_name
            student = history.student
            
            with transaction.atomic():
                # Delete the education history record
                history.delete()
            
            message = f'Education history record for {student_name} deleted successfully.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:student_education_history_list')
                })
            
            messages.success(request, message)
            return redirect('management:student_education_history_list')
            
        except Exception as e:
            logger.error(f"Education history deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting education history record: {e}')
            return redirect('management:student_education_history_detail', pk=pk)