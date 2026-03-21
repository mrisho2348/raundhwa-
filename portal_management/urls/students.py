"""
portal_management/urls/students.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Student URL patterns — one URL per view, grouped by section.

31 views mapped across 7 sections:
  Student CRUD       — list, create, detail, update
  Enrollment         — enroll, stream assign
  Drafts             — list, create, edit, publish, delete
  Lifecycle          — suspend, lift, transfer, withdraw
  Account            — reset password
  Parent Management  — management page, add, update, remove,
                       set primary, bulk add, edit, delete,
                       get details, list, create, update
  AJAX Helpers       — search parents, get streams, get combinations
"""
from django.urls import path
from portal_management.views.class_level import ClassLevelDetailView
from portal_management.views.division_scale_views import DivisionScaleCheckDependenciesView, DivisionScaleCreateView, DivisionScaleDeleteView, DivisionScaleDetailView, DivisionScaleListView, DivisionScaleSearchView, DivisionScaleUpdateView

from portal_management.views.grading_scale_views import GradingScaleCheckDependenciesView, GradingScaleCreateView, GradingScaleDeleteView, GradingScaleDetailView, GradingScaleListView, GradingScaleSearchView, GradingScaleUpdateView
from portal_management.views.promotion_views import PromotionBulkView, PromotionListView, PromotionProcessView, PromotionRevertView
from portal_management.views.stream_assignment import StreamAssignStudentsView, StreamRemoveStudentView
from portal_management.views.stream_class import *
from portal_management.views.student_combination_assignment import *
from portal_management.views.student_enrollment import *
from portal_management.views.student_transfer import *
from portal_management.views.students import *
from portal_management.views.subject_views import SubjectAssignStudentsView, SubjectRemoveStudentView
from portal_management.views.term_views import *

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════════
    # STUDENT CRUD
    # ══════════════════════════════════════════════════════════════════════
    path('students/',StudentListView.as_view(),name='student_list',),
    path('students/create/',StudentCreateView.as_view(),name='student_create',),
    path('students/<int:pk>/',StudentDetailView.as_view(),name='student_detail',),
    path('students/<int:pk>/edit/',StudentUpdateView.as_view(),name='student_update',),

    # ══════════════════════════════════════════════════════════════════════
    # ENROLLMENT
    # ══════════════════════════════════════════════════════════════════════
    path('students/<int:pk>/enroll/',StudentEnrollView.as_view(),name='student_enroll',),
    path('students/<int:pk>/stream/',StudentStreamAssignView.as_view(),name='student_stream',),

    # ══════════════════════════════════════════════════════════════════════
    # DRAFTS
    # ══════════════════════════════════════════════════════════════════════
    path('students/drafts/',StudentDraftListView.as_view(),name='student_draft_list',),
    path('students/drafts/create/',StudentDraftCreateView.as_view(),name='student_draft_create',),
    path('students/drafts/<int:pk>/edit/',StudentDraftEditView.as_view(),name='student_draft_edit',),
    path('students/drafts/<int:pk>/publish/',StudentDraftPublishView.as_view(),name='student_draft_publish',),
    path('students/drafts/<int:pk>/delete/',StudentDraftDeleteView.as_view(),name='student_draft_delete',),

    # ══════════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ══════════════════════════════════════════════════════════════════════
    path('students/<int:pk>/suspend/',StudentSuspendView.as_view(),name='student_suspend',),
    path('students/<int:pk>/suspend/<int:suspension_pk>/lift/',StudentLiftSuspensionView.as_view(),name='student_lift_suspension',),
    path('students/<int:pk>/transfer/',StudentTransferView.as_view(),name='student_transfer',),
    path('students/<int:pk>/withdraw/',StudentWithdrawView.as_view(),name='student_withdraw',),

    # ══════════════════════════════════════════════════════════════════════
    # ACCOUNT
    # ══════════════════════════════════════════════════════════════════════
    path('students/reset-password/<int:user_id>/',StudentResetPasswordView.as_view(),name='student_reset_password',),

    # ══════════════════════════════════════════════════════════════════════
    # PARENT MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════

    # Main management page for a student's parents
    path('students/<int:pk>/parents/', StudentParentManagementView.as_view(), name='student_parent_management',),
    # Add or link a parent to a student
    path('students/<int:pk>/parents/add/', StudentAddParentView.as_view(),name='student_add_parent',),
    # Update relationship flags (primary, fee responsible)
    path('students/<int:pk>/parents/<int:relationship_pk>/update/', StudentParentUpdateView.as_view(),name='student_parent_update',),
    # Unlink a parent from a student
    path('students/<int:pk>/parents/<int:relationship_pk>/remove/',StudentParentRemoveView.as_view(),name='student_parent_remove',),
    # Set a parent as primary contact
    path('students/<int:pk>/parents/<int:relationship_pk>/set-primary/',StudentParentSetPrimaryView.as_view(),name='student_parent_set_primary',),
    # Bulk link multiple parents
    path('students/<int:pk>/parents/bulk-add/',StudentParentBulkAddView.as_view(),name='student_parent_bulk_add',),

    # ── Standalone parent records ─────────────────────────────────────────
    # path('parents/',ParentListView.as_view(),name='student_parent_list',),
    # path('parents/create/',ParentCreateView.as_view(),name='student_parent_create',),
    # path('parents/<int:pk>/edit/',ParentUpdateView.as_view(),name='student_parent_update',),
    # Edit parent via AJAX modal (used from parent_management page)
    path('parents/<int:parent_pk>/edit-ajax/',ParentEditView.as_view(),name='parent_edit',),
    # Delete parent (only if no students linked)
    # path('parents/<int:parent_pk>/delete/',ParentDeleteView.as_view(),name='parent_delete',),
    # Get parent details for the edit modal
    path('parents/<int:parent_pk>/details/',GetParentDetailsView.as_view(),name='ajax_parent_details',),

    # ══════════════════════════════════════════════════════════════════════
    # AJAX HELPERS
    # ══════════════════════════════════════════════════════════════════════
    path('ajax/search-parents/', SearchParentsView.as_view(), name='ajax_search_parents',),
    path('ajax/get-streams/',GetStreamsView.as_view(), name='ajax_get_streams',),
    path('ajax/get-combinations/',GetCombinationsView.as_view(),name='ajax_get_combinations',),

        # Combination Management URLs (A-Level only)
    path('students/enrollments/<int:pk>/combination/', StudentEnrollmentCombinationView.as_view(), name='student_enrollment_combination'),
    path('students/enrollments/<int:pk>/combination/remove/', StudentEnrollmentCombinationRemoveView.as_view(), name='student_enrollment_combination_remove'),
      # ============================================================================
    # STUDENT ENROLLMENTS
    # ============================================================================
    path('students/enrollments/', StudentEnrollmentListView.as_view(), name='student_enrollment_list'),
    
    path('students/enrollments/create/', StudentEnrollmentCreateView.as_view(), name='student_enrollment_create'),
    path('students/enrollments/<int:pk>/', StudentEnrollmentDetailView.as_view(), name='student_enrollment_detail'),    
    path('students/enrollments/<int:pk>/update/', StudentEnrollmentUpdateView.as_view(), name='student_enrollment_update'),    
    path('students/enrollments/<int:pk>/status/', StudentEnrollmentStatusUpdateView.as_view(), name='student_enrollment_status_update'),    
    path('students/enrollments/<int:pk>/promote/', StudentEnrollmentPromoteView.as_view(), name='student_enrollment_promote'),    
    path('students/enrollments/<int:pk>/delete/', StudentEnrollmentDeleteView.as_view(), name='student_enrollment_delete'),
    path('students/enrollments/<int:pk>/stream/', StudentEnrollmentStreamView.as_view(), name='student_enrollment_stream'),  # Add this missing URL
    path('students/enrollments/<int:pk>/stream/remove/', StudentEnrollmentStreamRemoveView.as_view(), name='student_enrollment_stream_remove'),
    # ============================================================================
    # AJAX ENDPOINTS
    # ============================================================================
    path('students/ajax/get-available-class-levels/', GetAvailableClassLevelsView.as_view(), name='get_available_class_levels'),    
    path('students/ajax/get-student-enrollment-history/',GetStudentEnrollmentHistoryView.as_view(), name='get_student_enrollment_history'),
    path('students/ajax/search-students-for-enrollment/', SearchStudentsForEnrollmentView.as_view(), name='search_students_for_enrollment'),
    path('students/ajax/get-class-levels-by-academic-year/', GetClassLevelsByAcademicYearView.as_view(), name='get_class_levels_by_academic_year'),

     # Student Transfer CRUD
    path('students/transfers/',StudentTransferListView.as_view(), name='student_transfer_list'),
    path('students/transfers/create/', StudentTransferCreateView.as_view(), name='student_transfer_create'),    
    path('students/transfers/create/<int:student_id>/', StudentTransferCreateView.as_view(), name='student_transfer_create_for_student'),    
    path('students/transfers/<int:pk>/', StudentTransferDetailView.as_view(), name='student_transfer_detail'),    
    path('students/transfers/<int:pk>/update/', StudentTransferUpdateView.as_view(), name='student_transfer_update'),    
    path('students/transfers/<int:pk>/delete/', StudentTransferDeleteView.as_view(), name='student_transfer_delete'),    
    path('students/transfers/<int:pk>/details/', GetStudentTransferDetailsView.as_view(), name='get_student_transfer_details'),    

    # Stream Class URLs
    path('academic/streams/', StreamClassListView.as_view(), name='stream_class_list'),    
    path('academic/streams/create/', StreamClassCreateView.as_view(), name='stream_class_create'),    
    path('academic/streams/<int:pk>/', StreamClassDetailView.as_view(), name='stream_class_detail'),    
    path('academic/streams/<int:pk>/update/', StreamClassUpdateView.as_view(), name='stream_class_update'),    
    path('academic/streams/<int:pk>/delete/', StreamClassDeleteView.as_view(), name='stream_class_delete'),    


    path('academic/class-level/<int:pk>/',  ClassLevelDetailView.as_view(), name='class_level_detail'),
    path('academic/streams/<int:pk>/assign-students/', StreamAssignStudentsView.as_view(), name='stream_assign_students'),
    
    path('academic/streams/<int:pk>/remove-student/<int:assignment_pk>/', StreamRemoveStudentView.as_view(),name='stream_remove_student'),
    # Add to urls.py
    path('academic/subjects/<int:pk>/assign-students/', SubjectAssignStudentsView.as_view(),  name='subject_assign_students'),
    path('academic/subjects/<int:pk>/remove-student/<int:assignment_pk>/', SubjectRemoveStudentView.as_view(), name='subject_remove_student'),

     # Student Combination Assignment URLs
    path('students/combinations/', StudentCombinationAssignmentListView.as_view(), name='student_combination_assignment_list'),    
    path('students/combinations/create/', StudentCombinationAssignmentCreateView.as_view(), name='student_combination_assignment_create'),    
    path('students/combinations/create/<int:student_id>/', StudentCombinationAssignmentCreateView.as_view(), name='student_combination_assignment_create_for_student'),    
    path('students/combinations/<int:pk>/', StudentCombinationAssignmentDetailView.as_view(), name='student_combination_assignment_detail'),    
    path('students/combinations/<int:pk>/update/', StudentCombinationAssignmentUpdateView.as_view(), name='student_combination_assignment_update'),    
    path('students/combinations/<int:pk>/delete/', StudentCombinationAssignmentDeleteView.as_view(), name='student_combination_assignment_delete'),    
    path('api/student-enrollments/', GetStudentEnrollmentsView.as_view(), name='api_student_enrollments'),


    path('students/promotions/', PromotionListView.as_view(), name='promotion_list'),
    path('students/promotions/process/', PromotionProcessView.as_view(), name='promotion_process'),
    path('students/promotions/bulk/', PromotionBulkView.as_view(), name='promotion_bulk'),
    path('students/promotions/<int:enrollment_id>/revert/', PromotionRevertView.as_view(), name='promotion_revert'),

       # Term URLs
    path('terms/', TermListView.as_view(), name='term_list'),
    path('terms/create/', TermCreateView.as_view(), name='term_create'),
    path('terms/<int:pk>/', TermDetailView.as_view(), name='term_detail'),
    path('terms/<int:pk>/update/', TermUpdateView.as_view(), name='term_update'),
    path('terms/<int:pk>/delete/', TermDeleteView.as_view(), name='term_delete'),
    path('terms/<int:pk>/check-dependencies/', TermCheckDependenciesView.as_view(), name='term_check_dependencies'),
    path('terms/search/', TermSearchView.as_view(), name='term_search'),
    path('terms/<int:pk>/deactivate/', TermDeactivateView.as_view(), name='term_deactivate'),


        # Main CRUD URLs
    path('grading-scales/', GradingScaleListView.as_view(), name='grading_scale_list'),
    path('grading-scales/create/', GradingScaleCreateView.as_view(), name='grading_scale_create'),
    path('grading-scales/<int:pk>/', GradingScaleDetailView.as_view(), name='grading_scale_detail'),
    path('grading-scales/<int:pk>/update/', GradingScaleUpdateView.as_view(), name='grading_scale_update'),
    path('grading-scales/<int:pk>/delete/', GradingScaleDeleteView.as_view(), name='grading_scale_delete'),
    
    # AJAX helper URLs
    path('grading-scales/<int:pk>/check-dependencies/', GradingScaleCheckDependenciesView.as_view(), name='grading_scale_check_dependencies'),
    path('grading-scales/search/', GradingScaleSearchView.as_view(), name='grading_scale_search'),


     # Main CRUD URLs
    path('division-scales/', DivisionScaleListView.as_view(), name='division_scale_list'),
    path('division-scales/create/', DivisionScaleCreateView.as_view(), name='division_scale_create'),
    path('division-scales/<int:pk>/', DivisionScaleDetailView.as_view(), name='division_scale_detail'),
    path('division-scales/<int:pk>/update/', DivisionScaleUpdateView.as_view(), name='division_scale_update'),
    path('division-scales/<int:pk>/delete/', DivisionScaleDeleteView.as_view(), name='division_scale_delete'),
    
    # AJAX helper URLs
    path('division-scales/<int:pk>/check-dependencies/', DivisionScaleCheckDependenciesView.as_view(), name='division_scale_check_dependencies'),
    path('division-scales/search/', DivisionScaleSearchView.as_view(), name='division_scale_search'),


    

        # Parent URLs



]