"""results/views.py"""
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from core.models import ExamSession, Student, StudentEnrollment
from .services import calculate_session_results
from .utils import export_student_report, export_session_report

logger = logging.getLogger(__name__)


@login_required
def calculate_results(request, session_id):
    """
    Trigger full result calculation pipeline for an exam session.
    Only accessible via POST to prevent accidental recalculation.
    Redirects back to the exam session detail page after completion.
    """
    if request.method != 'POST':
        return redirect('management:exam_session_list')

    session = get_object_or_404(ExamSession, pk=session_id)

    try:
        summary = calculate_session_results(session_id)
        messages.success(
            request,
            f'Results calculated successfully for "{session.name}". '
            f'Subject results: {summary["subject_results"]["created"] + summary["subject_results"]["updated"]}, '
            f'Metrics: {summary["metrics"]["created"] + summary["metrics"]["updated"]}, '
            f'Positions: {summary["positions"]["class_positions"]}.'
        )
    except Exception as exc:
        logger.error('Result calculation failed for session %s: %s', session_id, exc, exc_info=True)
        messages.error(request, f'Calculation failed: {exc}')

    return redirect('management:exam_session_detail', pk=session_id)


@login_required
def export_student_report(request, student_id):
    """Export a student's results across all sessions as Excel."""
    student = get_object_or_404(Student, pk=student_id)

    # Get all exam sessions the student has results for
    from core.models import StudentSubjectResult
    session_ids = StudentSubjectResult.objects.filter(
        student=student
    ).values_list('exam_session_id', flat=True).distinct()

    sessions = ExamSession.objects.filter(pk__in=session_ids).order_by('exam_date')

    wb = export_student_report(student, sessions)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"results_{student.registration_number or student_id}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def export_session_report(request, session_id):
    """Export all student results for an exam session as Excel."""
    session = get_object_or_404(ExamSession, pk=session_id)
    wb = export_session_report(session)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"session_{session_id}_{session.name[:30]}.xlsx".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
