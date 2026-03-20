"""
portal_management/views/academics.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Academic structure CRUD for the Management portal.

Covers:
  - Educational levels
  - Academic years & terms
  - Departments
  - Class levels & streams
  - Subjects
  - Combinations & combination subjects
"""
import logging
import re
from django.db import transaction
from django.contrib import messages
from django.db import models
from django.db.models import Count, Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, TemplateView, View
from django.db.models import Count, Q, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, ClassLevel, Combination,
    CombinationSubject, Department, EducationalLevel,
    StreamClass, Student, StudentCombinationAssignment, StudentEnrollment, StudentStreamAssignment, StudentSubjectAssignment, Subject, Term,
)
from portal_management.forms.staff_form import AcademicYearForm, ClassLevelForm, CombinationForm, DepartmentForm, EducationalLevelForm, StreamClassForm, SubjectForm, TermForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from portal_management.forms.student_form import StudentEnrollmentForm

logger = logging.getLogger(__name__)
# ── Educational Level ─────────────────────────────────────────────────────────

class EducationalLevelListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/academic/educational_levels.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        levels = EducationalLevel.objects.annotate(
            subject_count=Count('subjects', distinct=True),
            class_count=Count('class_levels', distinct=True),
            student_count=Count('class_levels__student_enrollments', distinct=True),
        )
        ctx['levels'] = levels
        
        # Calculate counts by level type
        ctx['nursery_count'] = levels.filter(level_type='NURSERY').count()
        ctx['primary_count'] = levels.filter(level_type='PRIMARY').count()
        ctx['olevel_count'] = levels.filter(level_type='O_LEVEL').count()
        ctx['alevel_count'] = levels.filter(level_type='A_LEVEL').count()        
       
        return ctx


class EducationalLevelCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Educational Levels.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _create(self, request):
        form = EducationalLevelForm(request.POST)
        if form.is_valid():
            try:
                level = form.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Educational level "{level.name}" created successfully.',
                    'level': {
                        'id': level.pk,
                        'code': level.code,
                        'name': level.name,
                        'level_type': level.level_type,
                        'description': level.description,
                    }
                })
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors below.',
                'errors': form.errors
            }, status=400)
    
    def _update(self, request):
        level_id = request.POST.get('id')
        if not level_id:
            return JsonResponse({'success': False, 'message': 'Level ID required'}, status=400)
        
        level = get_object_or_404(EducationalLevel, pk=level_id)
        form = EducationalLevelForm(request.POST, instance=level)
        
        if form.is_valid():
            try:
                level = form.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Educational level "{level.name}" updated successfully.',
                    'level': {
                        'id': level.pk,
                        'code': level.code,
                        'name': level.name,
                        'level_type': level.level_type,
                        'description': level.description,
                    }
                })
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors below.',
                'errors': form.errors
            }, status=400)
    
    def _delete(self, request):
        level_id = request.POST.get('id')
        if not level_id:
            return JsonResponse({'success': False, 'message': 'Level ID required'}, status=400)
        
        level = get_object_or_404(EducationalLevel, pk=level_id)
        
        # Check dependencies
        if level.class_levels.exists() or level.subjects.exists():
            return JsonResponse({
                'success': False,
                'message': 'Cannot delete level that has classes or subjects.'
            }, status=400)
        
        try:
            level_name = level.name
            level.delete()
            return JsonResponse({
                'success': True,
                'message': f'Educational level "{level_name}" deleted successfully.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)




class SubjectCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Subjects.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _create(self, request):
        form = SubjectForm(request.POST)
        if form.is_valid():
            try:
                subject = form.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{subject.name}" created successfully.',
                    'subject': {
                        'id': subject.pk,
                        'code': subject.code,
                        'name': subject.name,
                        'is_compulsory': subject.is_compulsory,
                        'description': subject.description,
                    }
                })
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors below.',
                'errors': form.errors
            }, status=400)
    
    def _update(self, request):
        subject_id = request.POST.get('id')
        if not subject_id:
            return JsonResponse({'success': False, 'message': 'Subject ID required'}, status=400)
        
        subject = get_object_or_404(Subject, pk=subject_id)
        form = SubjectForm(request.POST, instance=subject)
        
        if form.is_valid():
            try:
                subject = form.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{subject.name}" updated successfully.',
                    'subject': {
                        'id': subject.pk,
                        'code': subject.code,
                        'name': subject.name,
                        'is_compulsory': subject.is_compulsory,
                        'description': subject.description,
                    }
                })
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
        else:
            return JsonResponse({
                'success': False,
                'message': 'Please correct the errors below.',
                'errors': form.errors
            }, status=400)
    
    def _delete(self, request):
        subject_id = request.POST.get('id')
        if not subject_id:
            return JsonResponse({'success': False, 'message': 'Subject ID required'}, status=400)
        
        subject = get_object_or_404(Subject, pk=subject_id)
        
        # Check dependencies
        if subject.combination_subjects.exists():
            return JsonResponse({
                'success': False,
                'message': 'Cannot delete subject that is part of combinations.'
            }, status=400)
        
        try:
            subject_name = subject.name
            subject.delete()
            return JsonResponse({
                'success': True,
                'message': f'Subject "{subject_name}" deleted successfully.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


class SubjectStudentsView(ManagementRequiredMixin, TemplateView):
    """View all students taking a specific subject with bulk operations."""
    template_name = 'portal_management/academic/subject_students.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        subject = get_object_or_404(Subject, pk=self.kwargs['pk'])
        ctx['subject'] = subject
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        ctx['current_academic_year'] = current_academic_year
        
        # Prefetch enrollments with related data
        enrollments_prefetch = Prefetch(
            'enrollments',
            queryset=StudentEnrollment.objects.filter(
                academic_year__is_active=True,
                status='active'
            ).select_related(
                'class_level',
                'academic_year'
            ).prefetch_related(
                'stream_assignment__stream_class',
                'combination_assignments'  # Prefetch combination assignments
            )
        )
        
        if subject.is_compulsory:
            # Compulsory subjects are taken by all students in the level
            students = Student.objects.filter(
                enrollments__class_level__educational_level=subject.educational_level,
                enrollments__academic_year__is_active=True,
                status='active'
            ).distinct().select_related(
                'user'
            ).prefetch_related(
                enrollments_prefetch
            ).order_by('first_name', 'last_name')
        else:
            # Optional subjects - get students from assignments
            students = Student.objects.filter(
                subject_assignments__subject=subject,
                subject_assignments__enrollment__academic_year__is_active=True
            ).distinct().select_related(
                'user'
            ).prefetch_related(
                enrollments_prefetch
            ).order_by('first_name', 'last_name')
            
            # For A-Level, also include students from combinations
            if subject.educational_level.level_type == 'A_LEVEL':
                combo_students = Student.objects.filter(
                    combination_assignments__combination__combination_subjects__subject=subject,
                    combination_assignments__is_active=True,
                    combination_assignments__enrollment__academic_year__is_active=True
                ).distinct().select_related(
                    'user'
                ).prefetch_related(
                    enrollments_prefetch
                )
                students = (students | combo_students).distinct().order_by('first_name', 'last_name')
        
        # Annotate each student with their enrollment and stream info
        for student in students:
            # Get active enrollment
            active_enrollment = None
            for enrollment in student.enrollments.all():
                if enrollment.academic_year.is_active and enrollment.status == 'active':
                    active_enrollment = enrollment
                    break
            
            student.active_enrollment = active_enrollment
            student.current_class = active_enrollment.class_level if active_enrollment else None
            student.current_stream = active_enrollment.stream_assignment.stream_class if active_enrollment and hasattr(active_enrollment, 'stream_assignment') else None
            
            # Get current combination for A-Level students
            if subject.educational_level.level_type == 'A_LEVEL':
                current_combination = None
                if active_enrollment:
                    current_combination = active_enrollment.current_combination
                student.current_combination = current_combination
        
        ctx['students'] = students
        ctx['student_count'] = students.count()
        
        # Get available students for bulk assign (O-Level only for elective subjects)
        if not subject.is_compulsory and subject.educational_level.level_type == 'O_LEVEL':
            # Students in this level who are NOT already assigned this subject
            available_students = Student.objects.filter(
                enrollments__class_level__educational_level=subject.educational_level,
                enrollments__academic_year__is_active=True,
                status='active'
            ).exclude(
                subject_assignments__subject=subject,
                subject_assignments__enrollment__academic_year__is_active=True
            ).distinct().select_related(
                'user'
            ).prefetch_related(
                enrollments_prefetch
            ).order_by('first_name', 'last_name')
            
            # Annotate available students
            for student in available_students:
                active_enrollment = None
                for enrollment in student.enrollments.all():
                    if enrollment.academic_year.is_active and enrollment.status == 'active':
                        active_enrollment = enrollment
                        break
                
                student.active_enrollment = active_enrollment
                student.current_class = active_enrollment.class_level if active_enrollment else None
                student.current_stream = active_enrollment.stream_assignment.stream_class if active_enrollment and hasattr(active_enrollment, 'stream_assignment') else None
            
            ctx['available_students'] = available_students
            ctx['available_count'] = available_students.count()
        
        # Get class levels for filtering
        ctx['class_levels'] = ClassLevel.objects.filter(
            educational_level=subject.educational_level
        ).order_by('order')
        
        # Get streams for filtering
        ctx['streams'] = StreamClass.objects.filter(
            class_level__educational_level=subject.educational_level
        ).order_by('class_level', 'stream_letter')
        
        return ctx


class SubjectBulkAssignView(ManagementRequiredMixin, View):
    """Bulk assign students to a subject."""
    
    def post(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get parameters
        student_ids = request.POST.getlist('student_ids')
        class_level_id = request.POST.get('class_level')
        stream_id = request.POST.get('stream')
        select_all = request.POST.get('select_all') == 'true'
        
        if not student_ids and not select_all:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No students selected.',
                    'errors': {'student_ids': ['Please select at least one student.']}
                }, status=400)
            messages.error(request, 'No students selected.')
            return redirect('management:subject_students', pk=pk)
        
        try:
            with transaction.atomic():
                # Get eligible students based on filters
                if select_all:
                    # Get all eligible students based on filters
                    students_qs = Student.objects.filter(
                        enrollments__class_level__educational_level=subject.educational_level,
                        enrollments__academic_year__is_active=True,
                        status='active'
                    ).distinct()
                    
                    if class_level_id:
                        students_qs = students_qs.filter(
                            enrollments__class_level_id=class_level_id
                        )
                    
                    if stream_id:
                        students_qs = students_qs.filter(
                            enrollments__stream_assignment__stream_class_id=stream_id
                        )
                    
                    # Exclude students already assigned this subject
                    students_qs = students_qs.exclude(
                        subject_assignments__subject=subject,
                        subject_assignments__enrollment__academic_year__is_active=True
                    )
                    
                    students = list(students_qs)
                else:
                    students = Student.objects.filter(pk__in=student_ids)
                
                if not students:
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': 'No eligible students found.'
                        }, status=400)
                    messages.warning(request, 'No eligible students found.')
                    return redirect('management:subject_students', pk=pk)
                
                # Create assignments
                created_count = 0
                errors = []
                
                for student in students:
                    try:
                        # Get active enrollment for this student
                        enrollment = StudentEnrollment.objects.filter(
                            student=student,
                            academic_year__is_active=True,
                            class_level__educational_level=subject.educational_level
                        ).first()
                        
                        if not enrollment:
                            errors.append(f"{student.full_name}: No active enrollment found")
                            continue
                        
                        # Check if assignment already exists
                        if StudentSubjectAssignment.objects.filter(
                            student=student,
                            enrollment=enrollment,
                            subject=subject
                        ).exists():
                            errors.append(f"{student.full_name}: Already assigned this subject")
                            continue
                        
                        # Create assignment
                        StudentSubjectAssignment.objects.create(
                            student=student,
                            enrollment=enrollment,
                            subject=subject
                        )
                        created_count += 1
                        
                    except Exception as e:
                        errors.append(f"{student.full_name}: {str(e)}")
                
                message = f"Successfully assigned {created_count} student(s) to {subject.name}."
                if errors:
                    message += f" {len(errors)} error(s) occurred."
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'created_count': created_count,
                        'error_count': len(errors),
                        'errors': errors[:5]  # Return first 5 errors
                    })
                
                if created_count > 0:
                    messages.success(request, message)
                if errors:
                    messages.warning(request, f"{len(errors)} errors occurred. Check logs for details.")
                
                return redirect('management:subject_students', pk=pk)
                
        except Exception as e:
            logger.error(f"Bulk assign error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error during bulk assignment: {e}')
            return redirect('management:subject_students', pk=pk)


class SubjectBulkRemoveView(ManagementRequiredMixin, View):
    """Bulk remove students from a subject."""
    
    def post(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get parameters
        student_ids = request.POST.getlist('student_ids')
        select_all = request.POST.get('select_all') == 'true'
        
        if not student_ids and not select_all:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No students selected.',
                    'errors': {'student_ids': ['Please select at least one student.']}
                }, status=400)
            messages.error(request, 'No students selected.')
            return redirect('management:subject_students', pk=pk)
        
        try:
            with transaction.atomic():
                # Get assignments to remove
                assignments_qs = StudentSubjectAssignment.objects.filter(
                    subject=subject,
                    enrollment__academic_year__is_active=True
                )
                
                if select_all:
                    # Remove all assignments for this subject
                    assignments = list(assignments_qs)
                else:
                    assignments_qs = assignments_qs.filter(student_id__in=student_ids)
                    assignments = list(assignments_qs)
                
                if not assignments:
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': 'No matching assignments found to remove.'
                        }, status=400)
                    messages.warning(request, 'No matching assignments found to remove.')
                    return redirect('management:subject_students', pk=pk)
                
                # Delete assignments
                count = len(assignments)
                student_names = [a.student.full_name for a in assignments]
                assignments_qs.delete()
                
                message = f"Successfully removed {count} student(s) from {subject.name}."
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'removed_count': count,
                        'students': student_names[:10]  # Return first 10 names
                    })
                
                messages.success(request, message)
                return redirect('management:subject_students', pk=pk)
                
        except Exception as e:
            logger.error(f"Bulk remove error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error during bulk removal: {e}')
            return redirect('management:subject_students', pk=pk)


class GetAvailableStudentsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get available students for bulk assign based on filters."""
    
    def get(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        
        class_level_id = request.GET.get('class_level')
        stream_id = request.GET.get('stream')
        search = request.GET.get('search', '')
        
        # Base queryset - students in this level not assigned this subject
        students = Student.objects.filter(
            enrollments__class_level__educational_level=subject.educational_level,
            enrollments__academic_year__is_active=True,
            status='active'
        ).exclude(
            subject_assignments__subject=subject,
            subject_assignments__enrollment__academic_year__is_active=True
        ).distinct().select_related(
            'user'
        ).prefetch_related(
            'enrollments__class_level',
            'enrollments__stream_assignment__stream_class'
        )
        
        # Apply filters
        if class_level_id:
            students = students.filter(enrollments__class_level_id=class_level_id)
        
        if stream_id:
            students = students.filter(enrollments__stream_assignment__stream_class_id=stream_id)
        
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(registration_number__icontains=search)
            )
        
        # Limit results for performance
        students = students.order_by('first_name', 'last_name')[:50]
        
        data = [{
            'id': s.pk,
            'full_name': s.full_name,
            'registration_number': s.registration_number,
            'class': s.enrollments.first().class_level.name if s.enrollments.first() else None,
            'stream': s.enrollments.first().stream_assignment.stream_class.name if s.enrollments.first() and hasattr(s.enrollments.first(), 'stream_assignment') else None,
        } for s in students]
        
        return JsonResponse({'students': data})

# ============================================================================
# STUDENT SUBJECT ASSIGNMENT VIEWS (O-Level Electives)
# ============================================================================

class StudentSubjectAssignmentListView(ManagementRequiredMixin, TemplateView):
    """List all O-Level student subject assignments with filtering."""
    template_name = 'portal_management/academic/student_subject_assignments.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        academic_year_id = self.request.GET.get('academic_year')
        class_level_id = self.request.GET.get('class_level')
        subject_id = self.request.GET.get('subject')
        stream_id = self.request.GET.get('stream')
        student_id = self.request.GET.get('student')
        
        # Base queryset - only O-Level
        assignments = StudentSubjectAssignment.objects.filter(
            enrollment__class_level__educational_level__level_type='O_LEVEL'
        ).select_related(
            'student', 'enrollment', 'subject',
            'enrollment__class_level',
            'enrollment__academic_year',
            'enrollment__stream_assignment__stream_class'
        ).order_by(
            '-enrollment__academic_year__start_date',
            'enrollment__class_level__order',
            'student__first_name'
        )
        
        # Apply filters
        if academic_year_id:
            assignments = assignments.filter(enrollment__academic_year_id=academic_year_id)
        if class_level_id:
            assignments = assignments.filter(enrollment__class_level_id=class_level_id)
        if subject_id:
            assignments = assignments.filter(subject_id=subject_id)
        if stream_id:
            assignments = assignments.filter(enrollment__stream_assignment__stream_class_id=stream_id)
        if student_id:
            assignments = assignments.filter(student_id=student_id)
        
        ctx['assignments'] = assignments
        ctx['total_assignments'] = assignments.count()
        
        # Get filter options (only O-Level)
        ctx['academic_years'] = AcademicYear.objects.all().order_by('-start_date')
        ctx['class_levels'] = ClassLevel.objects.filter(
            educational_level__level_type='O_LEVEL'
        ).order_by('educational_level', 'order')
        ctx['subjects'] = Subject.objects.filter(
            educational_level__level_type='O_LEVEL',
            is_compulsory=False
        ).order_by('name')
        ctx['streams'] = StreamClass.objects.filter(
            class_level__educational_level__level_type='O_LEVEL'
        ).order_by('class_level', 'stream_letter')
        
        # Get students with O-Level enrollments for quick add
        ctx['students'] = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='O_LEVEL',
            enrollments__academic_year__is_active=True,
            status='active'
        ).distinct().order_by('first_name', 'last_name')
        
        # Store selected filters for template
        ctx['selected_academic_year'] = int(academic_year_id) if academic_year_id else None
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['selected_subject'] = int(subject_id) if subject_id else None
        ctx['selected_stream'] = int(stream_id) if stream_id else None
        ctx['selected_student'] = int(student_id) if student_id else None
        
        # Statistics
        ctx['total_students_with_electives'] = Student.objects.filter(
            subject_assignments__enrollment__academic_year__is_active=True
        ).distinct().count()
        
        ctx['total_elective_assignments'] = StudentSubjectAssignment.objects.filter(
            enrollment__academic_year__is_active=True
        ).count()
        
        return ctx


class StudentSubjectAssignmentCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Student Subject Assignments.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _create(self, request):
        student_id = request.POST.get('student')
        enrollment_id = request.POST.get('enrollment')
        subject_id = request.POST.get('subject')
        
        # Validate required fields
        if not all([student_id, enrollment_id, subject_id]):
            return JsonResponse({
                'success': False,
                'message': 'Student, Enrollment, and Subject are required.',
                'errors': {
                    'student': ['This field is required.'] if not student_id else [],
                    'enrollment': ['This field is required.'] if not enrollment_id else [],
                    'subject': ['This field is required.'] if not subject_id else [],
                }
            }, status=400)
        
        # Check if assignment already exists
        if StudentSubjectAssignment.objects.filter(
            enrollment_id=enrollment_id,
            subject_id=subject_id
        ).exists():
            return JsonResponse({
                'success': False,
                'message': 'This subject is already assigned to this student enrollment.',
                'errors': {
                    'subject': ['This subject is already assigned to this student.']
                }
            }, status=400)
        
        try:
            with transaction.atomic():
                assignment = StudentSubjectAssignment.objects.create(
                    student_id=student_id,
                    enrollment_id=enrollment_id,
                    subject_id=subject_id
                )
                
                # Get related data for response
                assignment = StudentSubjectAssignment.objects.select_related(
                    'student', 'subject', 'enrollment__class_level', 'enrollment__academic_year'
                ).get(pk=assignment.pk)
                
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{assignment.subject.name}" assigned to {assignment.student.full_name} successfully.',
                    'assignment': {
                        'id': assignment.pk,
                        'student': assignment.student.full_name,
                        'student_id': assignment.student_id,
                        'student_reg': assignment.student.registration_number,
                        'subject': assignment.subject.name,
                        'subject_id': assignment.subject_id,
                        'subject_code': assignment.subject.code,
                        'enrollment': str(assignment.enrollment),
                        'academic_year': assignment.enrollment.academic_year.name,
                        'class_level': assignment.enrollment.class_level.name,
                        'stream': assignment.stream if hasattr(assignment, 'stream') else None,
                    }
                })
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': 'Validation error.',
                'errors': {'__all__': e.messages if hasattr(e, 'messages') else [str(e)]}
            }, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    def _update(self, request):
        assignment_id = request.POST.get('id')
        subject_id = request.POST.get('subject')
        
        if not assignment_id:
            return JsonResponse({'success': False, 'message': 'Assignment ID required'}, status=400)
        
        assignment = get_object_or_404(StudentSubjectAssignment, pk=assignment_id)
        old_subject = assignment.subject.name
        
        # Check if new subject is already assigned to this enrollment
        if subject_id and int(subject_id) != assignment.subject_id:
            if StudentSubjectAssignment.objects.filter(
                enrollment=assignment.enrollment,
                subject_id=subject_id
            ).exists():
                return JsonResponse({
                    'success': False,
                    'message': 'This subject is already assigned to this student enrollment.',
                    'errors': {
                        'subject': ['This subject is already assigned to this student.']
                    }
                }, status=400)
            
            assignment.subject_id = subject_id
        
        try:
            assignment.save()
            
            # Refresh with related data
            assignment = StudentSubjectAssignment.objects.select_related(
                'student', 'subject'
            ).get(pk=assignment.pk)
            
            return JsonResponse({
                'success': True,
                'message': f'Subject assignment updated from "{old_subject}" to "{assignment.subject.name}" successfully.',
                'assignment': {
                    'id': assignment.pk,
                    'student': assignment.student.full_name,
                    'student_id': assignment.student_id,
                    'subject': assignment.subject.name,
                    'subject_id': assignment.subject_id,
                    'subject_code': assignment.subject.code,
                }
            })
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': 'Validation error.',
                'errors': {'__all__': e.messages if hasattr(e, 'messages') else [str(e)]}
            }, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    def _delete(self, request):
        assignment_id = request.POST.get('id')
        
        if not assignment_id:
            return JsonResponse({'success': False, 'message': 'Assignment ID required'}, status=400)
        
        assignment = get_object_or_404(StudentSubjectAssignment, pk=assignment_id)
        
        try:
            student_name = assignment.student.full_name
            subject_name = assignment.subject.name
            assignment.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Subject "{subject_name}" removed from {student_name} successfully.'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


class GetStudentEnrollmentsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get O-Level enrollments for a selected student."""
    
    def get(self, request):
        student_id = request.GET.get('student_id')
        academic_year_id = request.GET.get('academic_year_id')
        
        if not student_id:
            return JsonResponse({'enrollments': []})
        
        enrollments = StudentEnrollment.objects.filter(
            student_id=student_id,
            class_level__educational_level__level_type='O_LEVEL',
            status='active'
        ).select_related('class_level', 'academic_year').order_by('-academic_year__start_date')
        
        if academic_year_id:
            enrollments = enrollments.filter(academic_year_id=academic_year_id)
        
        data = [{
            'id': e.pk,
            'text': f"{e.class_level.name} - {e.academic_year.name}",
            'academic_year': e.academic_year.name,
            'academic_year_id': e.academic_year_id,
            'class_level': e.class_level.name,
            'class_level_id': e.class_level_id,
            'stream': e.stream_assignment.stream_class.name if hasattr(e, 'stream_assignment') else None,
        } for e in enrollments]
        
        return JsonResponse({'enrollments': data})


class GetAvailableSubjectsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get available optional subjects for a student enrollment."""
    
    def get(self, request):
        enrollment_id = request.GET.get('enrollment_id')
        current_assignment_id = request.GET.get('current_assignment_id')
        
        if not enrollment_id:
            return JsonResponse({'subjects': []})
        
        try:
            enrollment = StudentEnrollment.objects.select_related(
                'class_level__educational_level'
            ).get(pk=enrollment_id)
        except StudentEnrollment.DoesNotExist:
            return JsonResponse({'subjects': []})
        
        # Get all optional subjects for this educational level
        available_subjects = Subject.objects.filter(
            educational_level=enrollment.class_level.educational_level,
            is_compulsory=False
        ).exclude(
            # Exclude subjects already assigned to this enrollment
            student_assignments__enrollment=enrollment
        ).order_by('name')
        
        # If updating, include the current subject
        if current_assignment_id:
            try:
                current = StudentSubjectAssignment.objects.get(pk=current_assignment_id)
                available_subjects = available_subjects | Subject.objects.filter(pk=current.subject_id)
            except:
                pass
        
        data = [{
            'id': s.pk,
            'text': f"{s.name} ({s.code})",
            'code': s.code,
            'name': s.name,
        } for s in available_subjects]
        
        return JsonResponse({'subjects': data})


class GetStudentsByFiltersView(ManagementRequiredMixin, View):
    """AJAX endpoint to get students based on class/stream filters."""
    
    def get(self, request):
        class_level_id = request.GET.get('class_level_id')
        stream_id = request.GET.get('stream_id')
        academic_year_id = request.GET.get('academic_year_id')
        
        if not academic_year_id:
            # Default to active academic year
            active_year = AcademicYear.objects.filter(is_active=True).first()
            academic_year_id = active_year.pk if active_year else None
        
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='O_LEVEL',
            status='active'
        ).distinct()
        
        if academic_year_id:
            students = students.filter(enrollments__academic_year_id=academic_year_id)
        
        if class_level_id:
            students = students.filter(enrollments__class_level_id=class_level_id)
        
        if stream_id:
            students = students.filter(enrollments__stream_assignment__stream_class_id=stream_id)
        
        students = students.order_by('first_name', 'last_name').select_related('user')
        
        data = [{
            'id': s.pk,
            'text': f"{s.full_name} ({s.registration_number})",
            'full_name': s.full_name,
            'registration_number': s.registration_number,
        } for s in students[:50]]  # Limit to 50 for performance
        
        return JsonResponse({'students': data})
    

class LevelSubjectsView(ManagementRequiredMixin, TemplateView):
    """View all subjects in an educational level."""
    template_name = 'portal_management/academic/level_subjects.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        level = get_object_or_404(EducationalLevel, pk=self.kwargs['pk'])
        ctx['level'] = level
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if level.level_type == 'A_LEVEL':
            # For A-Level, we need to consider both direct assignments and combinations
            subjects = Subject.objects.filter(
                educational_level=level
            ).annotate(
                # Count from StudentSubjectAssignment
                assignment_count=Coalesce(Subquery(
                    StudentSubjectAssignment.objects.filter(
                        subject=OuterRef('pk'),
                        enrollment__academic_year__is_active=True
                    ).values('subject').annotate(
                        count=Count('id')
                    ).values('count')[:1],
                    output_field=IntegerField()
                ), 0),
                # Count from Combination enrollments
                combination_count=Coalesce(Subquery(
                    StudentEnrollment.objects.filter(
                        combination__combination_subjects__subject=OuterRef('pk'),
                        academic_year__is_active=True
                    ).values('combination__combination_subjects__subject').annotate(
                        count=Count('id', distinct=True)
                    ).values('count')[:1],
                    output_field=IntegerField()
                ), 0)
            ).order_by('name')
            
            # Calculate total count and prepare display value
            for subject in subjects:
                if subject.is_compulsory:
                    subject.display_student_count = "-"
                else:
                    total = subject.assignment_count + subject.combination_count
                    subject.display_student_count = total if total > 0 else "0"
        else:
            # For non A-Level, just count from StudentSubjectAssignment
            subjects = Subject.objects.filter(
                educational_level=level
            ).annotate(
                student_count=Coalesce(Subquery(
                    StudentSubjectAssignment.objects.filter(
                        subject=OuterRef('pk'),
                        enrollment__academic_year__is_active=True
                    ).values('subject').annotate(
                        count=Count('id')
                    ).values('count')[:1],
                    output_field=IntegerField()
                ), 0)
            ).order_by('name')
            
            # Prepare display value
            for subject in subjects:
                if subject.is_compulsory:
                    subject.display_student_count = "-"
                else:
                    subject.display_student_count = subject.student_count if subject.student_count > 0 else "0"
        
        ctx['subjects'] = subjects
        
        # Calculate statistics
        ctx['compulsory_count'] = subjects.filter(is_compulsory=True).count()
        ctx['optional_count'] = subjects.filter(is_compulsory=False).count()
        
        # Get total students in this level for context
        ctx['total_students_in_level'] = Student.objects.filter(
            enrollments__class_level__educational_level=level,
            enrollments__academic_year__is_active=True,
            status='active'
        ).distinct().count()
        
        return ctx

class LevelClassesView(ManagementRequiredMixin, TemplateView):
    """View all classes in an educational level."""
    template_name = 'portal_management/academic/level_classes.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        level = get_object_or_404(EducationalLevel, pk=self.kwargs['pk'])
        ctx['level'] = level
        ctx['classes'] = ClassLevel.objects.filter(
            educational_level=level
        ).annotate(
            stream_count=Count('streams'),
            student_count=Count('student_enrollments')
        ).order_by('order')
        return ctx


class LevelStudentsView(ManagementRequiredMixin, TemplateView):
    """View all students in an educational level."""
    template_name = 'portal_management/academic/level_students.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        level = get_object_or_404(EducationalLevel, pk=self.kwargs['pk'])
        ctx['level'] = level
        
        # Get students through enrollments in this educational level
        students = Student.objects.filter(
            enrollments__class_level__educational_level=level
        ).distinct().select_related('user').prefetch_related(
            'enrollments__class_level'
        ).order_by('first_name', 'last_name')
        
        ctx['students'] = students
        return ctx
        


# ============================================================================
# ACADEMIC YEAR CRUD
# ============================================================================

class AcademicYearListView(ManagementRequiredMixin, TemplateView):
    """List all academic years with CRUD operations."""
    template_name = 'portal_management/academic/academic_years.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get all academic years ordered by start date (newest first)
        years = AcademicYear.objects.all().order_by('-start_date')
        
        # Annotate with additional info
        for year in years:
            year.term_count = year.terms.count()
            year.student_count = StudentEnrollment.objects.filter(
                academic_year=year
            ).count()
            year.has_active_term = year.terms.filter(is_active=True).exists()
        
        ctx['academic_years'] = years
        ctx['total_years'] = years.count()
        ctx['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        
        return ctx


class AcademicYearCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Academic Years.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """
        Format validation errors into a consistent structure.
        Handles both field-specific errors and non-field errors (__all__).
        """
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            # Django form errors format
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            # Already a dictionary, ensure values are lists of strings
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            # List of non-field errors
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            # Single error message
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_year_name_and_dates(self, name, start_date, end_date, year_id=None):
        """
        Comprehensive validation for academic year name and dates.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        import re
        from datetime import datetime
        
        # Validate name format (YYYY/YYYY)
        if not re.match(r'^\d{4}/\d{4}$', name):
            errors['name'] = ['Name must be in format YYYY/YYYY (e.g., 2024/2025)']
            return False, errors
        
        # Extract years from name
        start_year, end_year = map(int, name.split('/'))
        
        # Validate that end year is exactly one year after start year
        if end_year != start_year + 1:
            errors['name'] = ['Academic years must be consecutive (e.g., 2024/2025, not 2024/2026)']
            return False, errors
        
        # Validate that the years are reasonable (not too far in past/future)
        current_year = datetime.now().year
        if start_year < 1950 or start_year > current_year + 10:
            errors['name'] = [f'Start year {start_year} is invalid. Must be between 1950 and {current_year + 10}.']
            return False, errors
        
        if end_year < 1951 or end_year > current_year + 11:
            errors['name'] = [f'End year {end_year} is invalid. Must be between 1951 and {current_year + 11}.']
            return False, errors
        
        # Check for gaps in the academic year sequence
        # Get all existing academic years ordered by start_year
        existing_years = AcademicYear.objects.exclude(pk=year_id).values_list('name', flat=True)
        
        for existing in existing_years:
            existing_start, existing_end = map(int, existing.split('/'))
            
            # Check if this new year creates a gap in the sequence
            # Case 1: New year is after existing year but not consecutive
            if start_year > existing_end and start_year != existing_end + 1:
                errors['name'] = errors.get('name', []) + [
                    f'Gap detected: There is a gap between {existing_end} and {start_year}. '
                    f'Academic years must be consecutive without gaps (e.g., 2024/2025, 2025/2026, 2026/2027).'
                ]
            
            # Case 2: New year is before existing year but not consecutive
            if end_year < existing_start and end_year != existing_start - 1:
                errors['name'] = errors.get('name', []) + [
                    f'Gap detected: There is a gap between {end_year} and {existing_start}. '
                    f'Academic years must be consecutive without gaps (e.g., 2024/2025, 2025/2026, 2026/2027).'
                ]
        
        # Also check if the new year overlaps with existing years (though overlap check will catch this)
        # But we want to ensure the sequence is continuous
        
        # Convert string dates to date objects if they're strings
        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            from datetime import datetime
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Validate that dates fall within the academic year range
        # Check if start_date year matches start_year or end_year (allow for academic year spanning two calendar years)
        if start_date.year not in [start_year, end_year]:
            errors['start_date'] = [f'Start date year ({start_date.year}) must be either {start_year} or {end_year} for academic year {name}.']
        
        # Check if end_date year matches end_year
        if end_date.year != end_year:
            errors['end_date'] = [f'End date year ({end_date.year}) must be {end_year} for academic year {name}.']
        
        # Ensure start_date is before end_date
        if start_date >= end_date:
            errors['__all__'] = ['Start date must be before end date.']
        
        # Ensure the date range is reasonable (not too short or too long)
        date_range_days = (end_date - start_date).days
        if date_range_days < 300:  # Less than ~10 months
            errors['__all__'] = errors.get('__all__', []) + ['Academic year must be at least 10 months long.']
        if date_range_days > 400:  # More than ~13 months
            errors['__all__'] = errors.get('__all__', []) + ['Academic year cannot be longer than 400 days.']
        
        # Check for overlapping with existing academic years
        overlapping_years = AcademicYear.objects.exclude(pk=year_id).filter(
            models.Q(start_date__lt=end_date, end_date__gt=start_date)
        )
        
        if overlapping_years.exists():
            overlapping = overlapping_years.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Date range overlaps with existing academic year "{overlapping.name}" '
                f'({overlapping.start_date.strftime("%Y-%m-%d")} to {overlapping.end_date.strftime("%Y-%m-%d")}).'
            ]
        
        # Also check for year name conflicts (though model has unique constraint)
        if AcademicYear.objects.filter(name=name).exclude(pk=year_id).exists():
            errors['name'] = errors.get('name', []) + [f'Academic year "{name}" already exists.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([name, start_date, end_date]):
            errors = {}
            if not name:
                errors['name'] = ['Name is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_year_name_and_dates(name, start_date, end_date)
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                year = AcademicYear(
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    is_active=is_active
                )
                year.full_clean()
                year.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Academic year "{year.name}" created successfully.',
                    'academic_year': {
                        'id': year.pk,
                        'name': year.name,
                        'start_date': year.start_date.strftime('%Y-%m-%d'),
                        'end_date': year.end_date.strftime('%Y-%m-%d'),
                        'is_active': year.is_active,
                        'term_count': 0,
                        'student_count': 0,
                    }
                })
                
        except ValidationError as e:
            # Format the validation errors
            formatted_errors = self._format_errors(e)
            
            # Create a user-friendly message
            if '__all__' in formatted_errors:
                message = formatted_errors['__all__'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating academic year: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {
                    '__all__': ['An unexpected error occurred. Please try again.']
                }
            }, status=500)
    
    def _update(self, request):
        year_id = request.POST.get('id')
        if not year_id:
            return JsonResponse({
                'success': False,
                'message': 'Academic Year ID required',
                'errors': {
                    'id': ['Academic Year ID is required.']
                }
            }, status=400)
        
        try:
            year = get_object_or_404(AcademicYear, pk=year_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Academic year not found.',
                'errors': {
                    '__all__': ['The requested academic year does not exist.']
                }
            }, status=404)
        
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([name, start_date, end_date]):
            errors = {}
            if not name:
                errors['name'] = ['Name is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation (pass year_id to exclude current year from overlap check)
        is_valid, validation_errors = self._validate_year_name_and_dates(name, start_date, end_date, year_id)
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                year.name = name
                year.start_date = start_date
                year.end_date = end_date
                year.is_active = is_active
                
                year.full_clean()
                year.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Academic year "{year.name}" updated successfully.',
                    'academic_year': {
                        'id': year.pk,
                        'name': year.name,
                        'start_date': year.start_date.strftime('%Y-%m-%d'),
                        'end_date': year.end_date.strftime('%Y-%m-%d'),
                        'is_active': year.is_active,
                    }
                })
                
        except ValidationError as e:
            # Format the validation errors
            formatted_errors = self._format_errors(e)
            
            # Create a user-friendly message
            if '__all__' in formatted_errors:
                message = formatted_errors['__all__'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating academic year {year_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {
                    '__all__': ['An unexpected error occurred. Please try again.']
                }
            }, status=500)
    
    def _delete(self, request):
        year_id = request.POST.get('id')
        if not year_id:
            return JsonResponse({
                'success': False,
                'message': 'Academic Year ID required',
                'errors': {
                    'id': ['Academic Year ID is required.']
                }
            }, status=400)
        
        try:
            year = get_object_or_404(AcademicYear, pk=year_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Academic year not found.',
                'errors': {
                    '__all__': ['The requested academic year does not exist.']
                }
            }, status=404)
        
        # Check dependencies
        dependency_errors = {}
        
        if year.terms.exists():
            dependency_errors['__all__'] = [
                'Cannot delete academic year that has terms. Please delete all terms first.'
            ]
        
        if StudentEnrollment.objects.filter(academic_year=year).exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete academic year that has student enrollments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete academic year that has student enrollments.'
                ]
        
        if dependency_errors:
            return JsonResponse({
                'success': False,
                'message': dependency_errors['__all__'][0],
                'errors': dependency_errors
            }, status=400)
        
        try:
            year_name = year.name
            year.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Academic year "{year_name}" deleted successfully.'
            })
            
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting academic year {year_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {
                    '__all__': ['An unexpected error occurred while deleting. Please try again.']
                }
            }, status=500)
        

