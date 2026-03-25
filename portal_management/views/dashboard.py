"""
portal_management/views/dashboard.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Management portal main dashboard view with comprehensive statistics.
"""
from django.db.models import Count, Sum, Avg, Q, OuterRef, Subquery, Exists
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView
from datetime import datetime, timedelta

from core.mixins import ManagementRequiredMixin
from core.models import (
    AcademicYear, AuditLog, ClassLevel, Combination, Department,
    EducationalLevel, ExamSession, ExamType, GradingScale,
    Staff, StaffRole, StaffSession, Student, StudentEnrollment, 
    StudentExamMetrics, StudentPaperScore, StudentSubjectResult, 
    Subject, SubjectExamPaper, Term,
)


class DashboardView(ManagementRequiredMixin, TemplateView):
    """Enhanced admin dashboard with comprehensive school statistics."""
    template_name = 'portal_management/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # ============================================
        # BASIC COUNTS
        # ============================================
        ctx['total_students'] = Student.objects.filter(status='active').count()
        ctx['total_students_all'] = Student.objects.count()
        ctx['total_staff'] = Staff.objects.count()
        ctx['total_classes'] = ClassLevel.objects.count()
        ctx['total_subjects'] = Subject.objects.count()
        ctx['online_users'] = StaffSession.objects.filter(is_online=True).count()
        
        # ============================================
        # STUDENT DEMOGRAPHICS
        # ============================================
        ctx['male_students'] = Student.objects.filter(gender='male', status='active').count()
        ctx['female_students'] = Student.objects.filter(gender='female', status='active').count()
        ctx['students_by_status'] = {
            'active': Student.objects.filter(status='active').count(),
            'suspended': Student.objects.filter(status='suspended').count(),
            'withdrawn': Student.objects.filter(status='withdrawn').count(),
            'completed': Student.objects.filter(status='completed').count(),
            'transferred': Student.objects.filter(status='transferred').count(),
        }
        
        # Students by educational level
        students_by_level = {}
        for level in EducationalLevel.objects.all():
            count = StudentEnrollment.objects.filter(
                class_level__educational_level=level,
                status='active',
                academic_year__is_active=True
            ).values('student').distinct().count()
            students_by_level[level.name] = count
        ctx['students_by_level'] = students_by_level
        
        # Students by class level (top 5)
        class_enrollments = StudentEnrollment.objects.filter(
            status='active',
            academic_year__is_active=True
        ).values('class_level__name').annotate(
            count=Count('student', distinct=True)
        ).order_by('-count')[:5]
        ctx['class_enrollments'] = class_enrollments
        
        # ============================================
        # EXAMINATION STATISTICS
        # ============================================
        ctx['total_exam_sessions'] = ExamSession.objects.count()
        ctx['total_exam_sessions_published'] = ExamSession.objects.filter(status='published').count()
        ctx['total_exam_papers'] = SubjectExamPaper.objects.count()
        ctx['total_exam_papers_with_scores'] = SubjectExamPaper.objects.filter(
            student_scores__isnull=False
        ).distinct().count()
        
        # Results completion rate
        total_results = StudentSubjectResult.objects.count()
        ctx['total_results'] = total_results
        
        # Recent exam sessions
        ctx['recent_exam_sessions'] = ExamSession.objects.select_related(
            'exam_type', 'class_level', 'academic_year', 'term'
        ).order_by('-exam_date')[:5]
        
        # Performance overview
        ctx['overall_avg_score'] = StudentExamMetrics.objects.aggregate(
            avg=Avg('average_marks')
        )['avg'] or 0
        
        # Top performing subjects (by average score)
        subject_performance = StudentSubjectResult.objects.values(
            'subject__name'
        ).annotate(
            avg_score=Avg('total_marks'),
            total_students=Count('student', distinct=True)
        ).order_by('-avg_score')[:5]
        ctx['top_subjects'] = subject_performance
        
        # Grade distribution across all exams
        grade_distribution = StudentSubjectResult.objects.values('grade').annotate(
            count=Count('id')
        ).order_by('grade')
        ctx['grade_distribution'] = {g['grade']: g['count'] for g in grade_distribution if g['grade']}
        
        # ============================================
        # STAFF STATISTICS
        # ============================================
        # Staff by role
        try:
            ctx['staff_by_role'] = StaffRole.objects.annotate(
                staff_count=Count('staff_assignments', filter=Q(staff_assignments__is_active=True))
            ).order_by('-staff_count')[:5]
        except:
            ctx['staff_by_role'] = []
        
        # Department distribution
        ctx['staff_by_department'] = Department.objects.annotate(
            staff_count=Count('staff_assignments', filter=Q(staff_assignments__is_active=True))
        ).order_by('-staff_count')[:5]
        
        ctx['teaching_staff'] = Staff.objects.filter(teaching_assignments__isnull=False).distinct().count()
        
        # ============================================
        # ACADEMIC YEAR & TERM
        # ============================================
        ctx['active_year'] = AcademicYear.objects.filter(is_active=True).first()
        ctx['active_term'] = None
        if ctx['active_year']:
            ctx['active_term'] = ctx['active_year'].terms.filter(is_active=True).first()
        
        # Upcoming terms
        ctx['upcoming_terms'] = Term.objects.filter(
            start_date__gt=timezone.now().date()
        ).select_related('academic_year').order_by('start_date')[:3]
        
        # Academic years summary
        ctx['academic_years_summary'] = AcademicYear.objects.annotate(
            student_count=Count('student_enrollments', distinct=True),
            exam_count=Count('exam_sessions')
        ).order_by('-start_date')[:5]
        
        # ============================================
        # ENROLLMENT TRENDS
        # ============================================
        # Enrollment over last 6 months
        six_months_ago = timezone.now().date() - timedelta(days=180)
        enrollment_trend = Student.objects.filter(
            admission_date__gte=six_months_ago
        ).annotate(
            month=TruncMonth('admission_date')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('month')
        ctx['enrollment_trend'] = list(enrollment_trend)
        
        # ============================================
        # AUDIT & ACTIVITY
        # ============================================
        ctx['recent_audit'] = AuditLog.objects.select_related(
            'user', 'content_type'
        ).order_by('-timestamp')[:10]
        
        # Activity summary (last 24 hours)
        yesterday = timezone.now() - timedelta(days=1)
        ctx['activity_24h'] = AuditLog.objects.filter(timestamp__gte=yesterday).count()
        
        # Activity by type
        ctx['activity_by_type'] = AuditLog.objects.filter(
            timestamp__gte=yesterday
        ).values('action').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # ============================================
        # SYSTEM HEALTH
        # ============================================
        ctx['grading_scales_configured'] = GradingScale.objects.count()
        ctx['exam_types_configured'] = ExamType.objects.count()
        ctx['combinations_configured'] = Combination.objects.count()
        ctx['educational_levels'] = EducationalLevel.objects.count()
        
        # Data completeness - Fixed: Students without metrics in active enrollment
        # Get students who have active enrollments but no exam metrics
        active_students_with_enrollment = Student.objects.filter(
            status='active',
            enrollments__status='active',
            enrollments__academic_year__is_active=True
        ).distinct()
        
        students_with_metrics = StudentExamMetrics.objects.filter(
            student__in=active_students_with_enrollment
        ).values_list('student', flat=True).distinct()
        
        ctx['students_without_metrics'] = active_students_with_enrollment.exclude(
            id__in=students_with_metrics
        ).count()
        
        # ============================================
        # QUICK LINKS & ALERTS
        # ============================================
        # Upcoming exams (next 30 days)
        next_30_days = timezone.now().date() + timedelta(days=30)
        ctx['upcoming_exams'] = ExamSession.objects.filter(
            exam_date__gte=timezone.now().date(),
            exam_date__lte=next_30_days,
            status__in=['draft', 'submitted']
        ).select_related('class_level', 'exam_type').order_by('exam_date')[:5]
        
        # Students without scores in recent exams - Fixed
        # Get students who have enrolled in sessions but have no paper scores
        # First, get all exam sessions
        exam_sessions = ExamSession.objects.filter(
            academic_year__is_active=True
        ).values_list('id', flat=True)
        
        # Get students who have enrollments in active academic year
        enrolled_students = StudentEnrollment.objects.filter(
            academic_year__is_active=True,
            status='active'
        ).values_list('student', flat=True).distinct()
        
        # Get students who have paper scores
        students_with_scores = StudentPaperScore.objects.filter(
            exam_paper__exam_session__academic_year__is_active=True
        ).values_list('student', flat=True).distinct()
        
        # Students without scores are those enrolled but no scores
        ctx['students_without_scores_count'] = Student.objects.filter(
            id__in=enrolled_students
        ).exclude(
            id__in=students_with_scores
        ).count()
        
        # Pending exam sessions
        ctx['pending_sessions'] = ExamSession.objects.filter(
            status__in=['draft', 'submitted']
        ).count()
        
        return ctx