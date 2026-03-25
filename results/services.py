"""
results/services.py
═══════════════════
Single authoritative service for all result computation.

Design principles:
  - NO signals. Computation is triggered explicitly, never per-row.
  - All data for an exam session is loaded in a fixed small number of
    bulk queries regardless of student count.
  - Every public function is safe to call multiple times (idempotent).
  - All writes are atomic — a partial failure leaves the database clean.
  - level_type (not code) is used for education-level branching.

Public API
──────────
  calculate_session_results(exam_session_id)
      Full pipeline: subject results → metrics → positions.
      Call this once after a bulk upload completes.

  calculate_subject_results(exam_session_id)
      Step 1 — aggregate paper scores into StudentSubjectResult rows.

  calculate_metrics(exam_session_id)
      Step 2 — compute totals / division from StudentSubjectResult rows.

  calculate_positions(exam_session_id)
      Step 3 — rank students by total_points (O/A-Level) or
               average_marks (Primary/Nursery).
"""

import logging
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Sum

from core.models import CombinationSubject, DivisionScale, ExamSession, GradingScale, StudentEnrollment, StudentExamMetrics, StudentExamPosition, StudentPaperScore, StudentStreamAssignment, StudentSubjectResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_grading_scale(education_level):
    """
    Return grading scale as a list of dicts sorted descending by min_mark.
    Loaded once per call and passed around — never re-queried per student.
    """

    return list(
        GradingScale.objects
        .filter(education_level=education_level)
        .order_by('-min_mark')
        .values('grade', 'min_mark', 'max_mark', 'points')
    )


def _load_division_scale(education_level):
    """
    Return division scale as a list of dicts sorted ascending by min_points.
    Only applicable to O_LEVEL and A_LEVEL.
    """
  
    return list(
        DivisionScale.objects
        .filter(education_level=education_level)
        .order_by('min_points')
        .values('division', 'min_points', 'max_points')
    )


def _resolve_grade(total_marks, grading_scale):
    """
    Resolve grade and points from a pre-loaded grading scale list.
    Returns (grade, points) or ('F', Decimal('0')) if no band matches.
    """
    for band in grading_scale:
        if band['min_mark'] <= total_marks <= band['max_mark']:
            return band['grade'], band['points']
    return 'F', Decimal('0')


def _resolve_division(total_points, division_scale):
    """
    Resolve division string from a pre-loaded division scale list.
    Returns division string or '0' if no band matches.
    """
    points_int = int(total_points)
    for band in division_scale:
        if band['min_points'] <= points_int <= band['max_points']:
            return band['division']
    return '0'


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Aggregate paper scores → StudentSubjectResult
# ─────────────────────────────────────────────────────────────────────────────

