# views.py - Exam Result Analytics View

from django.views import View
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Avg, Count, Sum, F, FloatField, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
import json
from core.models import (
    ExamSession, StudentEnrollment, Student, StudentExamMetrics,
    StudentExamPosition, StudentSubjectResult, StudentPaperScore,
    SubjectExamPaper, EducationalLevel, StudentStreamAssignment, Subject
)


class ExamResultAnalyticsView(LoginRequiredMixin, View):
    """
    Comprehensive exam result analytics view with educational level specific templates.
    Routes to different templates based on educational level.
    """
    
    def get(self, request, pk):
        # Get exam session
        session = get_object_or_404(ExamSession, pk=pk)
        
        # Get educational level type
        level_type = session.class_level.educational_level.level_type
        
        # Route to appropriate template based on educational level
        if level_type == 'PRIMARY':
            template_name = 'portal_management/exams/analytics/primary_analytics.html'
        elif level_type == 'NURSERY':
            template_name = 'portal_management/exams/analytics/nursery_analytics.html'
        elif level_type == 'O_LEVEL':
            template_name = 'portal_management/exams/analytics/olevel_analytics.html'
        elif level_type == 'A_LEVEL':
            template_name = 'portal_management/exams/analytics/alevel_analytics.html'
        else:
            template_name = 'portal_management/exams/analytics/general_analytics.html'
        
        # Get filter parameters
        top_n = int(request.GET.get('top_n', 10))
        bottom_n = int(request.GET.get('bottom_n', 10))
        grade_filter = request.GET.get('grade', '')
        division_filter = request.GET.get('division', '')
        search_query = request.GET.get('search', '')
        gender_filter = request.GET.get('gender', '')
        
        # Get all enrolled students for this session
        enrolled_students = StudentEnrollment.objects.filter(
            academic_year=session.academic_year,
            class_level=session.class_level,
            status='active'
        ).select_related('student', 'student__user')
        
        if session.stream_class:
            enrolled_students = enrolled_students.filter(
                stream_assignment__stream_class=session.stream_class
            )
        
        enrolled_students = enrolled_students.order_by('student__first_name', 'student__last_name')
        
        # Get position data for this session
        positions = {
            pos.student_id: {
                'class_position': pos.class_position,
                'stream_position': pos.stream_position
            }
            for pos in StudentExamPosition.objects.filter(exam_session=session)
        }
        
        # Get metrics data
        metrics_data = {
            metric.student_id: {
                'total_marks': metric.total_marks,
                'average_marks': metric.average_marks,
                'total_points': metric.total_points,
                'division': metric.division,
                'remarks': metric.remarks
            }
            for metric in StudentExamMetrics.objects.filter(exam_session=session)
        }
        
        # Get subject results for all students
        subject_results = StudentSubjectResult.objects.filter(
            exam_session=session
        ).select_related('student', 'subject')
        
        # Organize subject results by student
        student_subject_results = {}
        for result in subject_results:
            if result.student_id not in student_subject_results:
                student_subject_results[result.student_id] = {}
            student_subject_results[result.student_id][result.subject_id] = {
                'grade': result.grade,
                'points': result.points,
                'total_marks': float(result.total_marks),
                'remarks': result.remarks
            }
        
        # Get subject exam papers for this session
        subject_papers = SubjectExamPaper.objects.filter(
            exam_session=session
        ).select_related('subject').order_by('subject__name', 'paper_number')
        
        # Organize papers by subject
        papers_by_subject = {}
        subject_objects = []
        subject_ids = set()
        
        for paper in subject_papers:
            subject_id = paper.subject_id
            subject_ids.add(subject_id)
            
            if subject_id not in papers_by_subject:
                papers_by_subject[subject_id] = {
                    'subject': paper.subject,
                    'papers': []
                }
            papers_by_subject[subject_id]['papers'].append({
                'paper_number': paper.paper_number,
                'paper_name': paper.paper_name,
                'max_marks': float(paper.max_marks)
            })
        
        # Get subject objects
        for subject_id in subject_ids:
            try:
                subject = Subject.objects.get(pk=subject_id)
                subject_objects.append({
                    'id': subject.id,
                    'name': subject.name,
                    'short_name': subject.short_name or subject.name[:15],
                    'code': subject.code
                })
            except Subject.DoesNotExist:
                continue
        
        # Get paper scores for each student
        paper_scores = StudentPaperScore.objects.filter(
            exam_paper__exam_session=session
        ).select_related('exam_paper')
        
        # Organize paper scores by student and subject
        student_paper_scores = {}
        for score in paper_scores:
            student_id = score.student_id
            subject_id = score.exam_paper.subject_id
            
            if student_id not in student_paper_scores:
                student_paper_scores[student_id] = {}
            if subject_id not in student_paper_scores[student_id]:
                student_paper_scores[student_id][subject_id] = []
            
            student_paper_scores[student_id][subject_id].append({
                'paper_number': score.exam_paper.paper_number,
                'marks': float(score.marks),
                'max_marks': float(score.exam_paper.max_marks)
            })
        
        # Build student analytics data
        students_data = []
        for enrollment in enrolled_students:
            student = enrollment.student
            student_id = student.pk
            
            # Apply gender filter
            if gender_filter and student.gender != gender_filter:
                continue
            
            # Get position data
            position_data = positions.get(student_id, {})
            
            # Get metrics data
            metrics = metrics_data.get(student_id, {})
            
            # Get subject results for this student
            subjects_result = student_subject_results.get(student_id, {})
            
            # Get paper scores for this student
            papers_scores = student_paper_scores.get(student_id, {})
            
            # Determine if student has any results
            has_results = len(subjects_result) > 0
            
            # Build subject performance with paper details
            subject_performance = []
            for subject in subject_objects:
                subject_result = subjects_result.get(subject['id'], {})
                subject_papers = papers_scores.get(subject['id'], [])
                
                # Calculate average for this subject from papers
                subject_average = 0
                if subject_papers:
                    total_marks = sum(p['marks'] for p in subject_papers)
                    total_max = sum(p['max_marks'] for p in subject_papers)
                    subject_average = (total_marks / total_max * 100) if total_max > 0 else 0
                
                if level_type in ['PRIMARY', 'NURSERY']:
                    subject_performance.append({
                        'subject_name': subject['name'],
                        'subject_code': subject['code'],
                        'grade': subject_result.get('grade', 'N/A') if has_results else 'Absent',
                        'marks': subject_result.get('total_marks', 'N/A') if has_results else 'Absent',
                        'average': round(subject_average, 2),
                        'papers': subject_papers
                    })
                else:
                    subject_performance.append({
                        'subject_name': subject['name'],
                        'subject_code': subject['code'],
                        'grade': subject_result.get('grade', 'N/A') if has_results else 'Absent',
                        'points': subject_result.get('points', 'N/A') if has_results else 'Absent',
                        'marks': subject_result.get('total_marks', 'N/A') if has_results else 'Absent',
                        'average': round(subject_average, 2),
                        'papers': subject_papers
                    })
            
            total_marks = metrics.get('total_marks', 0) if has_results else 0
            average_marks = metrics.get('average_marks', 0) if has_results else 0
            grade = None
            division = metrics.get('division', '') if has_results else ''
            points = metrics.get('total_points', '') if has_results else ''
            
            # Get overall grade for Primary/Nursery
            if level_type in ['PRIMARY', 'NURSERY'] and has_results:
                grades = [s['grade'] for s in subject_performance if s['grade'] != 'N/A' and s['grade'] != 'Absent']
                if grades:
                    grade_map = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1, 'F': 0}
                    avg_grade = sum(grade_map.get(g, 0) for g in grades) / len(grades)
                    for g, val in sorted(grade_map.items(), key=lambda x: x[1], reverse=True):
                        if avg_grade >= val:
                            grade = g
                            break
            
            # Apply grade filter
            if grade_filter and level_type in ['PRIMARY', 'NURSERY']:
                if grade != grade_filter:
                    continue
            
            # Apply division filter
            if division_filter and level_type in ['O_LEVEL', 'A_LEVEL']:
                if division != division_filter:
                    continue
            
            # Apply search filter
            if search_query:
                if not (search_query.lower() in student.full_name.lower() or 
                        search_query.lower() in (student.registration_number or '').lower()):
                    continue
            
            students_data.append({
                'student_id': student_id,
                'full_name': student.full_name,
                'registration_number': student.registration_number or 'N/A',
                'gender': student.get_gender_display() or 'Not specified',
                'gender_code': student.gender,
                'has_results': has_results,
                'class_position': position_data.get('class_position'),
                'stream_position': position_data.get('stream_position'),
                'total_marks': total_marks if has_results else 'Absent',
                'average_marks': average_marks if has_results else 'Absent',
                'grade': grade or (division if division else 'N/A'),
                'division': division if division else 'N/A',
                'points': points if points else 'N/A',
                'subjects': subject_performance,
                'status': 'Active' if has_results else 'Absent'
            })
        
        # Sort by class position for ranking
        students_with_position = [s for s in students_data if s['class_position'] is not None]
        students_with_position.sort(key=lambda x: x['class_position'])
        
        # Get Top N and Bottom N performers
        top_performers = students_with_position[:top_n]
        bottom_performers = students_with_position[-bottom_n:] if len(students_with_position) >= bottom_n else students_with_position
        
        # Get students without results
        students_without_results = [s for s in students_data if not s['has_results']]
        
        # Calculate statistics
        stats = self._calculate_statistics(students_data, level_type, subject_objects, papers_by_subject)
        
        # Calculate gender x division/grade cross matrix
        cross_matrix = self._calculate_cross_matrix(students_data, level_type)
        
        # Get unique values for filters
        grades = []
        divisions = []
        if level_type in ['PRIMARY', 'NURSERY']:
            grades = sorted(set([s['grade'] for s in students_data if s['grade'] and s['grade'] != 'N/A']))
        else:
            divisions = sorted(set([s['division'] for s in students_data if s['division'] and s['division'] != 'N/A']))
        
        context = {
            'session': session,
            'level_type': level_type,
            'students': students_data,
            'top_performers': top_performers,
            'bottom_performers': bottom_performers,
            'students_without_results': students_without_results,
            'subjects': subject_objects,
            'papers_by_subject': papers_by_subject,
            'stats': stats,
            'cross_matrix': cross_matrix,
            'grades': grades,
            'divisions': divisions,
            'selected_grade': grade_filter,
            'selected_division': division_filter,
            'selected_gender': gender_filter,
            'search_query': search_query,
            'top_n': top_n,
            'bottom_n': bottom_n,
            'has_results': len(students_with_position) > 0,
            'total_students': len(students_data),
            'students_with_results': len(students_with_position),
            'students_absent': len(students_without_results),
        }
        
        return render(request, template_name, context)
    
    def _calculate_statistics(self, students_data, level_type, subjects, papers_by_subject):
        """Calculate overall statistics for the exam session"""
        
        students_with_results = [s for s in students_data if s['has_results']]
        
        if not students_with_results:
            return {
                'total_students': len(students_data),
                'students_with_results': 0,
                'students_absent': len([s for s in students_data if not s['has_results']]),
                'average_total_marks': 0,
                'highest_total_marks': 0,
                'lowest_total_marks': 0,
                'average_points': 0,
                'division_distribution': {},
                'grade_distribution': {},
                'gender_distribution': {},
                'subject_performance': []
            }
        
        # Calculate mark statistics
        total_marks_list = [float(s['total_marks']) for s in students_with_results if s['total_marks'] != 'Absent']
        avg_total = sum(total_marks_list) / len(total_marks_list) if total_marks_list else 0
        highest = max(total_marks_list) if total_marks_list else 0
        lowest = min(total_marks_list) if total_marks_list else 0
        
        # Points statistics
        points_list = [float(s['points']) for s in students_with_results if s['points'] != 'Absent' and s['points'] != 'N/A']
        avg_points = sum(points_list) / len(points_list) if points_list else 0
        
        # Division distribution
        division_dist = {}
        for student in students_with_results:
            division = student.get('division', 'N/A')
            if division != 'N/A':
                division_dist[division] = division_dist.get(division, 0) + 1
        
        # Grade distribution
        grade_dist = {}
        for student in students_with_results:
            grade = student.get('grade', 'N/A')
            if grade != 'N/A':
                grade_dist[grade] = grade_dist.get(grade, 0) + 1
        
        # Gender distribution
        gender_dist = {}
        for student in students_with_results:
            gender = student.get('gender', 'N/A')
            if gender != 'N/A':
                gender_dist[gender] = gender_dist.get(gender, 0) + 1
        
        # Subject performance comparison
        subject_performance = []
        for subject in subjects:
            subject_marks = []
            for student in students_with_results:
                for subj in student['subjects']:
                    if subj['subject_name'] == subject['name'] and subj['marks'] != 'Absent':
                        try:
                            subject_marks.append(float(subj['marks']))
                        except (ValueError, TypeError):
                            pass
            
            avg = sum(subject_marks) / len(subject_marks) if subject_marks else 0
            subject_performance.append({
                'subject_name': subject['name'],
                'subject_code': subject['code'],
                'average_marks': round(avg, 2),
                'total_students': len(subject_marks),
                'absent_count': len([s for s in students_with_results if any(
                    subj['subject_name'] == subject['name'] and subj['marks'] == 'Absent' 
                    for subj in s['subjects']
                )])
            })
        
        return {
            'total_students': len(students_data),
            'students_with_results': len(students_with_results),
            'students_absent': len([s for s in students_data if not s['has_results']]),
            'average_total_marks': round(avg_total, 2),
            'highest_total_marks': round(highest, 2),
            'lowest_total_marks': round(lowest, 2),
            'average_points': round(avg_points, 2),
            'division_distribution': division_dist,
            'grade_distribution': grade_dist,
            'gender_distribution': gender_dist,
            'subject_performance': subject_performance
        }
    
    def _calculate_cross_matrix(self, students_data, level_type):
        """Calculate gender x division/grade cross matrix"""
        
        cross_matrix = {
            'male': {},
            'female': {},
            'total': {}
        }
        
        for student in students_data:
            if not student['has_results']:
                continue
            
            gender = student['gender_code']
            if level_type in ['PRIMARY', 'NURSERY']:
                value = student['grade']
            else:
                value = student['division']
            
            if value == 'N/A':
                continue
            
            # Update gender-specific counts
            if gender not in cross_matrix:
                cross_matrix[gender] = {}
            cross_matrix[gender][value] = cross_matrix[gender].get(value, 0) + 1
            
            # Update total counts
            cross_matrix['total'][value] = cross_matrix['total'].get(value, 0) + 1
        
        return cross_matrix