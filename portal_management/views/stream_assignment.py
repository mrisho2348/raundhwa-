# portal_management/views/stream_assignment.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Exists, OuterRef
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    StreamClass, StudentEnrollment, StudentStreamAssignment,
    AcademicYear, ClassLevel, Student
)

logger = logging.getLogger(__name__)


class StreamAssignStudentsView(ManagementRequiredMixin, View):
    """View to assign students to a stream."""
    template_name = 'portal_management/academic/streams/assign_students.html'
    
    def get_eligible_students(self, stream):
        """
        Get students eligible for assignment to this stream.
        Criteria:
        1. Student is active
        2. Student has active enrollment in current academic year
        3. Student is enrolled in the same class level as the stream
        4. Student has not been assigned to any stream yet
        """
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return []
        
        # Get all enrollments for the current academic year and class level
        # that are active and don't have a stream assignment
        enrollments_without_stream = StudentEnrollment.objects.filter(
            status='active',
            academic_year=current_academic_year,
            class_level=stream.class_level,
            stream_assignment__isnull=True  # No stream assignment
        ).select_related('student').order_by('student__first_name', 'student__last_name')
        
        # Extract students from these enrollments
        eligible_students = []
        for enrollment in enrollments_without_stream:
            student = enrollment.student
            if student.status == 'active':  # Double-check student is active
                student.enrollment_id = enrollment.pk
                student.enrollment_date = enrollment.enrollment_date
                eligible_students.append(student)
        
        return eligible_students
    
    def get_assigned_students(self, stream):
        """Get students already assigned to this stream."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return StudentStreamAssignment.objects.none()
        
        return StudentStreamAssignment.objects.filter(
            stream_class=stream,
            enrollment__academic_year=current_academic_year,
            enrollment__status='active'
        ).select_related(
            'enrollment__student',
            'enrollment__academic_year'
        ).order_by('enrollment__student__first_name', 'enrollment__student__last_name')
    
    def get(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        
        # Check capacity
        current_count = stream.student_count
        available_slots = stream.capacity - current_count
        
        # Get eligible students
        eligible_students = self.get_eligible_students(stream)
        
        # Get already assigned students
        assigned_students = self.get_assigned_students(stream)
        
        # Get current academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        return render(request, self.template_name, {
            'stream': stream,
            'eligible_students': eligible_students,
            'assigned_students': assigned_students,
            'current_count': current_count,
            'available_slots': available_slots,
            'capacity': stream.capacity,
            'current_academic_year': current_academic_year,
            'title': f'Assign Students to {stream.name}',
        })
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get selected student IDs
        student_ids = request.POST.getlist('students')
        
        if not student_ids:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please select at least one student to assign.'
                }, status=400)
            messages.error(request, 'Please select at least one student to assign.')
            return redirect('management:stream_assign_students', pk=stream.pk)
        
        # Check capacity
        current_count = stream.student_count
        if current_count + len(student_ids) > stream.capacity:
            error_msg = f'Cannot assign {len(student_ids)} students. Only {stream.capacity - current_count} slots available.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:stream_assign_students', pk=stream.pk)
        
        # Get current academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'No active academic year found.'
                }, status=400)
            messages.error(request, 'No active academic year found.')
            return redirect('management:stream_assign_students', pk=stream.pk)
        
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
                        class_level=stream.class_level
                    ).first()
                    
                    if not enrollment:
                        errors.append(f'{student.full_name} - No active enrollment found in {stream.class_level.name}.')
                        continue
                    
                    # Check if already assigned
                    if StudentStreamAssignment.objects.filter(enrollment=enrollment).exists():
                        errors.append(f'{student.full_name} - Already assigned to a stream.')
                        continue
                    
                    # Create stream assignment
                    StudentStreamAssignment.objects.create(
                        enrollment=enrollment,
                        stream_class=stream,
                        assigned_date=timezone.now().date(),
                        remarks=f'Assigned to stream {stream.name} on {timezone.now().date()}'
                    )
                    assigned_count += 1
                    
                except Student.DoesNotExist:
                    errors.append(f'Student with ID {student_id} not found.')
                except Exception as e:
                    errors.append(f'Error assigning student: {str(e)}')
        
        if assigned_count > 0:
            message = f'Successfully assigned {assigned_count} student(s) to {stream.name}.'
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
        
        return redirect('management:stream_class_detail', pk=stream.pk)


class StreamRemoveStudentView(ManagementRequiredMixin, View):
    """Remove a student from a stream."""
    
    def post(self, request, pk, assignment_pk):
        assignment = get_object_or_404(StudentStreamAssignment, pk=assignment_pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            student_name = assignment.enrollment.student.full_name
            stream_name = assignment.stream_class.name
            
            with transaction.atomic():
                assignment.delete()
            
            message = f'{student_name} has been removed from {stream_name}.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            messages.success(request, message)
            
        except Exception as e:
            logger.error(f"Error removing student from stream: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=500)
            messages.error(request, f'Error removing student: {str(e)}')
        
        return redirect('management:stream_assign_students', pk=pk)