def calculate_subject_results(exam_session_id: int) -> dict:
    """
    For every student × subject combination in the exam session,
    sum all paper scores and resolve grade + points from GradingScale.

    Query budget: O(1) queries regardless of student/subject count.

    Returns a summary dict:
        {'created': int, 'updated': int, 'skipped': int}
    """
 

    session = (
        ExamSession.objects
        .select_related(
            'class_level__educational_level',
            'academic_year',
        )
        .get(pk=exam_session_id)
    )
    education_level = session.class_level.educational_level
    grading_scale = _load_grading_scale(education_level)

    if not grading_scale:
        logger.warning(
            "No grading scale configured for '%s' — "
            "subject results cannot be calculated for session %s.",
            education_level, exam_session_id,
        )
        return {'created': 0, 'updated': 0, 'skipped': 0}

    # Load all paper scores for this session in ONE query
    # exam_paper__exam_session filter scopes to only this session's papers
    paper_scores = (
        StudentPaperScore.objects
        .filter(exam_paper__exam_session=session)
        .select_related('exam_paper__subject')
        .values(
            'student_id',
            'exam_paper__subject_id',
            'exam_paper__subject__name',
            'marks',
        )
    )

    # Aggregate: student × subject → total marks
    # Using Python aggregation avoids a GROUP BY query per student
    totals: dict[tuple, Decimal] = defaultdict(Decimal)
    for row in paper_scores:
        key = (row['student_id'], row['exam_paper__subject_id'])
        totals[key] += row['marks']

    if not totals:
        logger.info("No paper scores found for session %s.", exam_session_id)
        return {'created': 0, 'updated': 0, 'skipped': 0}

    # Load existing StudentSubjectResult rows for this session in ONE query
    existing = {
        (r.student_id, r.subject_id): r
        for r in StudentSubjectResult.objects.filter(exam_session=session)
    }

    to_create = []
    to_update = []

    for (student_id, subject_id), total_marks in totals.items():
        grade, points = _resolve_grade(total_marks, grading_scale)
        key = (student_id, subject_id)

        if key in existing:
            obj = existing[key]
            obj.total_marks = total_marks
            obj.grade = grade
            obj.points = points
            to_update.append(obj)
        else:
            to_create.append(StudentSubjectResult(
                student_id=student_id,
                exam_session=session,
                subject_id=subject_id,
                total_marks=total_marks,
                grade=grade,
                points=points,
            ))

    with transaction.atomic():
        if to_create:
            StudentSubjectResult.objects.bulk_create(to_create)
        if to_update:
            StudentSubjectResult.objects.bulk_update(
                to_update, ['total_marks', 'grade', 'points']
            )

    summary = {
        'created': len(to_create),
        'updated': len(to_update),
        'skipped': 0,
    }
    logger.info(
        "Session %s subject results — created: %d, updated: %d.",
        exam_session_id, summary['created'], summary['updated'],
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Compute metrics → StudentExamMetrics
# ─────────────────────────────────────────────────────────────────────────────

def calculate_metrics(exam_session_id: int) -> dict:
    """
    From StudentSubjectResult rows, compute per-student metrics and write
    to StudentExamMetrics.

    O-Level  — best 7 subjects by points (ascending = better in Tanzania).
               Minimum 7 subjects required; students with fewer get no metrics.
    A-Level  — best 3 core + best 1 subsidiary from student's combination.
               Minimum 3 core subjects required.
    Primary /
    Nursery  — average_marks only; no points or division.

    Query budget: O(1) queries regardless of student count.

    Returns {'created': int, 'updated': int, 'skipped': int}
    """


    session = (
        ExamSession.objects
        .select_related(
            'class_level__educational_level',
            'academic_year',
        )
        .get(pk=exam_session_id)
    )
    education_level = session.class_level.educational_level
    level_type = education_level.level_type

    division_scale = (
        _load_division_scale(education_level)
        if level_type in ('O_LEVEL', 'A_LEVEL')
        else []
    )

    # Load ALL subject results for this session in ONE query
    all_results = list(
        StudentSubjectResult.objects
        .filter(exam_session=session)
        .values('student_id', 'subject_id', 'total_marks', 'points')
    )

    if not all_results:
        logger.info("No subject results found for session %s.", exam_session_id)
        return {'created': 0, 'updated': 0, 'skipped': 0}

    # Group by student
    by_student: dict[int, list] = defaultdict(list)
    for row in all_results:
        by_student[row['student_id']].append(row)

    # For A-Level — load combination subjects per student in ONE query
    # Maps student_id → {'core': set(subject_ids), 'subsidiary': set(subject_ids)}
    combination_map: dict[int, dict] = {}
    if level_type == 'A_LEVEL':
        enrollments = (
            StudentEnrollment.objects
            .filter(
                student_id__in=by_student.keys(),
                academic_year=session.academic_year,
            )
            .select_related('combination')
            .values('student_id', 'combination_id')
        )
        combination_ids = {
            e['student_id']: e['combination_id']
            for e in enrollments
            if e['combination_id']
        }
        # Load all relevant CombinationSubject rows in ONE query
        combo_subjects = CombinationSubject.objects.filter(
            combination_id__in=set(combination_ids.values())
        ).values('combination_id', 'subject_id', 'role')

        combo_detail: dict[int, dict] = defaultdict(
            lambda: {'core': set(), 'subsidiary': set()}
        )
        for cs in combo_subjects:
            role_key = 'core' if cs['role'] == 'CORE' else 'subsidiary'
            combo_detail[cs['combination_id']][role_key].add(cs['subject_id'])

        for student_id, combo_id in combination_ids.items():
            combination_map[student_id] = combo_detail[combo_id]

    # Load existing metrics in ONE query
    existing_metrics = {
        m.student_id: m
        for m in StudentExamMetrics.objects.filter(exam_session=session)
    }

    to_create = []
    to_update = []
    skipped = 0

    for student_id, results in by_student.items():
        metrics_data = _compute_student_metrics(
            student_id=student_id,
            results=results,
            level_type=level_type,
            division_scale=division_scale,
            combination_info=combination_map.get(student_id),
        )

        if metrics_data is None:
            # Not enough subjects — do not write metrics
            skipped += 1
            continue

        if student_id in existing_metrics:
            obj = existing_metrics[student_id]
            obj.total_marks = metrics_data['total_marks']
            obj.average_marks = metrics_data['average_marks']
            obj.total_points = metrics_data['total_points']
            obj.division = metrics_data['division']
            to_update.append(obj)
        else:
            to_create.append(StudentExamMetrics(
                student_id=student_id,
                exam_session=session,
                **metrics_data,
            ))

    with transaction.atomic():
        if to_create:
            StudentExamMetrics.objects.bulk_create(to_create)
        if to_update:
            StudentExamMetrics.objects.bulk_update(
                to_update,
                ['total_marks', 'average_marks', 'total_points', 'division'],
            )
        # Remove stale metrics for students whose results were deleted
        # or who no longer have enough subjects
        stale_student_ids = set(existing_metrics.keys()) - set(by_student.keys())
        if stale_student_ids:
            StudentExamMetrics.objects.filter(
                exam_session=session,
                student_id__in=stale_student_ids,
            ).delete()

    summary = {
        'created': len(to_create),
        'updated': len(to_update),
        'skipped': skipped,
    }
    logger.info(
        "Session %s metrics — created: %d, updated: %d, skipped: %d.",
        exam_session_id, summary['created'], summary['updated'], summary['skipped'],
    )
    return summary


def _compute_student_metrics(
    student_id: int,
    results: list,
    level_type: str,
    division_scale: list,
    combination_info: dict | None,
) -> dict | None:
    """
    Compute metrics dict for a single student from pre-loaded data.
    Returns None if the student does not meet the minimum subject threshold.

    Never hits the database — all data is pre-loaded by the caller.
    """
    if level_type == 'O_LEVEL':
        return _compute_o_level_metrics(results, division_scale)

    elif level_type == 'A_LEVEL':
        return _compute_a_level_metrics(results, division_scale, combination_info)

    else:
        # PRIMARY and NURSERY — marks-based only, no points or division
        return _compute_primary_metrics(results)


def _compute_o_level_metrics(results: list, division_scale: list) -> dict | None:
    """
    O-Level: best 7 subjects by points (lowest points = best in Tanzania).
    Requires at least 7 subjects with valid points.
    """
    subjects_with_points = [
        (r['subject_id'], Decimal(str(r['points'])))
        for r in results
        if r['points'] is not None
    ]

    if len(subjects_with_points) < 7:
        return None

    # Sort ascending — lowest points first (best performance)
    subjects_with_points.sort(key=lambda x: x[1])
    best_7 = subjects_with_points[:7]
    total_points = sum(p for _, p in best_7)

    # Total and average marks across ALL subjects (not just best 7)
    all_marks = [Decimal(str(r['total_marks'])) for r in results]
    total_marks = sum(all_marks)
    average_marks = total_marks / len(all_marks)

    division = _resolve_division(total_points, division_scale)

    return {
        'total_marks': total_marks,
        'average_marks': average_marks.quantize(Decimal('0.01')),
        'total_points': total_points,
        'division': division,
    }


def _compute_a_level_metrics(
    results: list,
    division_scale: list,
    combination_info: dict | None,
) -> dict | None:
    """
    A-Level: best 3 core + best 1 subsidiary from student's combination.
    Requires at least 3 core subjects with valid points.
    """
    if not combination_info:
        return None

    core_ids = combination_info.get('core', set())
    subsidiary_ids = combination_info.get('subsidiary', set())

    core_points = sorted(
        [Decimal(str(r['points'])) for r in results
         if r['subject_id'] in core_ids and r['points'] is not None]
    )  # ascending = best first for A-Level too

    if len(core_points) < 3:
        return None

    total_points = sum(core_points[:3])

    subsidiary_points = sorted(
        [Decimal(str(r['points'])) for r in results
         if r['subject_id'] in subsidiary_ids and r['points'] is not None]
    )
    if subsidiary_points:
        total_points += subsidiary_points[0]

    all_marks = [Decimal(str(r['total_marks'])) for r in results]
    total_marks = sum(all_marks)
    average_marks = total_marks / len(all_marks)

    division = _resolve_division(total_points, division_scale)

    return {
        'total_marks': total_marks,
        'average_marks': average_marks.quantize(Decimal('0.01')),
        'total_points': total_points,
        'division': division,
    }


def _compute_primary_metrics(results: list) -> dict | None:
    """
    Primary/Nursery: simple average of marks. No points, no division.
    """
    marks = [Decimal(str(r['total_marks'])) for r in results if r['total_marks'] is not None]
    if not marks:
        return None

    total_marks = sum(marks)
    average_marks = total_marks / len(marks)

    return {
        'total_marks': total_marks,
        'average_marks': average_marks.quantize(Decimal('0.01')),
        'total_points': Decimal('0'),
        'division': '',
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Compute positions → StudentExamPosition
# ─────────────────────────────────────────────────────────────────────────────

def calculate_positions(exam_session_id: int) -> dict:
    """
    Rank all students in the session and write to StudentExamPosition.

    Ranking key:
      O/A-Level  — total_points ascending (lower = better), then
                   average_marks descending as tie-breaker, then
                   registration_number ascending as final tie-breaker.
      Primary /
      Nursery    — average_marks descending, then registration_number.

    Stream positions are also calculated where students have a stream
    assignment. Each stream is ranked independently.

    No duplicate positions — every student gets a unique position.
    Query budget: O(1) queries regardless of student count.

    Returns {'class_positions': int, 'stream_positions': int}
    """


    session = (
        ExamSession.objects
        .select_related('class_level__educational_level')
        .get(pk=exam_session_id)
    )
    level_type = session.class_level.educational_level.level_type
    use_points = level_type in ('O_LEVEL', 'A_LEVEL')

    # Load all metrics + student registration numbers in ONE query
    metrics_qs = (
        StudentExamMetrics.objects
        .filter(exam_session=session)
        .select_related('student')
        .values(
            'student_id',
            'total_points',
            'average_marks',
            'student__registration_number',
        )
    )
    metrics_list = list(metrics_qs)

    if not metrics_list:
        StudentExamPosition.objects.filter(exam_session=session).delete()
        return {'class_positions': 0, 'stream_positions': 0}

    # Sort for class ranking
    if use_points:
        # Lower points = better for O/A-Level
        metrics_list.sort(key=lambda m: (
            float(m['total_points'] or 9999),           # ascending
            -float(m['average_marks'] or 0),            # descending tie-breaker
            m['student__registration_number'] or '',    # ascending final tie-breaker
        ))
    else:
        # Higher average = better for Primary/Nursery
        metrics_list.sort(key=lambda m: (
            -float(m['average_marks'] or 0),
            m['student__registration_number'] or '',
        ))

    # Assign unique class positions
    class_position_map: dict[int, int] = {
        m['student_id']: rank
        for rank, m in enumerate(metrics_list, start=1)
    }

    # Load stream assignments for all students in ONE query
    # Maps student_id → stream_class_id
    stream_map: dict[int, int] = dict(
        StudentStreamAssignment.objects
        .filter(
            enrollment__student_id__in=class_position_map.keys(),
            enrollment__academic_year=session.academic_year,
        )
        .values_list('enrollment__student_id', 'stream_class_id')
    )

    # Group metrics by stream for stream-level ranking
    by_stream: dict[int, list] = defaultdict(list)
    for m in metrics_list:
        sid = m['student_id']
        if sid in stream_map:
            by_stream[stream_map[sid]].append(m)

    # Assign stream positions within each stream (same sort order)
    stream_position_map: dict[int, int] = {}
    for stream_id, stream_metrics in by_stream.items():
        # Already sorted in class order — stream order follows same criteria
        for rank, m in enumerate(stream_metrics, start=1):
            stream_position_map[m['student_id']] = rank

    # Load existing position rows in ONE query
    existing_positions = {
        p.student_id: p
        for p in StudentExamPosition.objects.filter(exam_session=session)
    }

    to_create = []
    to_update = []
    all_student_ids = set(class_position_map.keys())

    for student_id in all_student_ids:
        class_pos = class_position_map.get(student_id)
        stream_pos = stream_position_map.get(student_id)

        if student_id in existing_positions:
            obj = existing_positions[student_id]
            obj.class_position = class_pos
            obj.stream_position = stream_pos
            to_update.append(obj)
        else:
            to_create.append(StudentExamPosition(
                student_id=student_id,
                exam_session=session,
                class_position=class_pos,
                stream_position=stream_pos,
            ))

    with transaction.atomic():
        if to_create:
            StudentExamPosition.objects.bulk_create(to_create)
        if to_update:
            StudentExamPosition.objects.bulk_update(
                to_update, ['class_position', 'stream_position']
            )
        # Remove positions for students who no longer have metrics
        stale = set(existing_positions.keys()) - all_student_ids
        if stale:
            StudentExamPosition.objects.filter(
                exam_session=session,
                student_id__in=stale,
            ).delete()

    stream_count = len(stream_position_map)
    logger.info(
        "Session %s positions — class: %d, stream: %d.",
        exam_session_id, len(class_position_map), stream_count,
    )
    return {
        'class_positions': len(class_position_map),
        'stream_positions': stream_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline — call this after bulk upload
# ─────────────────────────────────────────────────────────────────────────────

def calculate_session_results(exam_session_id: int) -> dict:
    """
    Full three-step pipeline for one exam session.

    Step 1 — Paper scores → StudentSubjectResult
    Step 2 — Subject results → StudentExamMetrics
    Step 3 — Metrics → StudentExamPosition

    All three steps run inside a single atomic transaction so either
    everything succeeds or nothing is committed.

    Returns a combined summary dict from all three steps.
    """
    logger.info("Starting full result calculation for session %s.", exam_session_id)

    with transaction.atomic():
        step1 = calculate_subject_results(exam_session_id)
        step2 = calculate_metrics(exam_session_id)
        step3 = calculate_positions(exam_session_id)

    summary = {
        'subject_results': step1,
        'metrics': step2,
        'positions': step3,
    }
    logger.info(
        "Session %s calculation complete: %s", exam_session_id, summary
    )
    return summary


def bulk_calculate_sessions(exam_session_ids: list[int]) -> list[dict]:
    """
    Run the full pipeline for multiple exam sessions sequentially.
    Each session is atomic independently — a failure in one does not
    roll back others.

    Returns a list of result dicts, one per session.
    """
    results = []
    for session_id in exam_session_ids:
        try:
            summary = calculate_session_results(session_id)
            results.append({'exam_session_id': session_id, 'success': True, **summary})
        except Exception as exc:
            logger.error(
                "Failed to calculate results for session %s: %s",
                session_id, exc, exc_info=True,
            )
            results.append({
                'exam_session_id': session_id,
                'success': False,
                'error': str(exc),
            })
    return results
