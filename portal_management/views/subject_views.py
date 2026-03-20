# portal_management/views/subject.py

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
    Subject, EducationalLevel, Student, StudentEnrollment, 
    StudentSubjectAssignment, AcademicYear
)

logger = logging.getLogger(__name__)


class SubjectAssignStudentsView(ManagementRequiredMixin, View):
    """View to assign students to an optional subject."""
    template_name = 'portal_management/academic/subjects/assign_students.html'
    
    def get_eligible_students(self, subject):
        """
        Get students eligible for assignment to this optional subject.
        Criteria:
        1. Student is active
        2. Student has active enrollment in current academic year
        3. Student is enrolled in the same educational level as the subject
        4. Student has not been assigned to this subject yet
        """
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return []
        
        # Get students with active enrollment in current academic year
        # and same educational level as the subject
        enrollments_without_subject = StudentEnrollment.objects.filter(
            status='active',
            academic_year=current_academic_year,
            class_level__educational_level=subject.educational_level,
            student__status='active'
        ).exclude(
            subject_assignments__subject=subject
        ).select_related('student').order_by('student__first_name', 'student__last_name')
        
        # Extract students from these enrollments
        eligible_students = []
        for enrollment in enrollments_without_subject:
            student = enrollment.student
            student.enrollment_id = enrollment.pk
            student.enrollment_date = enrollment.enrollment_date
            eligible_students.append(student)
        
        return eligible_students
    
    def get_assigned_students(self, subject):
        """Get students already assigned to this subject."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return StudentSubjectAssignment.objects.none()
        
        return StudentSubjectAssignment.objects.filter(
            subject=subject,
            enrollment__academic_year=current_academic_year,
            enrollment__status='active'
        ).select_related(
            'enrollment__student',
            'enrollment__academic_year'
        ).order_by('enrollment__student__first_name', 'enrollment__student__last_name')
    
    def get(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        
        # Check if subject is optional
        if subject.is_compulsory:
            messages.error(request, 'Compulsory subjects are taken by all students and cannot be assigned individually.')
            return redirect('management:subject_list')
        
        # Get eligible students
        eligible_students = self.get_eligible_students(subject)
        
        # Get already assigned students
        assigned_students = self.get_assigned_students(subject)
        
        return render(request, self.template_name, {
            'subject': subject,
            'eligible_students': eligible_students,
            'assigned_students': assigned_students,
            'title': f'Assign Students to {subject.name}',
        })
    
    def post(self, request, pk):
        subject = get_object_or_404(Subject, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check if subject is optional
        if subject.is_compulsory:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Compulsory subjects are taken by all students and cannot be assigned individually.'
                }, status=400)
            messages.error(request, 'Compulsory subjects are taken by all students and cannot be assigned individually.')
            return redirect('management:subject_list')
        
        # Get selected student IDs
        student_ids = request.POST.getlist('students')
        
        if not student_ids:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please select at least one student to assign.'
                }, status=400)
            messages.error(request, 'Please select at least one student to assign.')
            return redirect('management:subject_assign_students', pk=subject.pk)
        
        # Get current academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No active academic year found.'
                }, status=400)
            messages.error(request, 'No active academic year found.')
            return redirect('management:subject_assign_students', pk=subject.pk)
        
        assigned_count = 0
        errors = []
        
        with transaction.atomic():
            for student_id in student_ids:
                try:
                    student = Student.objects.get(pk=student_id)
                    
                    # Get active enrollment
                    enrollment = student.enrollments.filter(
                        status='active',
                        academic_year=current_academic_year,
                        class_level__educational_level=subject.educational_level
                    ).first()
                    
                    if not enrollment:
                        errors.append(f'{student.full_name} - No active enrollment found in {subject.educational_level.name}.')
                        continue
                    
                    # Check if already assigned
                    if StudentSubjectAssignment.objects.filter(enrollment=enrollment, subject=subject).exists():
                        errors.append(f'{student.full_name} - Already assigned to this subject.')
                        continue
                    
                    # Create subject assignment
                    StudentSubjectAssignment.objects.create(
                        student=student,
                        enrollment=enrollment,
                        subject=subject
                    )
                    assigned_count += 1
                    
                except Student.DoesNotExist:
                    errors.append(f'Student with ID {student_id} not found.')
                except Exception as e:
                    errors.append(f'Error assigning student: {str(e)}')
        
        if assigned_count > 0:
            message = f'Successfully assigned {assigned_count} student(s) to {subject.name}.'
            if errors:
                message += f' However, {len(errors)} student(s) could not be assigned.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'assigned_count': assigned_count,
                    'errors': errors
                })
            messages.success(request, message)
            if errors:
                for error in errors:
                    messages.warning(request, error)
        else:
            error_msg = 'No students were assigned. ' + ' '.join(errors)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': errors
                }, status=400)
            messages.error(request, error_msg)
        
        return redirect('management:subject_assign_students', pk=subject.pk)


class SubjectRemoveStudentView(ManagementRequiredMixin, View):
    """Remove a student from a subject assignment."""
    
    def post(self, request, pk, assignment_pk):
        assignment = get_object_or_404(StudentSubjectAssignment, pk=assignment_pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = assignment.student.full_name
            subject_name = assignment.subject.name
            
            with transaction.atomic():
                assignment.delete()
            
            message = f'{student_name} has been removed from {subject_name}.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            messages.success(request, message)
            
        except Exception as e:
            logger.error(f"Error removing student from subject: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=500)
            messages.error(request, f'Error removing student: {str(e)}')
        
        return redirect('management:subject_assign_students', pk=pk)


class SubjectStudentsView(ManagementRequiredMixin, TemplateView):
    """View students assigned to a subject."""
    template_name = 'portal_management/academic/subjects/students.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        subject = get_object_or_404(Subject, pk=self.kwargs['pk'])
        
        # Get assigned students
        assigned_students = StudentSubjectAssignment.objects.filter(
            subject=subject,
            enrollment__academic_year__is_active=True
        ).select_related(
            'enrollment__student',
            'enrollment__academic_year'
        ).order_by('enrollment__student__first_name', 'enrollment__student__last_name')
        
        ctx['subject'] = subject
        ctx['students'] = assigned_students
        ctx['student_count'] = assigned_students.count()
        ctx['title'] = f'Students Taking {subject.name}'
        
        return ctx