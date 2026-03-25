# portal_management/views/student_academic_trend.py

import json
import logging
from datetime import date
from decimal import Decimal
from statistics import mean, median
from django.conf import settings
from django.db import models
from django.db.models import Avg, Max, Min, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.utils import timezone
from django.views.generic import View
from django.template.loader import render_to_string

from core.mixins import ManagementRequiredMixin
from core.models import (
    Student, ExamSession, StudentExamMetrics, StudentExamPosition,
    StudentSubjectResult, Subject, EducationalLevel, ClassLevel,
    StudentEnrollment, StudentStreamAssignment, GradingScale, DivisionScale
)

logger = logging.getLogger(__name__)


class StudentAcademicTrendView(ManagementRequiredMixin, View):
    """
    Display academic performance trend for a student across all exam sessions.
    Shows:
        - Performance overview with statistics
        - Trend chart of scores over time
        - Subject-wise performance analysis
        - Comparison with class averages
        - Performance by educational level
        - Grade progression visualization
    """
    template_name = 'portal_management/students/academic_trend.html'

    def get(self, request, student_pk):
        student = get_object_or_404(
            Student.objects.select_related('user'),
            pk=student_pk
        )
        
        # Get all exam sessions the student participated in
        exam_sessions = ExamSession.objects.filter(
            student_metrics__student=student
        ).select_related(
            'exam_type', 'academic_year', 'term', 
            'class_level__educational_level'
        ).order_by('exam_date')
        
        if not exam_sessions.exists():
            messages.info(request, f'No exam results found for {student.full_name}.')
            return render(request, self.template_name, {
                'student': student,
                'has_data': False,
                'exam_sessions': [],
            })
        
        # Get metrics for all sessions
        metrics = StudentExamMetrics.objects.filter(
            student=student,
            exam_session__in=exam_sessions
        ).select_related('exam_session')
        
        metrics_by_session = {m.exam_session_id: m for m in metrics}
        
        # Get positions
        positions = StudentExamPosition.objects.filter(
            student=student,
            exam_session__in=exam_sessions
        ).select_related('exam_session')
        
        positions_by_session = {p.exam_session_id: p for p in positions}
        
        # Get class averages for comparison
        class_averages = {}
        for session in exam_sessions:
            class_metrics = StudentExamMetrics.objects.filter(
                exam_session=session
            ).aggregate(
                avg_total=Avg('total_marks'),
                avg_average=Avg('average_marks'),
                highest=Max('total_marks'),
                lowest=Min('total_marks'),
                student_count=Count('id')
            )
            class_averages[session.pk] = class_metrics
        
        # Build session performance data for chart
        session_data = []
        for session in exam_sessions:
            metric = metrics_by_session.get(session.pk)
            position = positions_by_session.get(session.pk)
            class_avg = class_averages.get(session.pk, {})
            
            # Calculate performance vs class average
            vs_class_avg = None
            if metric and class_avg.get('avg_total'):
                diff = float(metric.total_marks) - float(class_avg['avg_total'])
                vs_class_avg = {
                    'difference': round(diff, 2),
                    'percentage_diff': round((diff / float(class_avg['avg_total']) * 100), 1) if class_avg['avg_total'] else 0,
                    'is_above': diff > 0,
                }
            
            session_data.append({
                'session': session,
                'metric': metric,
                'position': position,
                'class_average': class_avg.get('avg_total', 0),
                'class_average_percentage': class_avg.get('avg_average', 0),
                'vs_class_avg': vs_class_avg,
                'student_count': class_avg.get('student_count', 0),
            })
        
        # Get all subject results across sessions
        subject_results = StudentSubjectResult.objects.filter(
            student=student,
            exam_session__in=exam_sessions
        ).select_related('subject', 'exam_session')
        
        # Group by subject for subject-wise trend
        subjects_performance = {}
        for result in subject_results:
            subj_name = result.subject.name
            if subj_name not in subjects_performance:
                subjects_performance[subj_name] = {
                    'subject': result.subject,
                    'sessions': [],
                    'scores': [],
                    'grades': [],
                    'average': 0,
                    'trend': 'stable',
                }
            subjects_performance[subj_name]['sessions'].append({
                'session': result.exam_session,
                'marks': float(result.total_marks),
                'grade': result.grade,
                'percentage': None,  # Will calculate if we have max marks
            })
            subjects_performance[subj_name]['scores'].append(float(result.total_marks))
        
        # Calculate subject averages and trends
        for subj_name, data in subjects_performance.items():
            if data['scores']:
                data['average'] = round(mean(data['scores']), 2)
                # Determine trend (improving, declining, stable)
                if len(data['scores']) >= 2:
                    first_half = data['scores'][:len(data['scores'])//2]
                    second_half = data['scores'][len(data['scores'])//2:]
                    if mean(second_half) > mean(first_half) + 5:
                        data['trend'] = 'improving'
                    elif mean(second_half) < mean(first_half) - 5:
                        data['trend'] = 'declining'
                    else:
                        data['trend'] = 'stable'
        
        # Group by educational level
        level_performance = {}
        for session in exam_sessions:
            level_name = session.class_level.educational_level.name
            if level_name not in level_performance:
                level_performance[level_name] = {
                    'level': session.class_level.educational_level,
                    'sessions': [],
                    'scores': [],
                    'positions': [],
                }
            metric = metrics_by_session.get(session.pk)
            if metric:
                level_performance[level_name]['sessions'].append(session)
                level_performance[level_name]['scores'].append(float(metric.total_marks))
                pos = positions_by_session.get(session.pk)
                if pos:
                    level_performance[level_name]['positions'].append(pos.class_position)
        
        # Calculate level statistics
        for level_name, data in level_performance.items():
            if data['scores']:
                data['average_score'] = round(mean(data['scores']), 2)
                data['highest_score'] = max(data['scores'])
                data['lowest_score'] = min(data['scores'])
                data['session_count'] = len(data['sessions'])
            if data['positions']:
                data['best_position'] = min(data['positions'])
                data['average_position'] = round(mean(data['positions']), 1)
        
        # Calculate overall statistics
        all_scores = [float(m.total_marks) for m in metrics if m.total_marks]
        all_averages = [float(m.average_marks) for m in metrics if m.average_marks]
        all_positions = [p.class_position for p in positions if p.class_position]
        
        overall_stats = {
            'total_sessions': len(exam_sessions),
            'sessions_with_scores': len(all_scores),
            'average_score': round(mean(all_scores), 2) if all_scores else 0,
            'median_score': round(median(all_scores), 2) if all_scores else 0,
            'highest_score': max(all_scores) if all_scores else 0,
            'lowest_score': min(all_scores) if all_scores else 0,
            'average_percentage': round(mean(all_averages), 2) if all_averages else 0,
            'best_position': min(all_positions) if all_positions else None,
            'average_position': round(mean(all_positions), 2) if all_positions else None,
            'improvement_rate': self._calculate_improvement_rate(all_scores),
        }
        
        # Calculate grade distribution across all sessions
        grade_distribution = {}
        for result in subject_results:
            if result.grade:
                grade_distribution[result.grade] = grade_distribution.get(result.grade, 0) + 1
        
        # Get grading scale for reference
        educational_levels = EducationalLevel.objects.filter(
            class_levels__exam_sessions__student_metrics__student=student
        ).distinct()
        
        grading_scales = {}
        for level in educational_levels:
            scale = GradingScale.objects.filter(
                education_level=level
            ).order_by('-min_mark')
            if scale.exists():
                grading_scales[level.name] = scale
        
        # Prepare data for Chart.js
        chart_data = {
            'labels': [s['session'].exam_date.strftime('%b %Y') for s in session_data],
            'scores': [float(s['metric'].total_marks) if s['metric'] else None for s in session_data],
            'averages': [float(s['class_average']) for s in session_data],
            'percentages': [float(s['metric'].average_marks) if s['metric'] else None for s in session_data],
            'positions': [s['position'].class_position if s['position'] else None for s in session_data],
            'session_names': [s['session'].name[:30] for s in session_data],
            'session_ids': [s['session'].pk for s in session_data],
        }
        
        # Calculate subject performance for radar chart (top 6 subjects)
        top_subjects = sorted(
            subjects_performance.items(),
            key=lambda x: x[1]['average'],
            reverse=True
        )[:6]
        
        radar_chart_data = {
            'labels': [s[0] for s in top_subjects],
            'values': [s[1]['average'] for s in top_subjects],
        }
        
        # Get subject-wise class comparisons (best subject vs worst subject)
        best_subject = None
        worst_subject = None
        if subjects_performance:
            best_subject = max(subjects_performance.items(), key=lambda x: x[1]['average'])
            worst_subject = min(subjects_performance.items(), key=lambda x: x[1]['average'])
        
        # Get enrollment history for context
        enrollments = student.enrollments.select_related(
            'class_level__educational_level',
            'academic_year'
        ).order_by('-academic_year__start_date')
        
        context = {
            'student': student,
            'has_data': True,
            'session_data': session_data,
            'subjects_performance': subjects_performance,
            'level_performance': level_performance,
            'overall_stats': overall_stats,
            'grade_distribution': grade_distribution,
            'grading_scales': grading_scales,
            'chart_data': json.dumps(chart_data),
            'radar_chart_data': json.dumps(radar_chart_data),
            'best_subject': best_subject,
            'worst_subject': worst_subject,
            'enrollments': enrollments,
            'generated_date': timezone.now(),
        }
        
        return render(request, self.template_name, context)
    
    def _calculate_improvement_rate(self, scores):
        """Calculate improvement rate between first and last session."""
        if len(scores) < 2:
            return 0
        first_score = scores[0]
        last_score = scores[-1]
        if first_score == 0:
            return 0
        improvement = ((last_score - first_score) / first_score) * 100
        return round(improvement, 1)


# Optional: Export to PDF version
class ExportStudentAcademicTrendPDFView(ManagementRequiredMixin, View):
    """Export academic trend report to PDF."""
    
    def get(self, request, student_pk):
        student = get_object_or_404(Student, pk=student_pk)
        
        # Reuse the same data collection logic
        exam_sessions = ExamSession.objects.filter(
            student_metrics__student=student
        ).select_related(
            'exam_type', 'academic_year', 'term', 
            'class_level__educational_level'
        ).order_by('exam_date')
        
        if not exam_sessions.exists():
            messages.warning(request, f'No exam results found for {student.full_name}.')
            return redirect('management:student_academic_trend', student_pk=student_pk)
        
        metrics_by_session = {
            m.exam_session_id: m 
            for m in StudentExamMetrics.objects.filter(
                student=student, exam_session__in=exam_sessions
            )
        }
        
        positions_by_session = {
            p.exam_session_id: p 
            for p in StudentExamPosition.objects.filter(
                student=student, exam_session__in=exam_sessions
            )
        }
        
        # Prepare data for PDF
        session_data = []
        for session in exam_sessions:
            metric = metrics_by_session.get(session.pk)
            position = positions_by_session.get(session.pk)
            session_data.append({
                'session': session,
                'metric': metric,
                'position': position,
            })
        
        # Get school profile
        from core.models import SchoolProfile
        school_profile = SchoolProfile.objects.get_active_profile()
        
        context = {
            'student': student,
            'session_data': session_data,
            'school_info': {
                'name': school_profile.name if school_profile else getattr(settings, 'SCHOOL_NAME', 'School Management System'),
                'address': school_profile.address if school_profile else '',
                'phone': school_profile.get_contact_phone() if school_profile else '',
                'email': school_profile.email if school_profile else '',
                'motto': school_profile.motto if school_profile else '',
            },
            'generated_date': timezone.now(),
        }
        
        html_string = render_to_string('portal_management/students/academic_trend_pdf.html', context)
        
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
        
        font_config = FontConfiguration()
        
        response = HttpResponse(content_type='application/pdf')
        filename = f"academic_trend_{student.registration_number}_{date.today()}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        try:
            HTML(string=html_string).write_pdf(
                response,
                font_config=font_config,
                presentational_hints=True,
            )
            return response
        except Exception as e:
            logger.error(f'PDF generation error: {e}', exc_info=True)
            messages.error(request, f'Error generating PDF: {str(e)}')
            return redirect('management:student_academic_trend', student_pk=student_pk)