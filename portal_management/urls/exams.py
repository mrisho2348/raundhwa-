"""
portal_management/urls/exams.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Examination and grading URL patterns.

Covers:
  - Exam types
  - Exam sessions
  - Subject exam papers
  - Grading scales
  - Division scales
  - Publish session
"""
from django.urls import path
from portal_management.views.exams import (
    DivisionScaleCreateView,
    DivisionScaleDeleteView,
    ExamSessionCreateView,
    ExamSessionDetailView,
    ExamSessionListView,
    ExamSessionPublishView,
    ExamSessionUpdateView,
    ExamTypeCreateView,
    ExamTypeListView,
    ExamTypeUpdateView,
    GradingScaleCreateView,
    GradingScaleDeleteView,
    GradingScaleListView,
    SubjectExamPaperCreateView,
    SubjectExamPaperDeleteView,
)
app_name = 'management'
urlpatterns = [
    # ── Exam Types ────────────────────────────────────────────────────────────
    path(
        'exams/types/',
        ExamTypeListView.as_view(),
        name='exam_type_list',
    ),
    path(
        'exams/types/create/',
        ExamTypeCreateView.as_view(),
        name='exam_type_create',
    ),
    path(
        'exams/types/<int:pk>/edit/',
        ExamTypeUpdateView.as_view(),
        name='exam_type_update',
    ),

    # ── Exam Sessions ─────────────────────────────────────────────────────────
    path(
        'exams/sessions/',
        ExamSessionListView.as_view(),
        name='exam_session_list',
    ),
    path(
        'exams/sessions/create/',
        ExamSessionCreateView.as_view(),
        name='exam_session_create',
    ),
    path(
        'exams/sessions/<int:pk>/',
        ExamSessionDetailView.as_view(),
        name='exam_session_detail',
    ),
    path(
        'exams/sessions/<int:pk>/edit/',
        ExamSessionUpdateView.as_view(),
        name='exam_session_update',
    ),
    path(
        'exams/sessions/<int:pk>/publish/',
        ExamSessionPublishView.as_view(),
        name='exam_session_publish',
    ),

    # ── Subject Exam Papers ───────────────────────────────────────────────────
    path(
        'exams/sessions/<int:session_pk>/papers/add/',
        SubjectExamPaperCreateView.as_view(),
        name='exam_paper_create',
    ),
    path(
        'exams/papers/<int:pk>/delete/',
        SubjectExamPaperDeleteView.as_view(),
        name='exam_paper_delete',
    ),

    # ── Grading Scales ────────────────────────────────────────────────────────
    path(
        'exams/grading/',
        GradingScaleListView.as_view(),
        name='grading_scale_list',
    ),
    path(
        'exams/grading/create/',
        GradingScaleCreateView.as_view(),
        name='grading_scale_create',
    ),
    path(
        'exams/grading/<int:pk>/delete/',
        GradingScaleDeleteView.as_view(),
        name='grading_scale_delete',
    ),

    # ── Division Scales ───────────────────────────────────────────────────────
    path(
        'exams/division/create/',
        DivisionScaleCreateView.as_view(),
        name='division_scale_create',
    ),
    path(
        'exams/division/<int:pk>/delete/',
        DivisionScaleDeleteView.as_view(),
        name='division_scale_delete',
    ),
]