class SetActiveAcademicYearView(ManagementRequiredMixin, View):
    """Set an academic year as active."""
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        year_id = request.POST.get('id')
        if not year_id:
            if is_ajax:
                return JsonResponse({'success': False, 'message': 'Academic Year ID required'}, status=400)
            messages.error(request, 'Academic Year ID required.')
            return redirect('management:academic_year_list')
        
        year = get_object_or_404(AcademicYear, pk=year_id)
        
        try:
            with transaction.atomic():
                # Deactivate all other years
                AcademicYear.objects.exclude(pk=year.pk).update(is_active=False)
                # Activate selected year
                year.is_active = True
                year.save()
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': f'Academic year "{year.name}" is now active.',
                        'academic_year': {
                            'id': year.pk,
                            'name': year.name,
                            'is_active': True
                        }
                    })
                
                messages.success(request, f'Academic year "{year.name}" is now active.')
                return redirect('management:academic_year_list')
                
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error setting active year: {e}')
            return redirect('management:academic_year_list')


class GetAcademicYearDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get academic year details for editing."""
    
    def get(self, request, pk):
        year = get_object_or_404(AcademicYear, pk=pk)
        
        return JsonResponse({
            'id': year.pk,
            'name': year.name,
            'start_date': year.start_date.strftime('%Y-%m-%d'),
            'end_date': year.end_date.strftime('%Y-%m-%d'),
            'is_active': year.is_active,
            'term_count': year.terms.count(),
            'student_count': StudentEnrollment.objects.filter(academic_year=year).count(),
        })


# ============================================================================
# TERM CRUD VIEWS
# ============================================================================

class AcademicYearTermsView(ManagementRequiredMixin, TemplateView):
    """View all terms in an academic year."""
    template_name = 'portal_management/academic/terms.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        academic_year = get_object_or_404(AcademicYear, pk=self.kwargs['pk'])
        ctx['academic_year'] = academic_year
        
        # Get all terms for this academic year
        terms = Term.objects.filter(academic_year=academic_year).order_by('term_number')
        
        # Annotate with additional info
        for term in terms:
            term.exam_count = term.exam_sessions.count()
            term.has_exams = term.exam_sessions.exists()
        
        ctx['terms'] = terms
        ctx['total_terms'] = terms.count()
        ctx['active_term'] = terms.filter(is_active=True).first()
        
        return ctx


class TermCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Terms.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_term_dates(self, academic_year, term_number, start_date, end_date, term_id=None):
        """
        Comprehensive validation for term dates.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        from datetime import date
        
        # Convert string dates to date objects if they're strings
        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            from datetime import datetime
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Ensure start_date is before end_date
        if start_date >= end_date:
            errors['__all__'] = ['Start date must be before end date.']
        
        # Validate that term dates are within the academic year
        if start_date < academic_year.start_date:
            errors['start_date'] = [f'Term start date ({start_date}) cannot be before academic year start ({academic_year.start_date}).']
        
        if end_date > academic_year.end_date:
            errors['end_date'] = [f'Term end date ({end_date}) cannot be after academic year end ({academic_year.end_date}).']
        
        # Validate term duration (reasonable length for a term)
        term_duration_days = (end_date - start_date).days
        if term_duration_days < 60:  # Less than ~2 months
            errors['__all__'] = errors.get('__all__', []) + [f'Term duration ({term_duration_days} days) is too short. Terms must be at least 60 days.']
        if term_duration_days > 150:  # More than ~5 months
            errors['__all__'] = errors.get('__all__', []) + [f'Term duration ({term_duration_days} days) is too long. Terms cannot exceed 150 days.']
        
        # Check for overlapping with other terms in the same academic year
        overlapping_terms = Term.objects.filter(
            academic_year=academic_year
        ).exclude(pk=term_id).filter(
            models.Q(start_date__lt=end_date, end_date__gt=start_date)
        )
        
        if overlapping_terms.exists():
            overlapping = overlapping_terms.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Date range overlaps with existing term "{overlapping.name}" '
                f'({overlapping.start_date.strftime("%Y-%m-%d")} to {overlapping.end_date.strftime("%Y-%m-%d")}).'
            ]
        
        # Check for gaps between terms (optional, but good practice)
        # This ensures terms are properly sequenced without large gaps
        if term_id is None:  # Only for new terms
            # Get the maximum end date of existing terms in this academic year
            max_end_date = Term.objects.filter(
                academic_year=academic_year
            ).aggregate(models.Max('end_date'))['end_date__max']
            
            if max_end_date and start_date < max_end_date:
                # This would be caught by overlap check, but adding a specific message
                pass
        
        # Validate term number is appropriate (1,2,3)
        if term_number not in ['1', '2', '3']:
            errors['term_number'] = ['Term number must be 1, 2, or 3.']
        
        # Check if this term number already exists in this academic year
        if Term.objects.filter(academic_year=academic_year, term_number=term_number).exclude(pk=term_id).exists():
            errors['term_number'] = [f'Term {term_number} already exists in {academic_year.name}.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        academic_year_id = request.POST.get('academic_year')
        term_number = request.POST.get('term_number')
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([academic_year_id, term_number, start_date, end_date]):
            errors = {}
            if not academic_year_id:
                errors['academic_year'] = ['Academic year is required.']
            if not term_number:
                errors['term_number'] = ['Term number is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        try:
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Academic year not found.',
                'errors': {'academic_year': ['The selected academic year does not exist.']}
            }, status=404)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_term_dates(
            academic_year, term_number, start_date, end_date
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'term_number' in validation_errors:
                message = validation_errors['term_number'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                term = Term(
                    academic_year=academic_year,
                    term_number=term_number,
                    name=name or f"Term {term_number}",
                    start_date=start_date,
                    end_date=end_date,
                    is_active=is_active
                )
                term.full_clean()
                term.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Term "{term.name}" created successfully.',
                    'term': {
                        'id': term.pk,
                        'term_number': term.term_number,
                        'name': term.name,
                        'start_date': term.start_date.strftime('%Y-%m-%d'),
                        'end_date': term.end_date.strftime('%Y-%m-%d'),
                        'is_active': term.is_active,
                        'academic_year': term.academic_year.name,
                        'academic_year_id': term.academic_year_id,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating term: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _update(self, request):
        term_id = request.POST.get('id')
        if not term_id:
            return JsonResponse({
                'success': False,
                'message': 'Term ID required',
                'errors': {'id': ['Term ID is required.']}
            }, status=400)
        
        try:
            term = get_object_or_404(Term, pk=term_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Term not found.',
                'errors': {'__all__': ['The requested term does not exist.']}
            }, status=404)
        
        term_number = request.POST.get('term_number')
        name = request.POST.get('name')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([term_number, start_date, end_date]):
            errors = {}
            if not term_number:
                errors['term_number'] = ['Term number is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation (pass term_id to exclude current term from overlap check)
        is_valid, validation_errors = self._validate_term_dates(
            term.academic_year, term_number, start_date, end_date, term_id
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'term_number' in validation_errors:
                message = validation_errors['term_number'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                term.term_number = term_number
                term.name = name or f"Term {term_number}"
                term.start_date = start_date
                term.end_date = end_date
                term.is_active = is_active
                
                term.full_clean()
                term.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Term "{term.name}" updated successfully.',
                    'term': {
                        'id': term.pk,
                        'term_number': term.term_number,
                        'name': term.name,
                        'start_date': term.start_date.strftime('%Y-%m-%d'),
                        'end_date': term.end_date.strftime('%Y-%m-%d'),
                        'is_active': term.is_active,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating term {term_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _delete(self, request):
        term_id = request.POST.get('id')
        if not term_id:
            return JsonResponse({
                'success': False,
                'message': 'Term ID required',
                'errors': {'id': ['Term ID is required.']}
            }, status=400)
        
        try:
            term = get_object_or_404(Term, pk=term_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Term not found.',
                'errors': {'__all__': ['The requested term does not exist.']}
            }, status=404)
        
        # Check dependencies
        if term.exam_sessions.exists():
            return JsonResponse({
                'success': False,
                'message': 'Cannot delete term that has exam sessions. Delete the exam sessions first.',
                'errors': {'__all__': ['Cannot delete term that has exam sessions.']}
            }, status=400)
        
        try:
            term_name = term.name
            term.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Term "{term_name}" deleted successfully.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting term {term_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {'__all__': ['An unexpected error occurred while deleting. Please try again.']}
            }, status=500)


class GetTermDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get term details for editing."""
    
    def get(self, request, pk):
        term = get_object_or_404(Term, pk=pk)
        
        return JsonResponse({
            'id': term.pk,
            'term_number': term.term_number,
            'name': term.name,
            'start_date': term.start_date.strftime('%Y-%m-%d'),
            'end_date': term.end_date.strftime('%Y-%m-%d'),
            'is_active': term.is_active,
            'academic_year': term.academic_year.name,
            'academic_year_id': term.academic_year_id,
            'exam_count': term.exam_sessions.count(),
        })


class SetActiveTermView(ManagementRequiredMixin, View):
    """Set a term as active within its academic year."""
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        term_id = request.POST.get('id')
        if not term_id:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Term ID required',
                    'errors': {'id': ['Term ID is required.']}
                }, status=400)
            messages.error(request, 'Term ID required.')
            return redirect('management:academic_year_list')
        
        term = get_object_or_404(Term, pk=term_id)
        
        try:
            with transaction.atomic():
                # Deactivate all other terms in the same academic year
                Term.objects.filter(academic_year=term.academic_year).exclude(pk=term.pk).update(is_active=False)
                # Activate selected term
                term.is_active = True
                term.save()
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': f'Term "{term.name}" is now active in {term.academic_year.name}.',
                        'term': {
                            'id': term.pk,
                            'name': term.name,
                            'is_active': True
                        }
                    })
                
                messages.success(request, f'Term "{term.name}" is now active in {term.academic_year.name}.')
                return redirect('management:academic_year_terms', pk=term.academic_year.pk)
                
        except Exception as e:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': str(e),
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            messages.error(request, f'Error setting active term: {e}')
            return redirect('management:academic_year_terms', pk=term.academic_year.pk)



# ============================================================================
# CLASS LEVEL CRUD VIEWS
# ============================================================================

class ClassLevelListView(ManagementRequiredMixin, TemplateView):
    """List all class levels with filtering by educational level."""
    template_name = 'portal_management/academic/class_levels.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        level_id = self.request.GET.get('level')
        final_filter = self.request.GET.get('final')
        
        # Base queryset
        class_levels = ClassLevel.objects.select_related(
            'educational_level'
        ).annotate(
            stream_count=Count('streams', distinct=True),
            student_count=Count('student_enrollments', distinct=True, 
                              filter=Q(student_enrollments__academic_year__is_active=True)),
            teacher_count=Count('teaching_assignments__staff', distinct=True)
        ).order_by('educational_level__level_type', 'order')
        
        # Apply filters
        if level_id:
            class_levels = class_levels.filter(educational_level_id=level_id)
        
        if final_filter == 'final':
            class_levels = class_levels.filter(is_final=True)
        elif final_filter == 'non_final':
            class_levels = class_levels.filter(is_final=False)
        
        ctx['class_levels'] = class_levels
        ctx['total_classes'] = class_levels.count()
        
        # Get filter options
        ctx['educational_levels'] = EducationalLevel.objects.all().order_by('level_type', 'name')
        
        # Statistics
        ctx['final_count'] = ClassLevel.objects.filter(is_final=True).count()
        ctx['streams_total'] = StreamClass.objects.count()
        ctx['levels_count'] = EducationalLevel.objects.count()
        
        # Store selected filters
        ctx['selected_level'] = int(level_id) if level_id else None
        ctx['selected_final'] = final_filter
        
        return ctx


class ClassLevelCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Class Levels.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_class_level(self, educational_level_id, name, code, order, is_final, class_level_id=None):
        """
        Comprehensive validation for class levels.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Validate educational level exists
        if not educational_level_id:
            errors['educational_level'] = ['Educational level is required.']
            return False, errors
        
        try:
            educational_level = EducationalLevel.objects.get(pk=educational_level_id)
        except EducationalLevel.DoesNotExist:
            errors['educational_level'] = ['Selected educational level does not exist.']
            return False, errors
        
        # Validate name
        if not name or len(name.strip()) < 1:
            errors['name'] = ['Class level name is required.']
        elif len(name) > 50:
            errors['name'] = ['Class level name cannot exceed 50 characters.']
        
        # Validate code
        if not code or len(code.strip()) < 1:
            errors['code'] = ['Class level code is required.']
        elif len(code) > 20:
            errors['code'] = ['Class level code cannot exceed 20 characters.']
        elif not re.match(r'^[A-Z0-9]+$', code):
            errors['code'] = ['Class level code must contain only uppercase letters and numbers (e.g., F1, STD3).']
        
        # Check for duplicate code within the same educational level
        existing_code = ClassLevel.objects.filter(
            educational_level_id=educational_level_id,
            code=code
        ).exclude(pk=class_level_id)
        
        if existing_code.exists():
            errors['code'] = [f'Class level code "{code}" already exists in {educational_level.name}.']
        
        # Check for duplicate name within the same educational level (optional but good practice)
        existing_name = ClassLevel.objects.filter(
            educational_level_id=educational_level_id,
            name__iexact=name
        ).exclude(pk=class_level_id)
        
        if existing_name.exists():
            errors['name'] = errors.get('name', []) + [f'Class level name "{name}" already exists in {educational_level.name}.']
        
        # Validate order
        try:
            order_val = int(order)
            if order_val < 1:
                errors['order'] = ['Order must be a positive number.']
        except (ValueError, TypeError):
            errors['order'] = ['Order must be a valid number.']
        
        # Check for duplicate order within the same educational level
        if order and not errors.get('order'):
            existing_order = ClassLevel.objects.filter(
                educational_level_id=educational_level_id,
                order=order
            ).exclude(pk=class_level_id)
            
            if existing_order.exists():
                existing = existing_order.first()
                errors['order'] = [f'Order number {order} is already used by "{existing.name}". Please use a different order.']
        
        # Validate is_final - only one final class level per educational level
        if is_final and not errors.get('educational_level'):
            existing_final = ClassLevel.objects.filter(
                educational_level_id=educational_level_id,
                is_final=True
            ).exclude(pk=class_level_id)
            
            if existing_final.exists():
                existing = existing_final.first()
                errors['is_final'] = [f'"{educational_level.name}" already has a final class level: "{existing.name}". Only one class level can be marked as final.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        educational_level_id = request.POST.get('educational_level')
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        order = request.POST.get('order')
        is_final = request.POST.get('is_final') == 'true'
        
        # Validate required fields
        if not all([educational_level_id, name, code, order]):
            errors = {}
            if not educational_level_id:
                errors['educational_level'] = ['Educational level is required.']
            if not name:
                errors['name'] = ['Class level name is required.']
            if not code:
                errors['code'] = ['Class level code is required.']
            if not order:
                errors['order'] = ['Order is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_class_level(
            educational_level_id, name, code, order, is_final
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'educational_level' in validation_errors:
                message = validation_errors['educational_level'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            elif 'order' in validation_errors:
                message = validation_errors['order'][0]
            elif 'is_final' in validation_errors:
                message = validation_errors['is_final'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            educational_level = get_object_or_404(EducationalLevel, pk=educational_level_id)
            
            with transaction.atomic():
                class_level = ClassLevel(
                    educational_level=educational_level,
                    name=name,
                    code=code,
                    order=order,
                    is_final=is_final
                )
                class_level.full_clean()
                class_level.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Class level "{class_level.name}" created successfully.',
                    'class_level': {
                        'id': class_level.pk,
                        'name': class_level.name,
                        'code': class_level.code,
                        'order': class_level.order,
                        'is_final': class_level.is_final,
                        'educational_level': class_level.educational_level.name,
                        'educational_level_id': class_level.educational_level_id,
                        'educational_level_type': class_level.educational_level.level_type,
                        'stream_count': 0,
                        'student_count': 0,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating class level: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _update(self, request):
        class_level_id = request.POST.get('id')
        if not class_level_id:
            return JsonResponse({
                'success': False,
                'message': 'Class Level ID required',
                'errors': {'id': ['Class Level ID is required.']}
            }, status=400)
        
        try:
            class_level = get_object_or_404(ClassLevel, pk=class_level_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Class level not found.',
                'errors': {'__all__': ['The requested class level does not exist.']}
            }, status=404)
        
        educational_level_id = request.POST.get('educational_level')
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        order = request.POST.get('order')
        is_final = request.POST.get('is_final') == 'true'
        
        # Validate required fields
        if not all([educational_level_id, name, code, order]):
            errors = {}
            if not educational_level_id:
                errors['educational_level'] = ['Educational level is required.']
            if not name:
                errors['name'] = ['Class level name is required.']
            if not code:
                errors['code'] = ['Class level code is required.']
            if not order:
                errors['order'] = ['Order is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_class_level(
            educational_level_id, name, code, order, is_final, class_level_id
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'educational_level' in validation_errors:
                message = validation_errors['educational_level'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            elif 'order' in validation_errors:
                message = validation_errors['order'][0]
            elif 'is_final' in validation_errors:
                message = validation_errors['is_final'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            educational_level = get_object_or_404(EducationalLevel, pk=educational_level_id)
            
            with transaction.atomic():
                class_level.educational_level = educational_level
                class_level.name = name
                class_level.code = code
                class_level.order = order
                class_level.is_final = is_final
                
                class_level.full_clean()
                class_level.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Class level "{class_level.name}" updated successfully.',
                    'class_level': {
                        'id': class_level.pk,
                        'name': class_level.name,
                        'code': class_level.code,
                        'order': class_level.order,
                        'is_final': class_level.is_final,
                        'educational_level': class_level.educational_level.name,
                        'educational_level_id': class_level.educational_level_id,
                        'educational_level_type': class_level.educational_level.level_type,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating class level {class_level_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _delete(self, request):
        class_level_id = request.POST.get('id')
        if not class_level_id:
            return JsonResponse({
                'success': False,
                'message': 'Class Level ID required',
                'errors': {'id': ['Class Level ID is required.']}
            }, status=400)
        
        try:
            class_level = get_object_or_404(ClassLevel, pk=class_level_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Class level not found.',
                'errors': {'__all__': ['The requested class level does not exist.']}
            }, status=404)
        
        # Check dependencies
        dependency_errors = {}
        
        if class_level.streams.exists():
            dependency_errors['__all__'] = [
                'Cannot delete class level that has streams. Please delete all streams first.'
            ]
        
        if class_level.student_enrollments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete class level that has student enrollments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete class level that has student enrollments.'
                ]
        
        if class_level.teaching_assignments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete class level that has teaching assignments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete class level that has teaching assignments.'
                ]
        
        if class_level.class_teacher_assignments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete class level that has class teacher assignments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete class level that has class teacher assignments.'
                ]
        
        if dependency_errors:
            return JsonResponse({
                'success': False,
                'message': dependency_errors['__all__'][0],
                'errors': dependency_errors
            }, status=400)
        
        try:
            class_level_name = class_level.name
            class_level.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Class level "{class_level_name}" deleted successfully.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting class level {class_level_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {'__all__': ['An unexpected error occurred while deleting. Please try again.']}
            }, status=500)


class GetClassLevelDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get class level details for editing."""
    
    def get(self, request, pk):
        class_level = get_object_or_404(ClassLevel, pk=pk)
        
        return JsonResponse({
            'id': class_level.pk,
            'name': class_level.name,
            'code': class_level.code,
            'order': class_level.order,
            'is_final': class_level.is_final,
            'educational_level_id': class_level.educational_level_id,
            'educational_level': class_level.educational_level.name,
            'stream_count': class_level.streams.count(),
            'student_count': class_level.student_enrollments.count(),
        })



# ============================================================================
# STREAM CLASS CRUD VIEWS
# ============================================================================



class ClassStreamsView(ManagementRequiredMixin, TemplateView):
    """View all streams for a specific class level."""
    template_name = 'portal_management/academic/class_streams.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        class_level = get_object_or_404(ClassLevel, pk=self.kwargs['pk'])
        ctx['class_level'] = class_level
        
        # Get all streams for this class level with custom annotations
        streams = StreamClass.objects.filter(
            class_level=class_level
        ).annotate(
            # Use a different name to avoid conflict with the property
            active_students=Count(
                'stream_assignments',
                distinct=True,
                filter=Q(stream_assignments__enrollment__academic_year__is_active=True)
            ),
            teachers_count=Count(
                'teaching_assignments__staff',
                distinct=True
            )
        ).order_by('stream_letter')
        
        # Map the annotated fields to the template variables
        for stream in streams:
            stream.active_student_count = stream.active_students
            stream.teacher_count = stream.teachers_count
        
        ctx['streams'] = streams
        ctx['total_streams'] = streams.count()
        ctx['total_capacity'] = streams.aggregate(total=models.Sum('capacity'))['total'] or 0
        ctx['total_students'] = streams.aggregate(total=models.Sum('active_students'))['total'] or 0
        
        return ctx

class StreamClassCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Stream Classes.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_stream_sequence(self, class_level_id, stream_letter, stream_id=None):
        """
        Validate that stream letters are sequential (A, B, C, ...) without gaps.
        Returns (is_valid, error_message)
        """
        # Get all existing streams for this class level, ordered by stream_letter
        existing_streams = StreamClass.objects.filter(
            class_level_id=class_level_id
        ).exclude(pk=stream_id).order_by('stream_letter')
        
        if not existing_streams.exists():
            # First stream - always valid
            return True, None
        
        # Convert letters to their ASCII values for comparison
        existing_letters = [s.stream_letter for s in existing_streams]
        new_letter = stream_letter.upper()
        
        # Case 1: Adding at the beginning
        if new_letter < existing_letters[0]:
            # Should be 'A' if no streams exist, or the next logical letter
            expected_first = 'A'
            if existing_letters[0] != 'A':
                # If first existing letter is not 'A', then new letter must be 'A'
                if new_letter != 'A':
                    return False, f'Stream letters must start from A. The first stream should be A, but you are trying to add {new_letter}.'
            return True, None
        
        # Case 2: Adding at the end
        if new_letter > existing_letters[-1]:
            # Should be the next letter in sequence
            expected_next = chr(ord(existing_letters[-1]) + 1)
            if new_letter != expected_next:
                return False, f'Stream letters must be sequential. After {existing_letters[-1]}, the next stream should be {expected_next}, not {new_letter}.'
            return True, None
        
        # Case 3: Adding in the middle - check if there's a gap
        for i in range(len(existing_letters) - 1):
            if existing_letters[i] < new_letter < existing_letters[i + 1]:
                # Check if this position is the correct next letter
                expected_letter = chr(ord(existing_letters[i]) + 1)
                if new_letter != expected_letter:
                    return False, f'Stream letters must be sequential. After {existing_letters[i]}, the next stream should be {expected_letter}, not {new_letter}.'
                return True, None
            
            # Check if the letter already exists (caught by unique_together validation)
            if new_letter == existing_letters[i]:
                return False, f'Stream letter {new_letter} already exists.'
        
        return True, None
    
    def _validate_stream(self, class_level_id, stream_letter, name, capacity, stream_id=None):
        """
        Comprehensive validation for stream classes.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        import re
        
        # Validate class level exists
        if not class_level_id:
            errors['class_level'] = ['Class level is required.']
            return False, errors
        
        try:
            class_level = ClassLevel.objects.get(pk=class_level_id)
        except ClassLevel.DoesNotExist:
            errors['class_level'] = ['Selected class level does not exist.']
            return False, errors
        
        # Validate stream letter
        if not stream_letter or len(stream_letter.strip()) < 1:
            errors['stream_letter'] = ['Stream letter is required.']
        elif len(stream_letter) > 1:
            errors['stream_letter'] = ['Stream letter must be a single character.']
        elif not re.match(r'^[A-Z]$', stream_letter.upper()):
            errors['stream_letter'] = ['Stream letter must be a single uppercase letter (A-Z).']
        
        # Check for duplicate stream letter within the same class level
        if stream_letter and not errors.get('stream_letter'):
            existing_letter = StreamClass.objects.filter(
                class_level_id=class_level_id,
                stream_letter__iexact=stream_letter
            ).exclude(pk=stream_id)
            
            if existing_letter.exists():
                existing = existing_letter.first()
                errors['stream_letter'] = [f'Stream letter "{stream_letter.upper()}" already exists in {class_level.name}. This class already has stream {existing.name}.']
        
        # Validate stream sequence (only if letter is valid and not duplicate)
        if stream_letter and not errors.get('stream_letter'):
            is_sequence_valid, sequence_error = self._validate_stream_sequence(
                class_level_id, stream_letter, stream_id
            )
            if not is_sequence_valid:
                errors['stream_letter'] = [sequence_error]
        
        # Validate name (optional)
        if name and len(name) > 10:
            errors['name'] = ['Stream name cannot exceed 10 characters.']
        
        # Validate capacity
        try:
            capacity_val = int(capacity) if capacity else 50
            if capacity_val < 1:
                errors['capacity'] = ['Capacity must be at least 1.']
            elif capacity_val > 200:
                errors['capacity'] = ['Capacity cannot exceed 200.']
        except (ValueError, TypeError):
            errors['capacity'] = ['Capacity must be a valid number.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        class_level_id = request.POST.get('class_level')
        stream_letter = request.POST.get('stream_letter', '').strip().upper()
        name = request.POST.get('name', '').strip()
        capacity = request.POST.get('capacity', '50')
        
        # Validate required fields
        if not all([class_level_id, stream_letter]):
            errors = {}
            if not class_level_id:
                errors['class_level'] = ['Class level is required.']
            if not stream_letter:
                errors['stream_letter'] = ['Stream letter is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_stream(
            class_level_id, stream_letter, name, capacity
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'class_level' in validation_errors:
                message = validation_errors['class_level'][0]
            elif 'stream_letter' in validation_errors:
                message = validation_errors['stream_letter'][0]
            elif 'capacity' in validation_errors:
                message = validation_errors['capacity'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            class_level = get_object_or_404(ClassLevel, pk=class_level_id)
            
            with transaction.atomic():
                stream = StreamClass(
                    class_level=class_level,
                    stream_letter=stream_letter,
                    name=name or f"{class_level.name}{stream_letter}",
                    capacity=capacity
                )
                stream.full_clean()
                stream.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Stream "{stream.name}" created successfully.',
                    'stream': {
                        'id': stream.pk,
                        'name': stream.name,
                        'stream_letter': stream.stream_letter,
                        'capacity': stream.capacity,
                        'class_level': stream.class_level.name,
                        'class_level_id': stream.class_level_id,
                        'student_count': 0,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating stream: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _update(self, request):
        stream_id = request.POST.get('id')
        if not stream_id:
            return JsonResponse({
                'success': False,
                'message': 'Stream ID required',
                'errors': {'id': ['Stream ID is required.']}
            }, status=400)
        
        try:
            stream = get_object_or_404(StreamClass, pk=stream_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Stream not found.',
                'errors': {'__all__': ['The requested stream does not exist.']}
            }, status=404)
        
        stream_letter = request.POST.get('stream_letter', '').strip().upper()
        name = request.POST.get('name', '').strip()
        capacity = request.POST.get('capacity', '50')
        
        # Validate required fields
        if not stream_letter:
            errors = {'stream_letter': ['Stream letter is required.']}
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_stream(
            stream.class_level_id, stream_letter, name, capacity, stream_id
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'stream_letter' in validation_errors:
                message = validation_errors['stream_letter'][0]
            elif 'capacity' in validation_errors:
                message = validation_errors['capacity'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                old_letter = stream.stream_letter
                stream.stream_letter = stream_letter
                stream.name = name or f"{stream.class_level.name}{stream_letter}"
                stream.capacity = capacity
                
                stream.full_clean()
                stream.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Stream "{stream.name}" updated successfully.',
                    'stream': {
                        'id': stream.pk,
                        'name': stream.name,
                        'stream_letter': stream.stream_letter,
                        'capacity': stream.capacity,
                        'student_count': stream.student_count,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating stream {stream_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _delete(self, request):
        stream_id = request.POST.get('id')
        if not stream_id:
            return JsonResponse({
                'success': False,
                'message': 'Stream ID required',
                'errors': {'id': ['Stream ID is required.']}
            }, status=400)
        
        try:
            stream = get_object_or_404(StreamClass, pk=stream_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Stream not found.',
                'errors': {'__all__': ['The requested stream does not exist.']}
            }, status=404)
        
        # Check dependencies
        dependency_errors = {}
        
        if stream.stream_assignments.exists():
            dependency_errors['__all__'] = [
                'Cannot delete stream that has student assignments. Please reassign students first.'
            ]
        
        if stream.teaching_assignments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete stream that has teaching assignments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete stream that has teaching assignments.'
                ]
        
        if stream.class_teacher_assignments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete stream that has class teacher assignments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete stream that has class teacher assignments.'
                ]
        
        if dependency_errors:
            return JsonResponse({
                'success': False,
                'message': dependency_errors['__all__'][0],
                'errors': dependency_errors
            }, status=400)
        
        try:
            stream_name = stream.name
            stream.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Stream "{stream_name}" deleted successfully.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting stream {stream_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {'__all__': ['An unexpected error occurred while deleting. Please try again.']}
            }, status=500)


class GetStreamDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get stream details for editing."""
    
    def get(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        
        return JsonResponse({
            'id': stream.pk,
            'name': stream.name,
            'stream_letter': stream.stream_letter,
            'capacity': stream.capacity,
            'class_level_id': stream.class_level_id,
            'class_level': stream.class_level.name,
            'student_count': stream.student_count,
            'available_spots': stream.capacity - stream.student_count,
        })
    

# ============================================================================
# STREAM STUDENTS VIEWS
# ============================================================================

class StreamStudentsView(ManagementRequiredMixin, TemplateView):
    """View all students in a specific stream with management capabilities."""
    template_name = 'portal_management/academic/stream_students.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        stream = get_object_or_404(StreamClass, pk=self.kwargs['pk'])
        ctx['stream'] = stream
        ctx['class_level'] = stream.class_level
        
        # Get current academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        ctx['current_academic_year'] = current_academic_year
        
        # Get all students currently in this stream
        # The correct path: enrollments__stream_assignment__stream_class
        students = Student.objects.filter(
            enrollments__stream_assignment__stream_class=stream,
            enrollments__academic_year__is_active=True,
            status='active'
        ).select_related(
            'user'
        ).prefetch_related(
            'enrollments__class_level',
            'enrollments__academic_year',
            'enrollments__stream_assignment__stream_class',
            'subject_assignments__subject'
        ).distinct().order_by('first_name', 'last_name')
        
        # Annotate with additional info
        for student in students:
            # Get current enrollment
            enrollment = student.enrollments.filter(
                academic_year__is_active=True
            ).first()
            if enrollment:
                student.current_class = enrollment.class_level.name
                student.academic_year = enrollment.academic_year.name
                student.combination = enrollment.combination.code if enrollment.combination else None
                
                # Get optional subjects
                student.optional_subjects = student.subject_assignments.filter(
                    enrollment=enrollment
                ).select_related('subject')
        
        ctx['students'] = students
        ctx['student_count'] = students.count()
        
        # Calculate capacity usage
        ctx['capacity_used'] = students.count()
        ctx['capacity_available'] = max(0, stream.capacity - students.count())
        ctx['capacity_percentage'] = (students.count() / stream.capacity * 100) if stream.capacity > 0 else 0
        
        # Get available students for bulk assign (students in same class level but not in this stream)
        if stream.class_level:
            available_students = Student.objects.filter(
                enrollments__class_level=stream.class_level,
                enrollments__academic_year__is_active=True,
                status='active'
            ).exclude(
                enrollments__stream_assignment__stream_class=stream,
                enrollments__academic_year__is_active=True
            ).distinct().select_related(
                'user'
            ).prefetch_related(
                'enrollments__class_level'
            ).order_by('first_name', 'last_name')
            
            ctx['available_students'] = available_students
            ctx['available_count'] = available_students.count()
        
        return ctx
    

class StreamBulkAssignStudentsView(ManagementRequiredMixin, View):
    """Bulk assign students to a stream."""
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get parameters
        student_ids = request.POST.getlist('student_ids')
        select_all = request.POST.get('select_all') == 'true'
        
        if not student_ids and not select_all:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No students selected.',
                    'errors': {'student_ids': ['Please select at least one student.']}
                }, status=400)
            messages.error(request, 'No students selected.')
            return redirect('management:stream_students', pk=pk)
        
        # Check if there's enough capacity
        current_count = StudentStreamAssignment.objects.filter(
            stream_class=stream,
            enrollment__academic_year__is_active=True
        ).count()
        
        try:
            with transaction.atomic():
                # Get eligible students
                if select_all:
                    # Get all eligible students not already in this stream
                    students_qs = Student.objects.filter(
                        enrollments__class_level=stream.class_level,
                        enrollments__academic_year__is_active=True,
                        status='active'
                    ).exclude(
                        stream_assignments__stream_class=stream,
                        stream_assignments__enrollment__academic_year__is_active=True
                    ).distinct()
                    students = list(students_qs)
                else:
                    students = Student.objects.filter(pk__in=student_ids)
                
                if not students:
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': 'No eligible students found.'
                        }, status=400)
                    messages.warning(request, 'No eligible students found.')
                    return redirect('management:stream_students', pk=pk)
                
                # Check capacity
                if current_count + len(students) > stream.capacity:
                    available = stream.capacity - current_count
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': f'Cannot assign {len(students)} students. Only {available} spot(s) available in this stream.',
                            'errors': {'capacity': [f'Stream capacity exceeded. Available spots: {available}']}
                        }, status=400)
                    messages.error(request, f'Cannot assign {len(students)} students. Only {available} spot(s) available.')
                    return redirect('management:stream_students', pk=pk)
                
                # Create assignments
                created_count = 0
                errors = []
                
                for student in students:
                    try:
                        # Get active enrollment for this student
                        enrollment = StudentEnrollment.objects.filter(
                            student=student,
                            academic_year__is_active=True,
                            class_level=stream.class_level
                        ).first()
                        
                        if not enrollment:
                            errors.append(f"{student.full_name}: No active enrollment found in {stream.class_level.name}")
                            continue
                        
                        # Check if already has a stream assignment
                        existing = StudentStreamAssignment.objects.filter(
                            enrollment=enrollment
                        ).first()
                        
                        if existing:
                            if existing.stream_class == stream:
                                errors.append(f"{student.full_name}: Already assigned to this stream")
                            else:
                                # Update existing assignment to this stream
                                existing.stream_class = stream
                                existing.assigned_date = timezone.now().date()
                                existing.save()
                                created_count += 1
                        else:
                            # Create new assignment
                            StudentStreamAssignment.objects.create(
                                enrollment=enrollment,
                                stream_class=stream,
                                assigned_date=timezone.now().date()
                            )
                            created_count += 1
                            
                    except Exception as e:
                        errors.append(f"{student.full_name}: {str(e)}")
                
                message = f"Successfully assigned {created_count} student(s) to {stream.name}."
                if errors:
                    message += f" {len(errors)} error(s) occurred."
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'created_count': created_count,
                        'error_count': len(errors),
                        'errors': errors[:5]  # Return first 5 errors
                    })
                
                if created_count > 0:
                    messages.success(request, message)
                if errors:
                    messages.warning(request, f"{len(errors)} errors occurred. Check logs for details.")
                
                return redirect('management:stream_students', pk=pk)
                
        except Exception as e:
            logger.error(f"Bulk assign error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error during bulk assignment: {e}')
            return redirect('management:stream_students', pk=pk)


class StreamRemoveStudentView(ManagementRequiredMixin, View):
    """Remove a single student from a stream."""
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        student_id = request.POST.get('student_id')
        if not student_id:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Student ID required.',
                    'errors': {'student_id': ['Student ID is required.']}
                }, status=400)
            messages.error(request, 'Student ID required.')
            return redirect('management:stream_students', pk=pk)
        
        try:
            assignment = StudentStreamAssignment.objects.get(
                stream_class=stream,
                enrollment__student_id=student_id,
                enrollment__academic_year__is_active=True
            )
            
            student_name = assignment.enrollment.student.full_name
            assignment.delete()
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f'{student_name} removed from {stream.name} successfully.'
                })
            
            messages.success(request, f'{student_name} removed from {stream.name}.')
            return redirect('management:stream_students', pk=pk)
            
        except StudentStreamAssignment.DoesNotExist:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Student not found in this stream.',
                    'errors': {'student_id': ['Student not found in this stream.']}
                }, status=404)
            messages.error(request, 'Student not found in this stream.')
            return redirect('management:stream_students', pk=pk)
        except Exception as e:
            logger.error(f"Remove student error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error removing student: {e}')
            return redirect('management:stream_students', pk=pk)


class StreamBulkRemoveStudentsView(ManagementRequiredMixin, View):
    """Bulk remove students from a stream."""
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        student_ids = request.POST.getlist('student_ids')
        select_all = request.POST.get('select_all') == 'true'
        
        if not student_ids and not select_all:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No students selected.',
                    'errors': {'student_ids': ['Please select at least one student.']}
                }, status=400)
            messages.error(request, 'No students selected.')
            return redirect('management:stream_students', pk=pk)
        
        try:
            with transaction.atomic():
                # Get assignments to remove
                assignments_qs = StudentStreamAssignment.objects.filter(
                    stream_class=stream,
                    enrollment__academic_year__is_active=True
                )
                
                if select_all:
                    assignments = list(assignments_qs)
                else:
                    assignments_qs = assignments_qs.filter(enrollment__student_id__in=student_ids)
                    assignments = list(assignments_qs)
                
                if not assignments:
                    if is_ajax:
                        return JsonResponse({
                            'success': False,
                            'message': 'No matching students found to remove.'
                        }, status=400)
                    messages.warning(request, 'No matching students found to remove.')
                    return redirect('management:stream_students', pk=pk)
                
                # Delete assignments
                count = len(assignments)
                student_names = [a.enrollment.student.full_name for a in assignments]
                assignments_qs.delete()
                
                message = f"Successfully removed {count} student(s) from {stream.name}."
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'removed_count': count,
                        'students': student_names[:10]  # Return first 10 names
                    })
                
                messages.success(request, message)
                return redirect('management:stream_students', pk=pk)
                
        except Exception as e:
            logger.error(f"Bulk remove error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error during bulk removal: {e}')
            return redirect('management:stream_students', pk=pk)


class GetAvailableStudentsForStreamView(ManagementRequiredMixin, View):
    """AJAX endpoint to get available students for stream assignment."""
    
    def get(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        
        search = request.GET.get('search', '')
        
        # Get students in the same class level but not in this stream
        students = Student.objects.filter(
            enrollments__class_level=stream.class_level,
            enrollments__academic_year__is_active=True,
            status='active'
        ).exclude(
            stream_assignments__stream_class=stream,
            stream_assignments__enrollment__academic_year__is_active=True
        ).distinct().select_related(
            'user'
        ).prefetch_related(
            'enrollments__class_level'
        )
        
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(registration_number__icontains=search)
            )
        
        # Limit results for performance
        students = students.order_by('first_name', 'last_name')[:50]
        
        data = [{
            'id': s.pk,
            'full_name': s.full_name,
            'registration_number': s.registration_number,
            'current_stream': None,  # They don't have a stream in this class level
        } for s in students]
        
        return JsonResponse({'students': data})

class StreamClassCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = StreamClassForm(request.POST)
        if form.is_valid():
            stream = form.save()
            messages.success(
                request,
                f'Stream "{stream}" created under {stream.class_level}.'
            )
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:class_level_list')


# ============================================================================
# SUBJECT CRUD VIEWS
# ============================================================================

class SubjectListView(ManagementRequiredMixin, TemplateView):
    """List all subjects with filtering by educational level."""
    template_name = 'portal_management/academic/subjects.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        level_id = self.request.GET.get('level')
        compulsory_filter = self.request.GET.get('compulsory')
        
        # Base queryset
        subjects = Subject.objects.select_related(
            'educational_level'
        ).annotate(
            student_count=Count(
                'student_assignments__student',
                distinct=True,
                filter=Q(student_assignments__enrollment__academic_year__is_active=True)
            ),
            combination_count=Count(
                'combination_subjects__combination',
                distinct=True
            )
        ).order_by('educational_level__level_type', 'name')
        
        # Apply filters
        if level_id:
            subjects = subjects.filter(educational_level_id=level_id)
        
        if compulsory_filter == 'compulsory':
            subjects = subjects.filter(is_compulsory=True)
        elif compulsory_filter == 'optional':
            subjects = subjects.filter(is_compulsory=False)
        
        # Add display counts
        for subject in subjects:
            if subject.is_compulsory:
                subject.display_student_count = "-"  # All students
            else:
                subject.display_student_count = subject.student_count or 0
        
        ctx['subjects'] = subjects
        ctx['total_subjects'] = subjects.count()
        
        # Get filter options
        ctx['educational_levels'] = EducationalLevel.objects.all().order_by('level_type', 'name')
        
        # Statistics
        ctx['compulsory_count'] = Subject.objects.filter(is_compulsory=True).count()
        ctx['optional_count'] = Subject.objects.filter(is_compulsory=False).count()
        ctx['levels_count'] = EducationalLevel.objects.count()
        
        # Store selected filters
        ctx['selected_level'] = int(level_id) if level_id else None
        ctx['selected_compulsory'] = compulsory_filter
        
        return ctx


class SubjectCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Subjects.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_subject(self, educational_level_id, name, code, short_name, subject_id=None):
        """
        Comprehensive validation for subjects.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Validate educational level exists
        if not educational_level_id:
            errors['educational_level'] = ['Educational level is required.']
            return False, errors
        
        try:
            educational_level = EducationalLevel.objects.get(pk=educational_level_id)
        except EducationalLevel.DoesNotExist:
            errors['educational_level'] = ['Selected educational level does not exist.']
            return False, errors
        
        # Validate name
        if not name or len(name.strip()) < 2:
            errors['name'] = ['Subject name must be at least 2 characters long.']
        elif len(name) > 100:
            errors['name'] = ['Subject name cannot exceed 100 characters.']
        
        # Validate code
        if not code or len(code.strip()) < 1:
            errors['code'] = ['Subject code is required.']
        elif len(code) > 20:
            errors['code'] = ['Subject code cannot exceed 20 characters.']
        elif not re.match(r'^[A-Z0-9]+$', code):
            errors['code'] = ['Subject code must contain only uppercase letters and numbers (e.g., MATH, ENG, BIO101).']
        
        # Check for duplicate code within the same educational level
        existing_code = Subject.objects.filter(
            educational_level_id=educational_level_id,
            code=code
        ).exclude(pk=subject_id)
        
        if existing_code.exists():
            errors['code'] = [f'Subject code "{code}" already exists in {educational_level.name}.']
        
        # Check for duplicate name within the same educational level (optional but good practice)
        existing_name = Subject.objects.filter(
            educational_level_id=educational_level_id,
            name__iexact=name
        ).exclude(pk=subject_id)
        
        if existing_name.exists():
            errors['name'] = errors.get('name', []) + [f'Subject name "{name}" already exists in {educational_level.name}.']
        
        # Validate short_name if provided
        if short_name and len(short_name) > 20:
            errors['short_name'] = ['Short name cannot exceed 20 characters.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        educational_level_id = request.POST.get('educational_level')
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        short_name = request.POST.get('short_name', '').strip()
        is_compulsory = request.POST.get('is_compulsory') == 'true'
        description = request.POST.get('description', '').strip()
        
        # Validate required fields
        if not all([educational_level_id, name, code]):
            errors = {}
            if not educational_level_id:
                errors['educational_level'] = ['Educational level is required.']
            if not name:
                errors['name'] = ['Subject name is required.']
            if not code:
                errors['code'] = ['Subject code is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_subject(
            educational_level_id, name, code, short_name
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'educational_level' in validation_errors:
                message = validation_errors['educational_level'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            educational_level = get_object_or_404(EducationalLevel, pk=educational_level_id)
            
            with transaction.atomic():
                subject = Subject(
                    educational_level=educational_level,
                    name=name,
                    code=code,
                    short_name=short_name or name[:20],
                    is_compulsory=is_compulsory,
                    description=description
                )
                subject.full_clean()
                subject.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{subject.name}" created successfully.',
                    'subject': {
                        'id': subject.pk,
                        'name': subject.name,
                        'code': subject.code,
                        'short_name': subject.short_name,
                        'is_compulsory': subject.is_compulsory,
                        'description': subject.description,
                        'educational_level': subject.educational_level.name,
                        'educational_level_id': subject.educational_level_id,
                        'educational_level_type': subject.educational_level.level_type,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating subject: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _update(self, request):
        subject_id = request.POST.get('id')
        if not subject_id:
            return JsonResponse({
                'success': False,
                'message': 'Subject ID required',
                'errors': {'id': ['Subject ID is required.']}
            }, status=400)
        
        try:
            subject = get_object_or_404(Subject, pk=subject_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Subject not found.',
                'errors': {'__all__': ['The requested subject does not exist.']}
            }, status=404)
        
        educational_level_id = request.POST.get('educational_level')
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        short_name = request.POST.get('short_name', '').strip()
        is_compulsory = request.POST.get('is_compulsory') == 'true'
        description = request.POST.get('description', '').strip()
        
        # Validate required fields
        if not all([educational_level_id, name, code]):
            errors = {}
            if not educational_level_id:
                errors['educational_level'] = ['Educational level is required.']
            if not name:
                errors['name'] = ['Subject name is required.']
            if not code:
                errors['code'] = ['Subject code is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_subject(
            educational_level_id, name, code, short_name, subject_id
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'educational_level' in validation_errors:
                message = validation_errors['educational_level'][0]
            elif 'name' in validation_errors:
                message = validation_errors['name'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            educational_level = get_object_or_404(EducationalLevel, pk=educational_level_id)
            
            with transaction.atomic():
                subject.educational_level = educational_level
                subject.name = name
                subject.code = code
                subject.short_name = short_name or name[:20]
                subject.is_compulsory = is_compulsory
                subject.description = description
                
                subject.full_clean()
                subject.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{subject.name}" updated successfully.',
                    'subject': {
                        'id': subject.pk,
                        'name': subject.name,
                        'code': subject.code,
                        'short_name': subject.short_name,
                        'is_compulsory': subject.is_compulsory,
                        'description': subject.description,
                        'educational_level': subject.educational_level.name,
                        'educational_level_id': subject.educational_level_id,
                        'educational_level_type': subject.educational_level.level_type,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating subject {subject_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _delete(self, request):
        subject_id = request.POST.get('id')
        if not subject_id:
            return JsonResponse({
                'success': False,
                'message': 'Subject ID required',
                'errors': {'id': ['Subject ID is required.']}
            }, status=400)
        
        try:
            subject = get_object_or_404(Subject, pk=subject_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Subject not found.',
                'errors': {'__all__': ['The requested subject does not exist.']}
            }, status=404)
        
        # Check dependencies
        dependency_errors = {}
        
        if subject.student_assignments.exists():
            dependency_errors['__all__'] = [
                'Cannot delete subject that has student assignments. Please remove all student assignments first.'
            ]
        
        if subject.combination_subjects.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete subject that is part of combinations. Remove from combinations first.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete subject that is part of combinations. Remove from combinations first.'
                ]
        
        if subject.teaching_assignments.exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete subject that has teaching assignments. Remove teaching assignments first.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete subject that has teaching assignments. Remove teaching assignments first.'
                ]
        
        if dependency_errors:
            return JsonResponse({
                'success': False,
                'message': dependency_errors['__all__'][0],
                'errors': dependency_errors
            }, status=400)
        
        try:
            subject_name = subject.name
            subject.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Subject "{subject_name}" deleted successfully.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting subject {subject_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {'__all__': ['An unexpected error occurred while deleting. Please try again.']}
            }, status=500)


class GetSubjectDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get subject details for editing."""
    
    def get(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        
        return JsonResponse({
            'id': subject.pk,
            'name': subject.name,
            'code': subject.code,
            'short_name': subject.short_name,
            'is_compulsory': subject.is_compulsory,
            'description': subject.description,
            'educational_level_id': subject.educational_level_id,
            'educational_level': subject.educational_level.name,
            'student_count': subject.student_assignments.count(),
            'combination_count': subject.combination_subjects.count(),
        })


# ============================================================================
# COMBINATION CRUD VIEWS
# ============================================================================

class CombinationListView(ManagementRequiredMixin, TemplateView):
    """List all A-Level subject combinations."""
    template_name = 'portal_management/academic/combinations.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Base queryset - combinations are always A-Level
        combinations = Combination.objects.select_related(
            'educational_level'
        ).annotate(
            subject_count=Count('combination_subjects', distinct=True),
            # Count students through StudentCombinationAssignment (active assignments)
            student_count=Count(
                'student_assignments',
                distinct=True,
                filter=Q(
                    student_assignments__is_active=True,
                    student_assignments__enrollment__academic_year__is_active=True
                )
            ),
            core_count=Count('combination_subjects', distinct=True,
                           filter=Q(combination_subjects__role='CORE')),
            subsidiary_count=Count('combination_subjects', distinct=True,
                                 filter=Q(combination_subjects__role='SUBSIDIARY'))
        ).order_by('code')
        
        ctx['combinations'] = combinations
        ctx['total_combinations'] = combinations.count()
        
        # Statistics
        ctx['total_subjects_in_combinations'] = CombinationSubject.objects.values('subject').distinct().count()
        ctx['total_students_in_combinations'] = StudentCombinationAssignment.objects.filter(
            is_active=True,
            enrollment__academic_year__is_active=True
        ).count()
        
        return ctx


class CombinationCRUDView(ManagementRequiredMixin, View):
    """
    Unified view for AJAX CRUD operations on Combinations.
    Accepts 'action' parameter: create, update, delete
    """
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'create':
            return self._create(request)
        elif action == 'update':
            return self._update(request)
        elif action == 'delete':
            return self._delete(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors
    
    def _validate_combination(self, code, combination_id=None):
        """
        Comprehensive validation for combinations.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        import re
        
        # Validate code
        if not code or len(code.strip()) < 1:
            errors['code'] = ['Combination code is required.']
        elif len(code) > 10:
            errors['code'] = ['Combination code cannot exceed 10 characters.']
        elif not re.match(r'^[A-Z0-9]+$', code.upper()):
            errors['code'] = ['Combination code must contain only uppercase letters and numbers (e.g., PCM, CBG, HKL).']
        
        # Check for duplicate code
        if code and not errors.get('code'):
            existing_code = Combination.objects.filter(
                code__iexact=code
            ).exclude(pk=combination_id)
            
            if existing_code.exists():
                existing = existing_code.first()
                errors['code'] = [f'Combination code "{code.upper()}" already exists.']
        
        return len(errors) == 0, errors
    
    def _create(self, request):
        code = request.POST.get('code', '').strip().upper()
        
        # Validate required fields
        if not code:
            errors = {'code': ['Combination code is required.']}
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Get the A-Level educational level (there should be at least one)
        educational_level = EducationalLevel.objects.filter(level_type='A_LEVEL').first()
        if not educational_level:
            return JsonResponse({
                'success': False,
                'message': 'No A-Level educational level found. Please create an A-Level level first.',
                'errors': {'__all__': ['No A-Level educational level available.']}
            }, status=400)
        
        # Perform comprehensive validation - FIXED: changed from _validate_validation to _validate_combination
        is_valid, validation_errors = self._validate_combination(code)
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                combination = Combination(
                    educational_level=educational_level,
                    code=code,
                )
                combination.full_clean()
                combination.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Combination "{combination.code}" created successfully.',
                    'combination': {
                        'id': combination.pk,
                        'code': combination.code,
                        'educational_level': combination.educational_level.name,
                        'educational_level_id': combination.educational_level_id,
                        'subject_count': 0,
                        'student_count': 0,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating combination: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _update(self, request):
        combination_id = request.POST.get('id')
        if not combination_id:
            return JsonResponse({
                'success': False,
                'message': 'Combination ID required',
                'errors': {'id': ['Combination ID is required.']}
            }, status=400)
        
        try:
            combination = get_object_or_404(Combination, pk=combination_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Combination not found.',
                'errors': {'__all__': ['The requested combination does not exist.']}
            }, status=404)
        
        code = request.POST.get('code', '').strip().upper()
        
        # Validate required fields
        if not code:
            errors = {'code': ['Combination code is required.']}
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_combination(code, combination_id)
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'code' in validation_errors:
                message = validation_errors['code'][0]
            else:
                message = 'Please correct the errors below.'
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': validation_errors
            }, status=400)
        
        try:
            with transaction.atomic():
                combination.code = code
                
                combination.full_clean()
                combination.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Combination "{combination.code}" updated successfully.',
                    'combination': {
                        'id': combination.pk,
                        'code': combination.code,
                        'educational_level': combination.educational_level.name,
                        'educational_level_id': combination.educational_level_id,
                    }
                })
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            return JsonResponse({
                'success': False,
                'message': message,
                'errors': formatted_errors
            }, status=400)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating combination {combination_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred. Please try again.']}
            }, status=500)
    
    def _delete(self, request):
        combination_id = request.POST.get('id')
        if not combination_id:
            return JsonResponse({
                'success': False,
                'message': 'Combination ID required',
                'errors': {'id': ['Combination ID is required.']}
            }, status=400)
        
        try:
            combination = get_object_or_404(Combination, pk=combination_id)
        except Exception:
            return JsonResponse({
                'success': False,
                'message': 'Combination not found.',
                'errors': {'__all__': ['The requested combination does not exist.']}
            }, status=404)
        
        # Check dependencies
        dependency_errors = {}
        
        if combination.combination_subjects.exists():
            dependency_errors['__all__'] = [
                'Cannot delete combination that has subjects. Please remove all subjects first.'
            ]
        
        if combination.student_assignments.filter(is_active=True).exists():
            if '__all__' in dependency_errors:
                dependency_errors['__all__'].append(
                    'Cannot delete combination that has active student assignments.'
                )
            else:
                dependency_errors['__all__'] = [
                    'Cannot delete combination that has active student assignments.'
                ]
        
        if dependency_errors:
            return JsonResponse({
                'success': False,
                'message': dependency_errors['__all__'][0],
                'errors': dependency_errors
            }, status=400)
        
        try:
            combination_code = combination.code
            combination.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Combination "{combination_code}" deleted successfully.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error deleting combination {combination_id}: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred while deleting.',
                'errors': {'__all__': ['An unexpected error occurred while deleting. Please try again.']}
            }, status=500)


class GetCombinationDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get combination details for editing."""
    
    def get(self, request, pk):
        combination = get_object_or_404(Combination, pk=pk)
        
        return JsonResponse({
            'id': combination.pk,
            'code': combination.code,
            'educational_level_id': combination.educational_level_id,
            'educational_level': combination.educational_level.name,
            'subject_count': combination.combination_subjects.count(),
            'student_count': combination.student_assignments.filter(
                is_active=True,
                enrollment__academic_year__is_active=True
            ).count(),
        })


# ============================================================================
# STUDENT COMBINATION ASSIGNMENT VIEWS
# ============================================================================

class CombinationStudentsView(ManagementRequiredMixin, TemplateView):
    """View all students assigned to a specific combination."""
    template_name = 'portal_management/academic/combination_students.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        combination = get_object_or_404(Combination, pk=self.kwargs['pk'])
        ctx['combination'] = combination
        
        # Get all students with active assignments to this combination
        assignments = StudentCombinationAssignment.objects.filter(
            combination=combination,
            is_active=True,
            enrollment__academic_year__is_active=True
        ).select_related(
            'student',
            'enrollment__class_level',
            'enrollment__academic_year',
            'enrollment__stream_assignment__stream_class'
        ).order_by('student__first_name', 'student__last_name')
        
        students = []
        for assignment in assignments:
            student = assignment.student
            student.current_class = assignment.enrollment.class_level.name
            student.academic_year = assignment.enrollment.academic_year.name
            student.stream = assignment.enrollment.stream_assignment.stream_class.name if hasattr(assignment.enrollment, 'stream_assignment') else None
            student.assigned_date = assignment.assigned_date
            student.assignment_id = assignment.pk
            students.append(student)
        
        ctx['students'] = students
        ctx['student_count'] = len(students)
        
        return ctx




class StudentCombinationAssignView(ManagementRequiredMixin, View):
    """
    Assign a student to a combination.
    Creates a new active StudentCombinationAssignment record.
    """
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        student_id = request.POST.get('student_id')
        enrollment_id = request.POST.get('enrollment_id')
        combination_id = request.POST.get('combination_id')
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate required fields
        if not all([student_id, enrollment_id, combination_id]):
            errors = {}
            if not student_id:
                errors['student_id'] = ['Student is required.']
            if not enrollment_id:
                errors['enrollment_id'] = ['Enrollment is required.']
            if not combination_id:
                errors['combination_id'] = ['Combination is required.']
            
            return JsonResponse({
                'success': False,
                'message': 'Please fill in all required fields.',
                'errors': errors
            }, status=400)
        
        try:
            # Get related objects
            student = get_object_or_404(Student, pk=student_id)
            enrollment = get_object_or_404(StudentEnrollment, pk=enrollment_id)
            combination = get_object_or_404(Combination, pk=combination_id)
            
            # Verify student matches enrollment
            if enrollment.student_id != student.pk:
                return JsonResponse({
                    'success': False,
                    'message': 'Student does not match the enrollment record.',
                    'errors': {'student_id': ['Selected student does not match this enrollment.']}
                }, status=400)
            
            # Verify this is an A-Level enrollment
            if enrollment.class_level.educational_level.level_type != 'A_LEVEL':
                return JsonResponse({
                    'success': False,
                    'message': 'Combinations can only be assigned to A-Level students.',
                    'errors': {'enrollment_id': ['This enrollment is not for A-Level.']}
                }, status=400)
            
            # Verify combination belongs to the same educational level
            if combination.educational_level != enrollment.class_level.educational_level:
                return JsonResponse({
                    'success': False,
                    'message': f'Combination "{combination.code}" is for {combination.educational_level.name}, but the student is enrolled in {enrollment.class_level.educational_level.name}.',
                    'errors': {'combination_id': ['Combination must match the student\'s educational level.']}
                }, status=400)
            
            # Check if student already has an active assignment for this enrollment
            existing_active = StudentCombinationAssignment.objects.filter(
                enrollment=enrollment,
                is_active=True
            ).first()
            
            if existing_active:
                return JsonResponse({
                    'success': False,
                    'message': f'Student already has an active combination: {existing_active.combination.code}. Please deactivate it first.',
                    'errors': {'__all__': ['Student already has an active combination.']}
                }, status=400)
            
            # Create the assignment
            with transaction.atomic():
                assignment = StudentCombinationAssignment.objects.create(
                    student=student,
                    enrollment=enrollment,
                    combination=combination,
                    assigned_date=timezone.now().date(),
                    is_active=True,
                    remarks=remarks
                )
                
                # Get the complete assignment with related data for response
                assignment = StudentCombinationAssignment.objects.select_related(
                    'student', 'combination', 'enrollment__class_level', 'enrollment__academic_year'
                ).get(pk=assignment.pk)
                
                return JsonResponse({
                    'success': True,
                    'message': f'Student {student.full_name} assigned to {combination.code} successfully.',
                    'assignment': {
                        'id': assignment.pk,
                        'student_id': student.pk,
                        'student_name': student.full_name,
                        'student_reg': student.registration_number,
                        'combination_id': combination.pk,
                        'combination_code': combination.code,
                        'class_level': enrollment.class_level.name,
                        'academic_year': enrollment.academic_year.name,
                        'assigned_date': assignment.assigned_date.strftime('%Y-%m-%d'),
                        'remarks': assignment.remarks,
                    }
                })
                
        except Exception as e:
            logger.error(f"Error assigning combination: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': [str(e)]}
            }, status=500)


class StudentCombinationRemoveView(ManagementRequiredMixin, View):
    """
    Remove a student from a combination (soft delete by deactivating).
    This deactivates the assignment rather than deleting it to preserve history.
    """
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        assignment_id = request.POST.get('assignment_id')
        
        if not assignment_id:
            return JsonResponse({
                'success': False,
                'message': 'Assignment ID required.',
                'errors': {'assignment_id': ['Assignment ID is required.']}
            }, status=400)
        
        try:
            assignment = get_object_or_404(StudentCombinationAssignment, pk=assignment_id)
            
            if not assignment.is_active:
                return JsonResponse({
                    'success': False,
                    'message': 'This assignment is already inactive.',
                    'errors': {'__all__': ['Assignment is already inactive.']}
                }, status=400)
            
            with transaction.atomic():
                assignment.is_active = False
                assignment.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'{assignment.student.full_name} removed from {assignment.combination.code} successfully.'
                })
                
        except Exception as e:
            logger.error(f"Error removing combination assignment: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': [str(e)]}
            }, status=500)


class StudentCombinationBulkRemoveView(ManagementRequiredMixin, View):
    """
    Bulk remove multiple students from a combination.
    Deactivates multiple assignments in a single transaction.
    """
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        assignment_ids = request.POST.getlist('assignment_ids')
        combination_id = request.POST.get('combination_id')
        
        if not assignment_ids:
            return JsonResponse({
                'success': False,
                'message': 'No assignments selected.',
                'errors': {'assignment_ids': ['Please select at least one student.']}
            }, status=400)
        
        try:
            # Get all active assignments for the given IDs
            assignments = StudentCombinationAssignment.objects.filter(
                pk__in=assignment_ids,
                is_active=True
            ).select_related('student', 'combination')
            
            if not assignments.exists():
                return JsonResponse({
                    'success': False,
                    'message': 'No active assignments found for the selected students.',
                    'errors': {'__all__': ['No active assignments found.']}
                }, status=400)
            
            # If combination_id is provided, verify all assignments belong to that combination
            if combination_id:
                combination = get_object_or_404(Combination, pk=combination_id)
                invalid_assignments = assignments.exclude(combination_id=combination_id)
                
                if invalid_assignments.exists():
                    student_names = [a.student.full_name for a in invalid_assignments[:3]]
                    return JsonResponse({
                        'success': False,
                        'message': f'Some selected students are not assigned to {combination.code}.',
                        'errors': {'__all__': [f'Invalid selections: {", ".join(student_names)}']}
                    }, status=400)
            
            count = assignments.count()
            student_names = [a.student.full_name for a in assignments[:5]]
            
            with transaction.atomic():
                # Deactivate all assignments
                assignments.update(is_active=False)
                
                # Prepare success message
                if count == 1:
                    message = f'{student_names[0]} removed from combination successfully.'
                else:
                    message = f'{count} students removed from combination successfully.'
                    if len(student_names) < count:
                        message += f' ({", ".join(student_names[:3])} and {count - 3} others)'
                
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'removed_count': count,
                    'students': student_names[:10]
                })
                
        except Exception as e:
            logger.error(f"Error in bulk remove: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': [str(e)]}
            }, status=500)


class GetCombinationHistoryView(ManagementRequiredMixin, View):
    """
    AJAX endpoint to get combination assignment history for a student enrollment.
    """
    
    def get(self, request):
        enrollment_id = request.GET.get('enrollment_id')
        student_id = request.GET.get('student_id')
        
        if not enrollment_id and not student_id:
            return JsonResponse({'assignments': []})
        
        # Base queryset
        assignments = StudentCombinationAssignment.objects.select_related(
            'combination', 'student'
        ).order_by('-assigned_date')
        
        # Apply filters
        if enrollment_id:
            assignments = assignments.filter(enrollment_id=enrollment_id)
        elif student_id:
            assignments = assignments.filter(student_id=student_id)
        
        # Limit to last 20 assignments for performance
        assignments = assignments[:20]
        
        data = [{
            'id': a.pk,
            'student_name': a.student.full_name,
            'student_reg': a.student.registration_number,
            'combination_id': a.combination_id,
            'combination_code': a.combination.code,
            'assigned_date': a.assigned_date.strftime('%Y-%m-%d'),
            'is_active': a.is_active,
            'remarks': a.remarks,
        } for a in assignments]
        
        return JsonResponse({'assignments': data})


class GetAvailableStudentsForCombinationView(ManagementRequiredMixin, View):
    """
    AJAX endpoint to get students available for combination assignment.
    Returns A-Level students without active combination assignments.
    """
    
    def get(self, request):
        combination_id = request.GET.get('combination_id')
        search = request.GET.get('search', '')
        class_level_id = request.GET.get('class_level_id')
        
        # Get students with A-Level enrollments but no active combination
        students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL',
            enrollments__academic_year__is_active=True,
            status='active'
        ).exclude(
            enrollments__combination_assignments__is_active=True
        ).distinct().select_related('user')
        
        # Apply search filter
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(registration_number__icontains=search)
            )
        
        # Apply class level filter
        if class_level_id:
            students = students.filter(
                enrollments__class_level_id=class_level_id
            )
        
        # Limit results for performance
        students = students.order_by('first_name', 'last_name')[:50]
        
        data = [{
            'id': s.pk,
            'full_name': s.full_name,
            'registration_number': s.registration_number,
            'class_level': s.enrollments.filter(academic_year__is_active=True).first().class_level.name if s.enrollments.filter(academic_year__is_active=True).exists() else None,
        } for s in students]
        
        return JsonResponse({'students': data})


class GetALevelEnrollmentsView(ManagementRequiredMixin, View):
    """
    AJAX endpoint to get A-Level enrollments for a selected student.
    """
    
    def get(self, request):
        student_id = request.GET.get('student_id')
        academic_year_id = request.GET.get('academic_year_id')
        
        if not student_id:
            return JsonResponse({'enrollments': []})
        
        enrollments = StudentEnrollment.objects.filter(
            student_id=student_id,
            class_level__educational_level__level_type='A_LEVEL',
            status='active'
        ).select_related('class_level', 'academic_year').order_by('-academic_year__start_date')
        
        if academic_year_id:
            enrollments = enrollments.filter(academic_year_id=academic_year_id)
        
        data = [{
            'id': e.pk,
            'text': f"{e.class_level.name} - {e.academic_year.name}",
            'academic_year': e.academic_year.name,
            'academic_year_id': e.academic_year_id,
            'class_level': e.class_level.name,
            'class_level_id': e.class_level_id,
            'has_active_combination': e.combination_assignments.filter(is_active=True).exists(),
            'current_combination': e.combination_assignments.filter(is_active=True).first().combination.code if e.combination_assignments.filter(is_active=True).exists() else None,
        } for e in enrollments]
        
        return JsonResponse({'enrollments': data})
    

class CombinationSubjectsView(ManagementRequiredMixin, TemplateView):
    """View and manage subjects in a combination."""
    template_name = 'portal_management/academic/combination_subjects.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        combination = get_object_or_404(Combination, pk=self.kwargs['pk'])
        ctx['combination'] = combination
        
        # Get all subjects in this combination
        combination_subjects = CombinationSubject.objects.filter(
            combination=combination
        ).select_related('subject').order_by('role', 'subject__name')
        
        ctx['combination_subjects'] = combination_subjects
        ctx['total_subjects'] = combination_subjects.count()
        
        # Count by role
        ctx['core_count'] = combination_subjects.filter(role='CORE').count()
        ctx['subsidiary_count'] = combination_subjects.filter(role='SUBSIDIARY').count()
        
        # Get available subjects (subjects in the same educational level not already in this combination)
        available_subjects = Subject.objects.filter(
            educational_level=combination.educational_level
        ).exclude(
            combination_subjects__combination=combination
        ).order_by('name')
        
        ctx['available_subjects'] = available_subjects
        ctx['available_count'] = available_subjects.count()
        
        return ctx


class CombinationSubjectCRUDView(ManagementRequiredMixin, View):
    """CRUD operations for subjects within a combination."""
    
    def post(self, request):
        action = request.POST.get('action')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if not is_ajax:
            return JsonResponse({'success': False, 'message': 'AJAX required'}, status=400)
        
        if action == 'add_subject':
            return self._add_subject(request)
        elif action == 'update_role':
            return self._update_role(request)
        elif action == 'remove_subject':
            return self._remove_subject(request)
        else:
            return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)
    
    def _add_subject(self, request):
        combination_id = request.POST.get('combination_id')
        subject_id = request.POST.get('subject_id')
        role = request.POST.get('role', 'CORE')
        
        if not all([combination_id, subject_id]):
            return JsonResponse({
                'success': False,
                'message': 'Combination and subject are required.',
                'errors': {
                    'combination_id': ['Combination is required.'] if not combination_id else [],
                    'subject_id': ['Subject is required.'] if not subject_id else []
                }
            }, status=400)
        
        try:
            combination = get_object_or_404(Combination, pk=combination_id)
            subject = get_object_or_404(Subject, pk=subject_id)
            
            # Check if subject already exists in this combination
            if CombinationSubject.objects.filter(combination=combination, subject=subject).exists():
                return JsonResponse({
                    'success': False,
                    'message': f'Subject "{subject.code}" already exists in this combination.',
                    'errors': {'subject_id': ['Subject already exists in this combination.']}
                }, status=400)
            
            # Validate subject belongs to the same educational level
            if subject.educational_level != combination.educational_level:
                return JsonResponse({
                    'success': False,
                    'message': f'Subject "{subject.code}" belongs to {subject.educational_level.name}, but this combination is for {combination.educational_level.name}.',
                    'errors': {'subject_id': ['Subject must belong to the same educational level as the combination.']}
                }, status=400)
            
            # Validate role
            if role not in ['CORE', 'SUBSIDIARY']:
                role = 'CORE'
            
            # For subsidiary role, ensure subject is not compulsory
            if role == 'SUBSIDIARY' and subject.is_compulsory:
                return JsonResponse({
                    'success': False,
                    'message': f'"{subject.name}" is a compulsory subject and cannot be assigned as a Subsidiary.',
                    'errors': {'role': ['Compulsory subjects cannot be subsidiary.']}
                }, status=400)
            
            with transaction.atomic():
                combo_subject = CombinationSubject.objects.create(
                    combination=combination,
                    subject=subject,
                    role=role
                )
                
                return JsonResponse({
                    'success': True,
                    'message': f'Subject "{subject.code}" added to combination as {role.lower()}.',
                    'combination_subject': {
                        'id': combo_subject.pk,
                        'subject_id': subject.id,
                        'subject_code': subject.code,
                        'subject_name': subject.name,
                        'role': role,
                        'is_compulsory': subject.is_compulsory,
                    }
                })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error adding subject to combination: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred.']}
            }, status=500)
    
    def _update_role(self, request):
        combo_subject_id = request.POST.get('id')
        role = request.POST.get('role')
        
        if not combo_subject_id:
            return JsonResponse({
                'success': False,
                'message': 'Combination subject ID required.',
                'errors': {'id': ['ID is required.']}
            }, status=400)
        
        if role not in ['CORE', 'SUBSIDIARY']:
            return JsonResponse({
                'success': False,
                'message': 'Invalid role.',
                'errors': {'role': ['Role must be CORE or SUBSIDIARY.']}
            }, status=400)
        
        try:
            combo_subject = get_object_or_404(CombinationSubject, pk=combo_subject_id)
            
            # Validate role change for compulsory subjects
            if role == 'SUBSIDIARY' and combo_subject.subject.is_compulsory:
                return JsonResponse({
                    'success': False,
                    'message': f'"{combo_subject.subject.name}" is a compulsory subject and cannot be assigned as a Subsidiary.',
                    'errors': {'role': ['Compulsory subjects cannot be subsidiary.']}
                }, status=400)
            
            old_role = combo_subject.role
            combo_subject.role = role
            combo_subject.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Subject role updated from {old_role.lower()} to {role.lower()}.',
                'combination_subject': {
                    'id': combo_subject.pk,
                    'role': role,
                }
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating subject role: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred.']}
            }, status=500)
    
    def _remove_subject(self, request):
        combo_subject_id = request.POST.get('id')
        
        if not combo_subject_id:
            return JsonResponse({
                'success': False,
                'message': 'Combination subject ID required.',
                'errors': {'id': ['ID is required.']}
            }, status=400)
        
        try:
            combo_subject = get_object_or_404(CombinationSubject, pk=combo_subject_id)
            subject_code = combo_subject.subject.code
            combination_code = combo_subject.combination.code
            
            combo_subject.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Subject "{subject_code}" removed from combination {combination_code}.'
            })
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error removing subject from combination: {str(e)}", exc_info=True)
            
            return JsonResponse({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'errors': {'__all__': ['An unexpected error occurred.']}
            }, status=500)



