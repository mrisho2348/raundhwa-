"""
portal_management/urls/academics.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Academic structure URL patterns.

Covers:
  - Educational levels
  - Academic years and terms
  - Departments
  - Class levels and streams
  - Subjects
  - Combinations and combination subjects
"""
from django.urls import path
from portal_management.views.academics import *
from portal_management.views.departments import *

app_name = 'management'
urlpatterns = [
    # ── Educational Levels ────────────────────────────────────────────────────
    path('academic/levels/',EducationalLevelListView.as_view(),  name='educational_level_list',  ),
    path('levels/crud/', EducationalLevelCRUDView.as_view(), name='admin_educational_levels_crud'),
   path('academic/subjects/crud/', SubjectCRUDView.as_view(), name='subject_crud'),
   path('academic/subjects/<int:pk>/students/', SubjectStudentsView.as_view(), name='subject_students'),
   
    
    path('academic/subjects/<int:pk>/bulk-assign/', SubjectBulkAssignView.as_view(), name='subject_bulk_assign'),    
    path('academic/subjects/<int:pk>/bulk-remove/', SubjectBulkRemoveView.as_view(), name='subject_bulk_remove'),    
    path('academic/subjects/<int:pk>/available-students/', GetAvailableStudentsView.as_view(), name='get_available_students'),
    # Student Subject Assignments (O-Level Electives)
    path('academic/student-subject-assignments/', StudentSubjectAssignmentListView.as_view(), name='student_subject_assignments'),    
    path('academic/student-subject-assignments/crud/', StudentSubjectAssignmentCRUDView.as_view(), name='student_subject_assignment_crud'),
    
    # AJAX endpoints for dependent dropdowns
    path('academic/ajax/get-student-enrollments/', GetStudentEnrollmentsView.as_view(),name='get_student_enrollments'),    
    path('academic/ajax/get-available-subjects/', GetAvailableSubjectsView.as_view(), name='get_available_subjects'),    
    path('academic/ajax/get-students-by-filters/', GetStudentsByFiltersView.as_view(), name='get_students_by_filters'),
     # Level-specific views
     path('levels/<int:pk>/subjects/', LevelSubjectsView.as_view(), name='level_subjects',),
     path('levels/<int:pk>/classes/', LevelClassesView.as_view(), name='level_classes',),
     path('levels/<int:pk>/students/',LevelStudentsView.as_view(), name='level_students',),  
   
     # Academic Year Terms
    path('academic/years/<int:pk>/terms/', AcademicYearTermsView.as_view(), name='academic_year_terms'),
    
    # Term CRUD
    path('academic/terms/crud/', TermCRUDView.as_view(), name='term_crud'),    
    path('academic/terms/<int:pk>/details/', GetTermDetailsView.as_view(), name='get_term_details'),    
    path('academic/terms/set-active/', SetActiveTermView.as_view(), name='set_active_term'),
 # Academic Years
    path('academic/years/', AcademicYearListView.as_view(), name='academic_year_list'),    
    path('academic/years/crud/', AcademicYearCRUDView.as_view(), name='academic_year_crud'),    
    path('academic/years/set-active/', SetActiveAcademicYearView.as_view(), name='set_active_academic_year'),    
    path('academic/years/<int:pk>/details/', GetAcademicYearDetailsView.as_view(), name='get_academic_year_details'),



    # ── Class Levels ──────────────────────────────────────────────────────────
    path('academic/classes/',ClassLevelListView.as_view(),name='class_level_list',),
     # Class Levels
    path('academic/classes/', ClassLevelListView.as_view(), name='class_level_list'),    
    path('academic/classes/crud/', ClassLevelCRUDView.as_view(), name='class_level_crud'),    
    path('academic/classes/<int:pk>/details/',GetClassLevelDetailsView.as_view(), name='get_class_level_details'),    
    path('academic/classes/<int:pk>/streams/', ClassStreamsView.as_view(), name='class_streams'),

    # Streams
    path('academic/classes/<int:pk>/streams/', ClassStreamsView.as_view(),  name='class_streams'),    
    path('academic/streams/crud/', StreamClassCRUDView.as_view(), name='stream_crud'),    
    path('academic/streams/<int:pk>/details/', GetStreamDetailsView.as_view(), name='get_stream_details'), 


     # Stream Students
    path('academic/streams/<int:pk>/students/', StreamStudentsView.as_view(), name='stream_students'),
    
    path('academic/streams/<int:pk>/bulk-assign/',  StreamBulkAssignStudentsView.as_view(), name='stream_bulk_assign'),    
    path('academic/streams/<int:pk>/remove-student/', StreamRemoveStudentView.as_view(), name='stream_remove_student'),    
    path('academic/streams/<int:pk>/bulk-remove/', StreamBulkRemoveStudentsView.as_view(), name='stream_bulk_remove'),    
    path('academic/streams/<int:pk>/available-students/',  GetAvailableStudentsForStreamView.as_view(), name='get_available_students_for_stream'),

    # ── Streams ───────────────────────────────────────────────────────────────
    path('academic/streams/create/',StreamClassCreateView.as_view(),name='stream_create',),   

    # ── Subjects ──────────────────────────────────────────────────────────────
    path('academic/subjects/',SubjectListView.as_view(),name='subject_list',),
   
          # Subjects
    path('academic/subjects/',  SubjectListView.as_view(),  name='subject_list'),    
    path('academic/subjects/crud/',  SubjectCRUDView.as_view(),  name='subject_crud'),    
    path('academic/subjects/<int:pk>/details/',   GetSubjectDetailsView.as_view(),  name='get_subject_details'),    
    path('academic/subjects/<int:pk>/students/',       SubjectStudentsView.as_view(),  name='subject_students'),

    # ── Combinations (A-Level) ────────────────────────────────────────────────
    path('academic/combinations/',CombinationListView.as_view(),name='combination_list',), 
          # Combinations
    path('academic/combinations/', CombinationListView.as_view(), name='combination_list'),    
    path('academic/combinations/crud/', CombinationCRUDView.as_view(),name='combination_crud'),    
    path('academic/combinations/<int:pk>/details/', GetCombinationDetailsView.as_view(), name='get_combination_details'),    
    path('academic/combinations/<int:pk>/subjects/', CombinationSubjectsView.as_view(), name='combination_subjects'),    
    path('academic/combination-subjects/crud/', CombinationSubjectCRUDView.as_view(), name='combination_subject_crud'),
    path('academic/combinations/<int:pk>/students/', CombinationStudentsView.as_view(),  name='combination_students'),

    # Student Combination Assignment CRUD
    path('academic/student-combination/assign/',StudentCombinationAssignView.as_view(), name='student_combination_assign'),    
    path('academic/student-combination/remove/', StudentCombinationRemoveView.as_view(), name='student_combination_remove'),    
    path('academic/student-combination/bulk-remove/', StudentCombinationBulkRemoveView.as_view(), name='student_combination_bulk_remove'),
    path('academic/ajax/get-combination-history/',  GetCombinationHistoryView.as_view(), name='get_combination_history'),
    path('academic/ajax/get-a-level-enrollments/', GetALevelEnrollmentsView.as_view(), name='get_a_level_enrollments'),

    path('departments/', DepartmentListView.as_view(), name='department_list'),
    path('departments/create/', DepartmentCreateView.as_view(), name='department_create'),
    path('departments/<int:pk>/', DepartmentDetailView.as_view(), name='department_detail'),
    path('departments/<int:pk>/update/', DepartmentUpdateView.as_view(), name='department_update'),
    path('departments/<int:pk>/delete/', DepartmentDeleteView.as_view(), name='department_delete'),
    
    # AJAX helper URLs

    path('departments/search/', DepartmentSearchView.as_view(), name='department_search'),

     
    
]