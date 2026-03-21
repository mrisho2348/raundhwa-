# portal_management/urls/exams.py

from django.urls import path
from portal_management.views.exam_views import (
    # Exam Type URLs
    ExamTypeListView, ExamTypeCreateView, ExamTypeUpdateView, 
    ExamTypeDeleteView, ExamTypeSearchView,
    # Exam Session URLs
    ExamSessionListView, ExamSessionCreateView, ExamSessionDetailView,
    ExamSessionUpdateView, ExamSessionDeleteView,
    # Result Calculation URLs
    CalculateSubjectResultsView, CalculateMetricsView, CalculatePositionsView,
    CalculateFullResultsView, PublishExamSessionView, ExportSessionReportView, TermsByAcademicYearView,
)

urlpatterns = [
    # Exam Types
    path('exam-types/', ExamTypeListView.as_view(), name='exam_type_list'),
    path('exam-types/create/', ExamTypeCreateView.as_view(), name='exam_type_create'),
    path('exam-types/<int:pk>/update/', ExamTypeUpdateView.as_view(), name='exam_type_update'),
    path('exam-types/<int:pk>/delete/', ExamTypeDeleteView.as_view(), name='exam_type_delete'),
    path('exam-types/search/', ExamTypeSearchView.as_view(), name='exam_type_search'),
    
    # Exam Sessions
    path('exam-sessions/', ExamSessionListView.as_view(), name='exam_session_list'),
    path('exam-sessions/create/', ExamSessionCreateView.as_view(), name='exam_session_create'),
    path('exam-sessions/<int:pk>/', ExamSessionDetailView.as_view(), name='exam_session_detail'),
    path('exam-sessions/<int:pk>/update/', ExamSessionUpdateView.as_view(), name='exam_session_update'),
    path('exam-sessions/<int:pk>/delete/', ExamSessionDeleteView.as_view(), name='exam_session_delete'),
    path('api/terms-by-academic-year/', TermsByAcademicYearView.as_view(), name='terms_by_academic_year'),
    # Result Calculation
    path('exam-sessions/<int:pk>/calculate-subject-results/', CalculateSubjectResultsView.as_view(), name='calculate_subject_results'),
    path('exam-sessions/<int:pk>/calculate-metrics/', CalculateMetricsView.as_view(), name='calculate_metrics'),
    path('exam-sessions/<int:pk>/calculate-positions/', CalculatePositionsView.as_view(), name='calculate_positions'),
    path('exam-sessions/<int:pk>/calculate-full-results/', CalculateFullResultsView.as_view(), name='calculate_full_results'),
    path('exam-sessions/<int:pk>/publish/', PublishExamSessionView.as_view(), name='publish_exam_session'),
    path('exam-sessions/<int:pk>/export/', ExportSessionReportView.as_view(), name='export_session_report'),
]