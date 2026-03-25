# views.py - Exam Result Analytics View (Fixed Combination Filter)

from django.views import View
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Avg, Count, Sum, F, FloatField, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from decimal import Decimal
import json
import logging
from core.models import (
    ExamSession, StudentEnrollment, Student, StudentExamMetrics,
    StudentExamPosition, StudentSubjectResult, StudentPaperScore,
    SubjectExamPaper, EducationalLevel, StudentStreamAssignment, Subject,
    GradingScale, DivisionScale, Combination, StudentCombinationAssignment
)

logger = logging.getLogger(__name__)


class ExamResultAnalyticsView(LoginRequiredMixin, View):
    """
    Comprehensive exam result analytics view with educational level specific templates.
    Routes to different templates based on educational level.
    """

    # -------------------------------------------------------------------------
    # Grading helpers
    # -------------------------------------------------------------------------

    def _build_grading_scale(self, educational_level):
        """
        Return a list of GradingScale rows for *educational_level*, ordered
        from highest to lowest min_mark so the first match wins.
        """
        return list(
            GradingScale.objects.filter(education_level=educational_level)
            .order_by('-min_mark')
        )

    def _grade_from_average(self, average, grading_scale):
        """
        Look up the grade for *average* (0-100 percentage) from the pre-built
        grading_scale list.  Returns 'N/A' when no band matches.
        """
        for gs in grading_scale:
            if float(gs.min_mark) <= average <= float(gs.max_mark):
                return gs.grade
        return 'N/A'

    def _points_from_grade(self, grade, grading_scale):
        """Return the point value for a grade from the grading scale."""
        for gs in grading_scale:
            if gs.grade == grade:
                return float(gs.points)
        return 0.0

    # -------------------------------------------------------------------------
    # Division scale helpers
    # -------------------------------------------------------------------------

    def _build_division_scale(self, educational_level):
        """
        Return an ordered dict  {division_label: DivisionScale}  for the level
        (O-Level / A-Level only).  For Primary / Nursery returns {}.
        """
        qs = DivisionScale.objects.filter(
            education_level=educational_level
        ).order_by('min_points')
        return {ds.division: ds for ds in qs}

    def _all_division_labels(self, division_scale):
        """
        Return every division label defined for this level, in the display
        order: I, II, III, IV, 0.  Falls back to sorted dict keys when the
        standard sequence is not applicable.
        """
        standard_order = ['I', 'II', 'III', 'IV', '0']
        defined = set(division_scale.keys())
        ordered = [d for d in standard_order if d in defined]
        ordered += sorted(defined - set(ordered))
        return ordered

    # -------------------------------------------------------------------------
    # Subject helpers
    # -------------------------------------------------------------------------

    def _compute_subject_average(self, paper_scores):
        """
        Given a list of paper score dicts for ONE subject for ONE student,
        return the percentage average (0-100) of the raw scores scaled to
        each paper's max_marks, or 0 when there are no papers.

        Formula: (sum of marks / sum of max_marks) * 100
        """
        if not paper_scores:
            return 0.0
        total_marks = sum(p['marks'] for p in paper_scores)
        total_max = sum(p['max_marks'] for p in paper_scores)
        return (total_marks / total_max * 100) if total_max > 0 else 0.0

    # -------------------------------------------------------------------------
    # Combination helpers for A-Level
    # -------------------------------------------------------------------------

    def _get_student_combination(self, student_id, academic_year):
        """
        Get the active combination for an A-Level student in a given academic year.
        Returns the combination object or None if not assigned.
        """
        try:
            assignment = StudentCombinationAssignment.objects.filter(
                student_id=student_id,
                enrollment__academic_year=academic_year,
                is_active=True
            ).select_related('combination').first()
            return assignment.combination if assignment else None
        except Exception:
            return None

    def _get_all_combinations(self, educational_level):
        """
        Get all combinations for A-Level educational level.
        """
        if educational_level.level_type == 'A_LEVEL':
            return list(Combination.objects.filter(
                educational_level=educational_level
            ).order_by('code'))
        return []

    # -------------------------------------------------------------------------
    # Main GET handler
    # -------------------------------------------------------------------------

    def get(self, request, pk):
        # Get exam session
        session = get_object_or_404(ExamSession, pk=pk)

        # Educational level metadata
        educational_level = session.class_level.educational_level
        level_type = educational_level.level_type

        # Template routing
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

        # Filter parameters
        top_n = int(request.GET.get('top_n', 10))
        bottom_n = int(request.GET.get('bottom_n', 10))
        grade_filter = request.GET.get('grade', '')
        division_filter = request.GET.get('division', '')
        search_query = request.GET.get('search', '')
        gender_filter = request.GET.get('gender', '')
        combination_filter = request.GET.get('combination', '')

        # ------------------------------------------------------------------
        # Pre-load grading & division scales (single DB round-trip each)
        # ------------------------------------------------------------------
        grading_scale = self._build_grading_scale(educational_level)
        division_scale = self._build_division_scale(educational_level)
        all_divisions = self._all_division_labels(division_scale)

        # ------------------------------------------------------------------
        # ALL subjects for this educational level — ensures subjects with
        # no exam papers / no results still appear in every student row and
        # in the subject-comparison analytics table.
        # ------------------------------------------------------------------
        all_level_subjects = list(
            Subject.objects.filter(
                educational_level=educational_level
            ).order_by('name')
        )
        
        all_level_subject_objects = [
            {
                'id': subj.id,
                'name': subj.name,
                'short_name': subj.short_name or subj.name[:15],
                'code': subj.code,
            }
            for subj in all_level_subjects
        ]

        # ------------------------------------------------------------------
        # Get all combinations for A-Level
        # ------------------------------------------------------------------
        combinations = self._get_all_combinations(educational_level)

        # ------------------------------------------------------------------
        # Enrolled students
        # ------------------------------------------------------------------
        enrolled_students_qs = StudentEnrollment.objects.filter(
            academic_year=session.academic_year,
            class_level=session.class_level,
            status='active'
        ).select_related('student', 'student__user')

        if session.stream_class:
            enrolled_students_qs = enrolled_students_qs.filter(
                stream_assignment__stream_class=session.stream_class
            )

        enrolled_students = enrolled_students_qs.order_by(
            'student__first_name', 'student__last_name'
        )

        # ------------------------------------------------------------------
        # Position data
        # ------------------------------------------------------------------
        positions_qs = StudentExamPosition.objects.filter(exam_session=session)
        positions = {
            pos.student_id: {
                'class_position': pos.class_position,
                'stream_position': pos.stream_position,
            }
            for pos in positions_qs
        }

        # ------------------------------------------------------------------
        # Metrics data  (total marks, average, points, division)
        # ------------------------------------------------------------------
        metrics_qs = StudentExamMetrics.objects.filter(exam_session=session)
        metrics_data = {
            metric.student_id: {
                'total_marks': metric.total_marks,
                'average_marks': metric.average_marks,
                'total_points': metric.total_points,
                'division': metric.division,
                'remarks': metric.remarks,
            }
            for metric in metrics_qs
        }

        # ------------------------------------------------------------------
        # Exam papers defined for this session, organised by subject
        # ------------------------------------------------------------------
        session_papers = SubjectExamPaper.objects.filter(
            exam_session=session
        ).select_related('subject').order_by('subject__name', 'paper_number')
        
        papers_by_subject = {}
        for paper in session_papers:
            sid = paper.subject_id
            if sid not in papers_by_subject:
                papers_by_subject[sid] = {'subject': paper.subject, 'papers': []}
            papers_by_subject[sid]['papers'].append({
                'paper_number': paper.paper_number,
                'paper_name': paper.paper_name,
                'max_marks': float(paper.max_marks),
            })

        # ------------------------------------------------------------------
        # Paper scores for every student in this session
        # student_paper_scores[student_id][subject_id] = [
        #     {paper_number, marks, max_marks}, ...
        # ]
        # ------------------------------------------------------------------
        paper_scores_qs = StudentPaperScore.objects.filter(
            exam_paper__exam_session=session
        ).select_related('exam_paper', 'exam_paper__subject')
        
        student_paper_scores = {}
        for score in paper_scores_qs:
            student_id = score.student_id
            subject_id = score.exam_paper.subject_id
            
            student_paper_scores.setdefault(student_id, {})
            student_paper_scores[student_id].setdefault(subject_id, [])
            student_paper_scores[student_id][subject_id].append({
                'paper_number': score.exam_paper.paper_number,
                'marks': float(score.marks),
                'max_marks': float(score.exam_paper.max_marks),
            })

        # ------------------------------------------------------------------
        # Existing StudentSubjectResult rows  (used as a fallback for grade /
        # points when no paper scores are present and for remarks)
        # ------------------------------------------------------------------
        subject_results_qs = StudentSubjectResult.objects.filter(
            exam_session=session
        ).select_related('student', 'subject')
        
        subject_results_map = {}
        for result in subject_results_qs:
            subject_results_map[(result.student_id, result.subject_id)] = result

        # ------------------------------------------------------------------
        # Build per-student analytics data
        # ------------------------------------------------------------------
        students_data = []

        for enrollment in enrolled_students:
            student = enrollment.student
            student_id = student.pk

            # Gender filter
            if gender_filter and student.gender != gender_filter:
                continue

            position_data = positions.get(student_id, {})
            metrics = metrics_data.get(student_id, {})
            papers_scores = student_paper_scores.get(student_id, {})
            
            # Check if student has ANY subject results or metrics
            has_metrics = student_id in metrics_data
            has_paper_scores = len(papers_scores) > 0
            has_subject_results = any((student_id, subj['id']) in subject_results_map for subj in all_level_subject_objects)
            
            # A student has results if they have ANY of these
            has_results = has_metrics or has_paper_scores or has_subject_results

            # Get student combination for A-Level
            combination_obj = None
            combination_code = None
            if level_type == 'A_LEVEL':
                combination_obj = self._get_student_combination(student_id, session.academic_year)
                combination_code = combination_obj.code if combination_obj else None
                
                # Apply combination filter - compare by ID
                if combination_filter:
                    if combination_obj:
                        if str(combination_obj.id) != combination_filter:
                            continue
                    else:
                        # Filter expects a combination but student has none
                        continue

            # --------------------------------------------------------------
            # Build subject performance list covering ALL level subjects
            # --------------------------------------------------------------
            subject_performance = []

            for subject in all_level_subject_objects:
                subj_id = subject['id']
                subj_papers = papers_scores.get(subj_id, [])
                db_result = subject_results_map.get((student_id, subj_id))

                has_paper_scores_for_subject = len(subj_papers) > 0
                has_exam_papers_for_subject = subj_id in papers_by_subject
                has_db_result = db_result is not None

                # -- Compute average from paper scores ----------------------
                if has_paper_scores_for_subject:
                    subject_average = self._compute_subject_average(subj_papers)
                    computed_grade = self._grade_from_average(
                        subject_average, grading_scale
                    )
                    computed_points = self._points_from_grade(
                        computed_grade, grading_scale
                    )
                    subject_marks = round(subject_average, 2)
                elif has_db_result:
                    # Fallback: use persisted result (legacy / imported data)
                    subject_average = float(db_result.total_marks)
                    computed_grade = db_result.grade
                    computed_points = float(db_result.points) if db_result.points is not None else 0.0
                    subject_marks = subject_average
                else:
                    subject_average = 0.0
                    computed_grade = None
                    computed_points = 0.0
                    subject_marks = None

                # -- Determine display values --------------------------------
                if not has_results:
                    display_grade = 'Absent'
                    display_marks = 'Absent'
                    display_points = 'Absent'
                elif not has_exam_papers_for_subject:
                    # Subject exists on the level but has no paper for this session
                    display_grade = 'N/A'
                    display_marks = 'N/A'
                    display_points = 'N/A'
                elif not has_paper_scores_for_subject and not has_db_result:
                    # Paper defined but student has no score entered
                    display_grade = 'N/A'
                    display_marks = 'N/A'
                    display_points = 'N/A'
                else:
                    display_grade = computed_grade or 'N/A'
                    display_marks = round(subject_average, 2) if subject_average is not None else 'N/A'
                    display_points = computed_points

                if level_type in ['PRIMARY', 'NURSERY']:
                    subject_performance.append({
                        'subject_name': subject['name'],
                        'subject_code': subject['code'],
                        'grade': display_grade,
                        'marks': display_marks,
                        'average': round(subject_average, 2),
                        'papers': subj_papers,
                        'has_papers': has_exam_papers_for_subject,
                    })
                else:
                    subject_performance.append({
                        'subject_name': subject['name'],
                        'subject_code': subject['code'],
                        'grade': display_grade,
                        'points': display_points,
                        'marks': display_marks,
                        'average': round(subject_average, 2),
                        'papers': subj_papers,
                        'has_papers': has_exam_papers_for_subject,
                    })

            # --------------------------------------------------------------
            # Overall student figures
            # --------------------------------------------------------------
            if has_metrics:
                total_marks = metrics.get('total_marks', 0)
                average_marks = metrics.get('average_marks', 0)
                division = metrics.get('division', '')
                points = metrics.get('total_points', '')
            elif has_paper_scores or has_subject_results:
                # Calculate from subject scores
                subject_scores = []
                for subj in subject_performance:
                    if subj['marks'] not in ('Absent', 'N/A'):
                        try:
                            subject_scores.append(float(subj['marks']))
                        except (ValueError, TypeError):
                            pass
                
                if subject_scores:
                    total_marks = sum(subject_scores)
                    average_marks = total_marks / len(subject_scores) if subject_scores else 0
                    division = ''
                    points = ''
                else:
                    total_marks = 0
                    average_marks = 0
                    division = ''
                    points = ''
            else:
                total_marks = 0
                average_marks = 0
                division = ''
                points = ''

            # Derive overall grade (Primary / Nursery) from subject averages
            grade = None
            if level_type in ['PRIMARY', 'NURSERY'] and has_results:
                subject_averages = [
                    s['average']
                    for s in subject_performance
                    if s['marks'] not in ('Absent', 'N/A') and s['average'] > 0
                ]
                if subject_averages:
                    overall_avg = sum(subject_averages) / len(subject_averages)
                    grade = self._grade_from_average(overall_avg, grading_scale)

            # Apply filters
            if grade_filter and level_type in ['PRIMARY', 'NURSERY']:
                if grade != grade_filter:
                    continue

            if division_filter and level_type in ['O_LEVEL', 'A_LEVEL']:
                if division != division_filter:
                    continue

            if search_query:
                if not (
                    search_query.lower() in student.full_name.lower()
                    or search_query.lower() in (student.registration_number or '').lower()
                ):
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
                'combination': combination_code,  # Store the code for display
                'combination_id': combination_obj.id if combination_obj else None,  # Store ID for reference
                'subjects': subject_performance,
                'status': 'Active' if has_results else 'Absent',
            })

        # ------------------------------------------------------------------
        # Sort & slice top / bottom performers
        # ------------------------------------------------------------------
        students_with_position = [
            s for s in students_data if s['class_position'] is not None
        ]
        students_with_position.sort(key=lambda x: x['class_position'])

        top_performers = students_with_position[:top_n]
        bottom_performers = (
            students_with_position[-bottom_n:]
            if len(students_with_position) >= bottom_n
            else students_with_position
        )
        students_without_results = [s for s in students_data if not s['has_results']]

        # ------------------------------------------------------------------
        # Statistics & cross matrix
        # ------------------------------------------------------------------
        stats = self._calculate_statistics(
            students_data, level_type,
            all_level_subject_objects, papers_by_subject,
            grading_scale, all_divisions
        )

        cross_matrix = self._calculate_cross_matrix(
            students_data, level_type, all_divisions
        )

        # ------------------------------------------------------------------
        # Filter option lists — always include all defined divisions/grades
        # ------------------------------------------------------------------
        if level_type in ['PRIMARY', 'NURSERY']:
            grades = [gs.grade for gs in sorted(
                grading_scale, key=lambda g: g.min_mark, reverse=True
            )]
            divisions = []
        else:
            grades = []
            divisions = all_divisions

        # Add combination filter list for A-Level
        combination_list = [{'id': str(c.id), 'code': c.code, 'name': c.code} for c in combinations] if combinations else []

        context = {
            'session': session,
            'level_type': level_type,
            'students': students_data,
            'top_performers': top_performers,
            'bottom_performers': bottom_performers,
            'students_without_results': students_without_results,
            'subjects': all_level_subject_objects,
            'papers_by_subject': papers_by_subject,
            'stats': stats,
            'cross_matrix': cross_matrix,
            'grades': grades,
            'divisions': divisions,
            'all_divisions': all_divisions,
            'combinations': combination_list,  # Add combinations for A-Level filter
            'selected_grade': grade_filter,
            'selected_division': division_filter,
            'selected_gender': gender_filter,
            'selected_combination': combination_filter,  # Add selected combination
            'search_query': search_query,
            'top_n': top_n,
            'bottom_n': bottom_n,
            'has_results': len(students_with_position) > 0,
            'total_students': len(students_data),
            'students_with_results': len(students_with_position),
            'students_absent': len(students_without_results),
        }

        return render(request, template_name, context)

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def _calculate_statistics(
        self, students_data, level_type,
        subjects, papers_by_subject,
        grading_scale, all_divisions
    ):
        """Calculate overall statistics for the exam session."""
        
        students_with_results = [s for s in students_data if s['has_results']]

        # Empty-state skeleton
        empty_division_dist = {d: 0 for d in all_divisions}
        if not students_with_results:
            return {
                'total_students': len(students_data),
                'students_with_results': 0,
                'students_absent': len([s for s in students_data if not s['has_results']]),
                'average_total_marks': 0,
                'highest_total_marks': 0,
                'lowest_total_marks': 0,
                'average_points': 0,
                'division_distribution': empty_division_dist,
                'grade_distribution': {},  # Empty dict for grade distribution
                'gender_distribution': {},
                'subject_performance': self._empty_subject_performance(subjects),
            }

        # Mark totals
        total_marks_list = [
            float(s['total_marks'])
            for s in students_with_results
            if s['total_marks'] != 'Absent' and s['total_marks'] is not None
        ]
        avg_total = sum(total_marks_list) / len(total_marks_list) if total_marks_list else 0
        highest = max(total_marks_list) if total_marks_list else 0
        lowest = min(total_marks_list) if total_marks_list else 0

        # Points
        points_list = [
            float(s['points'])
            for s in students_with_results
            if s['points'] not in ('Absent', 'N/A') and s['points'] is not None
        ]
        avg_points = sum(points_list) / len(points_list) if points_list else 0

        # Division distribution — ALWAYS include all defined divisions with
        # zero counts so the template never has to guess which ones exist.
        division_dist = {d: 0 for d in all_divisions}
        for student in students_with_results:
            div = student.get('division', 'N/A')
            if div != 'N/A' and div in division_dist:
                division_dist[div] += 1
            elif div != 'N/A':
                division_dist[div] = division_dist.get(div, 0) + 1

        # Grade distribution
        grade_dist = {}
        for student in students_with_results:
            g = student.get('grade', 'N/A')
            if g != 'N/A':
                grade_dist[g] = grade_dist.get(g, 0) + 1

        # Gender distribution
        gender_dist = {}
        for student in students_with_results:
            gender = student.get('gender', 'N/A')
            if gender != 'N/A':
                gender_dist[gender] = gender_dist.get(gender, 0) + 1

        # Subject performance comparison — ALL subjects always included;
        # subjects with no scores get zeros, not omitted.
        subject_performance = []
        for subject in subjects:
            subject_averages = []
            absent_count = 0
            no_paper_count = 0

            for student in students_with_results:
                for subj in student['subjects']:
                    if subj['subject_name'] != subject['name']:
                        continue
                    if subj['marks'] == 'Absent':
                        absent_count += 1
                    elif subj['marks'] == 'N/A':
                        no_paper_count += 1
                    else:
                        try:
                            subject_averages.append(float(subj['average']))
                        except (ValueError, TypeError):
                            pass

            avg = (
                sum(subject_averages) / len(subject_averages)
                if subject_averages else 0
            )

            # Grade distribution per subject
            subj_grade_dist = {}
            for student in students_with_results:
                for subj in student['subjects']:
                    if subj['subject_name'] != subject['name']:
                        continue
                    g = subj.get('grade', 'N/A')
                    if g not in ('N/A', 'Absent'):
                        subj_grade_dist[g] = subj_grade_dist.get(g, 0) + 1

            has_papers_in_session = subject['id'] in papers_by_subject

            subject_performance.append({
                'subject_name': subject['name'],
                'subject_code': subject['code'],
                'average_marks': round(avg, 2),
                'total_students': len(subject_averages),
                'absent_count': absent_count,
                'no_paper_count': no_paper_count,
                'grade_distribution': subj_grade_dist,
                'has_papers': has_papers_in_session,
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
            'subject_performance': subject_performance,
        }

    def _empty_subject_performance(self, subjects):
        """Return zeroed subject_performance rows when no results exist."""
        return [
            {
                'subject_name': s['name'],
                'subject_code': s['code'],
                'average_marks': 0,
                'total_students': 0,
                'absent_count': 0,
                'no_paper_count': 0,
                'grade_distribution': {},
                'has_papers': False,
            }
            for s in subjects
        ]

    # -------------------------------------------------------------------------
    # Cross matrix
    # -------------------------------------------------------------------------

    def _calculate_cross_matrix(self, students_data, level_type, all_divisions):
        """
        Calculate gender × division/grade cross matrix.

        For O-Level / A-Level every defined division always appears as a column
        (with zero counts where appropriate) so the template never renders
        an incomplete table.
        """
        cross_matrix = {
            'male': {},
            'female': {},
            'total': {},
        }

        # Seed all division slots with zeros for O/A-Level
        if level_type in ['O_LEVEL', 'A_LEVEL']:
            for d in all_divisions:
                cross_matrix['male'][d] = 0
                cross_matrix['female'][d] = 0
                cross_matrix['total'][d] = 0

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

            # Per-gender bucket
            if gender not in cross_matrix:
                cross_matrix[gender] = {}
            cross_matrix[gender][value] = cross_matrix[gender].get(value, 0) + 1

            # Total bucket
            cross_matrix['total'][value] = cross_matrix['total'].get(value, 0) + 1

        return cross_matrix