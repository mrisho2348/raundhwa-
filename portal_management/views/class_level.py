# portal_management/views/class_level.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    ClassLevel, EducationalLevel, StreamClass, Subject, 
    StudentEnrollment, StaffTeachingAssignment, AcademicYear
)

logger = logging.getLogger(__name__)


class ClassLevelDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a class level."""
    template_name = 'portal_management/academic/class_levels/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get the class level with related data
        class_level = get_object_or_404(
            ClassLevel.objects.select_related('educational_level'),
            pk=self.kwargs['pk']
        )
        
        ctx['class_level'] = class_level
        
        # Get streams for this class level - use the property directly
        streams = StreamClass.objects.filter(
            class_level=class_level
        ).order_by('stream_letter')
        
        ctx['streams'] = streams
        ctx['total_streams'] = streams.count()
        
        # Calculate total capacity
        total_capacity = streams.aggregate(total=Sum('capacity'))['total'] or 0
        ctx['total_capacity'] = total_capacity
        
        # Calculate total students by iterating through streams and summing their student_count property
        total_students = sum(stream.student_count for stream in streams)
        ctx['total_students'] = total_students
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        ctx['current_academic_year'] = current_academic_year
        
        # Get enrolled students in this class level for current academic year
        if current_academic_year:
            enrollments = StudentEnrollment.objects.filter(
                class_level=class_level,
                academic_year=current_academic_year,
                status='active'
            ).select_related(
                'student',
                'stream_assignment__stream_class'
            ).order_by('student__first_name', 'student__last_name')[:20]
            
            ctx['enrollments'] = enrollments
            ctx['total_enrolled'] = StudentEnrollment.objects.filter(
                class_level=class_level,
                academic_year=current_academic_year,
                status='active'
            ).count()
        else:
            ctx['enrollments'] = []
            ctx['total_enrolled'] = 0
        
        # Get subjects taught in this class level
        subjects = Subject.objects.filter(
            educational_level=class_level.educational_level
        ).annotate(
            teacher_count=Count(
                'teaching_assignments',
                filter=Q(
                    teaching_assignments__class_level=class_level,
                    teaching_assignments__academic_year=current_academic_year if current_academic_year else None
                ),
                distinct=True
            )
        ).order_by('name')
        
        ctx['subjects'] = subjects
        ctx['total_subjects'] = subjects.count()
        
        # Get teachers assigned to this class level - FIXED: remove DISTINCT ON
        if current_academic_year:
            # Get all teaching assignments for this class level
            all_assignments = StaffTeachingAssignment.objects.filter(
                class_level=class_level,
                academic_year=current_academic_year
            ).select_related(
                'staff',
                'staff__user',
                'subject'
            ).order_by('staff__first_name', 'staff__last_name')
            
            # Create a dictionary to get unique teachers
            unique_teachers = {}
            for assignment in all_assignments:
                if assignment.staff_id not in unique_teachers:
                    unique_teachers[assignment.staff_id] = assignment
            
            # Get the first 20 unique teachers
            teachers = list(unique_teachers.values())[:20]
            
            # Get total count of unique teachers
            total_teachers = len(unique_teachers)
            
            ctx['teachers'] = teachers
            ctx['total_teachers'] = total_teachers
        else:
            ctx['teachers'] = []
            ctx['total_teachers'] = 0
        
        # Calculate utilization statistics
        if ctx['total_capacity'] > 0:
            ctx['capacity_utilization'] = (ctx['total_students'] / ctx['total_capacity']) * 100
        else:
            ctx['capacity_utilization'] = 0
        
        # Get class level order information
        previous_class = ClassLevel.objects.filter(
            educational_level=class_level.educational_level,
            order__lt=class_level.order
        ).order_by('-order').first()
        
        next_class = ClassLevel.objects.filter(
            educational_level=class_level.educational_level,
            order__gt=class_level.order
        ).order_by('order').first()
        
        ctx['previous_class'] = previous_class
        ctx['next_class'] = next_class
        
        return ctx