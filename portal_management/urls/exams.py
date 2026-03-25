# portal_management/urls/exams.py

from django.urls import path
from portal_management.views.exam_result_analytics import ExamResultAnalyticsView
from portal_management.views.exam_views import (
    # Exam Type URLs
    BulkExamPaperCreateSubmitView, BulkExamPaperCreateView, BulkPaperResultEntryView, BulkPaperResultSaveView, BulkSaveScoresView,   ExamTypeListView, ExamTypeCreateView, ExamTypeUpdateView, 
    ExamTypeDeleteView, ExamTypeSearchView,
    # Exam Session URLs
    ExamSessionListView, ExamSessionCreateView, ExamSessionDetailView,
    ExamSessionUpdateView, ExamSessionDeleteView,
    # Result Calculation URLs
    CalculateSubjectResultsView, CalculateMetricsView, CalculatePositionsView,
    CalculateFullResultsView, ExportSubjectAnalyticsPDFView, ExportSubjectReportView,  ExportSubjectResultsPDFView, GetPapersForSubjectView, PaperAnalyticsView, PaperResultsFilterView, PublishSessionView, QuickScoreSaveView, SavePaperScoreView, SessionResultsView, StudentResultEntryView, SubjectAnalyticsView, SubjectExamPaperCreateView, SubjectExamPaperDeleteView, SubjectExamPaperDetailView, SubjectExamPaperListView, SubjectExamPaperReorderView, SubjectExamPaperUpdateView, SubjectResultsSummaryView, SubmitSessionView, TermsByAcademicYearView, UnpublishSessionView,  VerifySessionView,
)
from portal_management.views.export_result_analytics import ExportResultAnalyticsView
from portal_management.views.export_subject_results_excel_view import ExportSubjectResultsExcelView
from portal_management.views.paper_excel import BulkExcelUploadView, DownloadPaperTemplateView
from portal_management.views.result_download import DownloadResultTemplateView
from portal_management.views.result_upload import UploadResultsView
from portal_management.views.session_export_views import ExportSessionReportView

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
    # path('exam-sessions/<int:pk>/publish/', PublishExamSessionView.as_view(), name='publish_exam_session'),
    path('exam-sessions/<int:pk>/export/', ExportSessionReportView.as_view(), name='export_session_report'),

    # ══════════════════════════════════════════════════════════════════════
    # RESULT ENTRY
    # ══════════════════════════════════════════════════════════════════════
 
    # Full session grid  (all students × all papers)
    path('exams/sessions/<int:pk>/results/',SessionResultsView.as_view(),name='session_results',),
    
    # Per-student entry  (one student, all subjects × papers)
    path('exams/sessions/<int:session_pk>/results/student/<int:student_pk>/',StudentResultEntryView.as_view(),name='student_result_entry',),
    # AJAX — save single paper score
    path('exams/results/save-score/',SavePaperScoreView.as_view(),name='save_paper_score', ),
    # AJAX — bulk save all scores for one student
    path('exams/results/bulk-save/',BulkSaveScoresView.as_view(),name='bulk_save_scores',
    ),
 
    # ══════════════════════════════════════════════════════════════════════
    # EXCEL UPLOAD / DOWNLOAD
    # ══════════════════════════════════════════════════════════════════════
 
    # Download template
    # ?mode=full           → all subjects × all papers
    # ?mode=subject&subject_id=N → one subject
    # ?mode=prefilled      → include existing scores
    path('exams/sessions/<int:session_pk>/template/download/',DownloadResultTemplateView.as_view(),name='download_result_template',),
    # Upload filled template
    path('exams/sessions/<int:session_pk>/template/upload/',UploadResultsView.as_view(),name='upload_results',),
    # ══════════════════════════════════════════════════════════════════════
    # WORKFLOW
    # ══════════════════════════════════════════════════════════════════════
    path('exams/sessions/<int:pk>/submit/',SubmitSessionView.as_view(),name='exam_session_submit',),
    path('exams/sessions/<int:pk>/verify/',VerifySessionView.as_view(),name='exam_session_verify',),
    path('exams/sessions/<int:pk>/publish/',PublishSessionView.as_view(),name='exam_session_publish',),
    path('exams/sessions/<int:pk>/unpublish/',UnpublishSessionView.as_view(),name='exam_session_unpublish',),
 
    # ══════════════════════════════════════════════════════════════════════
    # EXPORT
    # ══════════════════════════════════════════════════════════════════════
    path('exams/sessions/<int:pk>/export/',ExportSessionReportView.as_view(),name='export_session_report',),
    path('exams/sessions/<int:session_pk>/export/subject/<int:subject_pk>/',ExportSubjectReportView.as_view(),name='export_subject_report',),
    path('exam-papers/<int:paper_pk>/results-filter/',  PaperResultsFilterView.as_view(),  name='paper_results_filter'),
    # Exam Paper URLs
    path('exam-sessions/<int:session_pk>/papers/', SubjectExamPaperListView.as_view(), name='exam_paper_list'),
    
    path('exam-sessions/<int:session_pk>/papers/create/', SubjectExamPaperCreateView.as_view(), name='exam_paper_create'),
    
    path('exam-papers/<int:pk>/',  SubjectExamPaperDetailView.as_view(), name='exam_paper_detail'),
    
    path('exam-papers/<int:pk>/update/',  SubjectExamPaperUpdateView.as_view(), name='exam_paper_update'),
    
    path('exam-papers/<int:pk>/delete/', SubjectExamPaperDeleteView.as_view(), name='exam_paper_delete'),
    
    path('exam-sessions/<int:session_pk>/papers/bulk-create/',  BulkExamPaperCreateView.as_view(), name='exam_paper_bulk_create'),
    path('exam-sessions/<int:session_pk>/papers/bulk-create-submit/',  BulkExamPaperCreateSubmitView.as_view(), name='exam_paper_bulk_create_submit'),
    
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/papers/reorder/',    SubjectExamPaperReorderView.as_view(), name='exam_paper_reorder'),
    
    # AJAX endpoints
    path('ajax/papers/by-subject/<int:session_pk>/<int:subject_pk>/',    GetPapersForSubjectView.as_view(), name='ajax_papers_by_subject'),

        # Bulk Result Entry URLs
    # Bulk Result Entry URLs
    path('exam-papers/<int:paper_pk>/results/bulk/',  BulkPaperResultEntryView.as_view(), name='bulk_paper_result_entry'),    
    path('exam-papers/<int:paper_pk>/results/bulk-save/', BulkPaperResultSaveView.as_view(), name='bulk_paper_result_save'),    
    path('exam-papers/results/quick-save/', QuickScoreSaveView.as_view(), name='quick_score_save'),    
    path('exam-papers/<int:paper_pk>/upload-excel/',  BulkExcelUploadView.as_view(), name='bulk_excel_upload'),    
    path('exam-papers/<int:paper_pk>/download-template/', DownloadPaperTemplateView.as_view(), name='download_paper_template'),
    # Add to urlpatterns
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/results/',SubjectResultsSummaryView.as_view(), name='subject_results_summary'),    # Add these to urlpatterns
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/results/excel/', ExportSubjectResultsExcelView.as_view(), name='export_subject_results_excel'),
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/results/pdf/', ExportSubjectResultsPDFView.as_view(), name='export_subject_results_pdf'),
    # Paper Analytics
    path('exam-papers/<int:paper_pk>/analytics/', PaperAnalyticsView.as_view(), name='paper_analytics'),
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/analytics/', SubjectAnalyticsView.as_view(), name='subject_analytics'),
    # Subject Analytics Export PDF
    path('exam-sessions/<int:session_pk>/subjects/<int:subject_pk>/analytics/export/', ExportSubjectAnalyticsPDFView.as_view(), name='subject_analytics_export'),
    path('exam-sessions/<int:pk>/analytics/', ExamResultAnalyticsView.as_view(), name='exam_result_analytics'),
     path('exam-sessions/<int:pk>/analytics/export/', ExportResultAnalyticsView.as_view(), name='export_result_analytics'),
]