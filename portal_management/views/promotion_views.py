# portal_management/views/promotion_views.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    StreamClass, StudentEnrollment, Student, AcademicYear, ClassLevel,
    StudentStreamAssignment, StudentCombinationAssignment
)

logger = logging.getLogger(__name__)


class PromotionListView(ManagementRequiredMixin, View):
    """View to list students eligible for promotion."""
    template_name = 'portal_management/students/promotions/list.html'
    paginate_by = 20

    def get_eligible_students(self, from_class_level, from_academic_year):
        """Get students eligible for promotion from a specific class."""
        enrollments = StudentEnrollment.objects.filter(
            status='active',
            class_level=from_class_level,
            academic_year=from_academic_year
        ).select_related('student', 'class_level', 'academic_year')
        
        enrollments = enrollments.exclude(status='promoted')
        
        return enrollments

    def get_promoted_students(self, from_class_level, from_academic_year):
        """Get students already promoted from this class."""
        return StudentEnrollment.objects.filter(
            status='promoted',
            class_level=from_class_level,
            academic_year=from_academic_year
        ).select_related('student', 'class_level', 'academic_year')

    def get(self, request):
        """Display promotion list with filters."""
        from_class_id = request.GET.get('from_class')
        to_class_id = request.GET.get('to_class')
        academic_year_id = request.GET.get('academic_year')
        
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        class_levels = ClassLevel.objects.all().order_by('educational_level', 'order')
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        context = {
            'class_levels': class_levels,
            'academic_years': academic_years,
            'current_academic_year': current_academic_year,
            'selected_from_class': from_class_id,
            'selected_to_class': to_class_id,
            'selected_academic_year': academic_year_id,
        }
        
        if from_class_id and academic_year_id:
            from_class = get_object_or_404(ClassLevel, pk=from_class_id)
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
            
            eligible_students = self.get_eligible_students(from_class, academic_year)
            promoted_students = self.get_promoted_students(from_class, academic_year)
            
            next_class = None
            if to_class_id:
                next_class = get_object_or_404(ClassLevel, pk=to_class_id)
            else:
                next_class = ClassLevel.objects.filter(
                    educational_level=from_class.educational_level,
                    order=from_class.order + 1
                ).first()
            
            next_academic_year = AcademicYear.objects.filter(
                start_date__gt=academic_year.start_date
            ).order_by('start_date').first()
            
            if not next_academic_year:
                current_year_end = int(academic_year.name.split('/')[1]) if '/' in academic_year.name else int(academic_year.name)
                next_year_name = f"{current_year_end}/{current_year_end + 1}"
                next_academic_year = AcademicYear.objects.filter(name=next_year_name).first()
            
            total_enrolled = StudentEnrollment.objects.filter(
                class_level=from_class,
                academic_year=academic_year,
                status='active'
            ).count()
            
            promoted_count = promoted_students.count()
            pending_count = eligible_students.count()
            promotion_percentage = (promoted_count / total_enrolled * 100) if total_enrolled > 0 else 0
            
            context.update({
                'from_class': from_class,
                'to_class': next_class,
                'academic_year': academic_year,
                'next_academic_year': next_academic_year,
                'eligible_students': eligible_students,
                'promoted_students': promoted_students,
                'total_enrolled': total_enrolled,
                'promoted_count': promoted_count,
                'pending_count': pending_count,
                'promotion_percentage': promotion_percentage,
            })
        
        return render(request, self.template_name, context)


class PromotionProcessView(ManagementRequiredMixin, View):
    """View to process student promotions."""
    
    def validate_promotion(self, enrollment, to_class_level, to_academic_year):
        """Comprehensive validation for student promotion."""
        errors = []
        warnings = []
        
        if not enrollment:
            errors.append("Student enrollment record not found.")
            return errors, warnings
        
        if enrollment.status != 'active':
            errors.append(f"{enrollment.student.full_name} is not active (Status: {enrollment.get_status_display()}).")
        
        if enrollment.status == 'promoted':
            errors.append(f"{enrollment.student.full_name} has already been promoted.")
        
        if enrollment.student.status in ['suspended', 'withdrawn', 'transferred']:
            errors.append(
                f"{enrollment.student.full_name} is {enrollment.student.get_status_display()} and "
                f"cannot be promoted until the status is resolved."
            )
        
        if enrollment.class_level.is_final:
            errors.append(
                f"{enrollment.student.full_name} is in the final class level "
                f"({enrollment.class_level.name}). This student should be marked as 'completed', "
                f"not promoted to another class."
            )
        
        if to_class_level.educational_level != enrollment.class_level.educational_level:
            errors.append(
                f"{enrollment.student.full_name} cannot be promoted across educational levels. "
                f"Cannot move from {enrollment.class_level.educational_level.name} "
                f"to {to_class_level.educational_level.name}."
            )
        
        if to_class_level.order <= enrollment.class_level.order:
            errors.append(
                f"{enrollment.student.full_name} cannot be promoted to a lower or same class level. "
                f"Cannot move from {enrollment.class_level.name} (Order: {enrollment.class_level.order}) "
                f"to {to_class_level.name} (Order: {to_class_level.order})."
            )
        
        if to_class_level.order != enrollment.class_level.order + 1:
            warnings.append(
                f"{enrollment.student.full_name} is being promoted from {enrollment.class_level.name} "
                f"to {to_class_level.name}, skipping {enrollment.class_level.order + 1}. "
                f"Please verify this is intended."
            )
        
        if not to_academic_year:
            errors.append("Target academic year is not specified.")
        else:
            if not to_academic_year.is_active:
                warnings.append(
                    f"Target academic year {to_academic_year.name} is not active. "
                    f"The promotion will still proceed, but the student will be enrolled in an inactive year."
                )
            
            if to_academic_year.start_date <= enrollment.academic_year.start_date:
                errors.append(
                    f"{enrollment.student.full_name} cannot be promoted to {to_academic_year.name} "
                    f"because it is not after the current academic year {enrollment.academic_year.name}."
                )
        
        existing_enrollment = StudentEnrollment.objects.filter(
            student=enrollment.student,
            academic_year=to_academic_year
        ).exclude(pk=enrollment.pk).exists()
        
        if existing_enrollment:
            errors.append(
                f"{enrollment.student.full_name} already has an enrollment "
                f"for {to_academic_year.name}. Duplicate enrollment is not allowed."
            )
        
        return errors, warnings
    
    def promote_single_student(self, enrollment, to_class_level, to_academic_year, 
                               remarks=None, preserve_stream=True, preserve_combination=True):
        """Promote a single student with comprehensive validation."""
        try:
            with transaction.atomic():
                errors, warnings = self.validate_promotion(enrollment, to_class_level, to_academic_year)
                
                if errors:
                    return {
                        'success': False, 
                        'errors': errors,
                        'warnings': warnings
                    }
                
                existing_target_enrollment = StudentEnrollment.objects.filter(
                    student=enrollment.student,
                    academic_year=to_academic_year,
                    class_level=to_class_level
                ).exists()
                
                if existing_target_enrollment:
                    return {
                        'success': False,
                        'errors': [f"{enrollment.student.full_name} is already enrolled in {to_class_level.name} for {to_academic_year.name}."],
                        'warnings': warnings
                    }
                
                promotion_remarks = f"Promoted from {enrollment.class_level.name} ({enrollment.academic_year.name}) on {timezone.now().date()}"
                if remarks:
                    promotion_remarks += f"\nRemarks: {remarks}"
                
                new_enrollment = StudentEnrollment.objects.create(
                    student=enrollment.student,
                    academic_year=to_academic_year,
                    class_level=to_class_level,
                    enrollment_date=timezone.now().date(),
                    status='active',
                    remarks=promotion_remarks
                )
                
                stream_preserved = False
                if preserve_stream:
                    current_stream = StudentStreamAssignment.objects.filter(
                        enrollment=enrollment
                    ).select_related('stream_class').first()
                    
                    if current_stream:
                        new_stream = StreamClass.objects.filter(
                            class_level=to_class_level,
                            stream_letter=current_stream.stream_class.stream_letter
                        ).first()
                        
                        if new_stream:
                            current_count = new_stream.student_count
                            if current_count < new_stream.capacity:
                                StudentStreamAssignment.objects.create(
                                    enrollment=new_enrollment,
                                    stream_class=new_stream,
                                    assigned_date=timezone.now().date(),
                                    remarks=f"Carried over from previous class on promotion"
                                )
                                stream_preserved = True
                            else:
                                warnings.append(
                                    f"Stream {new_stream.name} is at full capacity ({new_stream.capacity}/{new_stream.capacity}). "
                                    f"Stream assignment not carried over for {enrollment.student.full_name}."
                                )
                        else:
                            warnings.append(
                                f"Stream {current_stream.stream_class.name} not found in "
                                f"{to_class_level.name}. Stream assignment not carried over for {enrollment.student.full_name}."
                            )
                
                combination_preserved = False
                if preserve_combination and to_class_level.educational_level.level_type == 'A_LEVEL':
                    current_combination = enrollment.current_combination
                    if current_combination:
                        StudentCombinationAssignment.objects.filter(
                            enrollment=enrollment,
                            is_active=True
                        ).update(is_active=False)
                        
                        StudentCombinationAssignment.objects.create(
                            student=enrollment.student,
                            enrollment=new_enrollment,
                            combination=current_combination,
                            assigned_date=timezone.now().date(),
                            is_active=True,
                            remarks=f"Carried over from previous enrollment on promotion"
                        )
                        combination_preserved = True
                
                enrollment.status = 'promoted'
                enrollment.remarks = (enrollment.remarks or '') + f"\nPromoted to {to_class_level.name} ({to_academic_year.name}) on {timezone.now().date()}"
                enrollment.save()
                
                success_details = []
                if stream_preserved:
                    success_details.append("stream preserved")
                if combination_preserved:
                    success_details.append("combination preserved")
                
                details_text = f" ({', '.join(success_details)})" if success_details else ""
                
                return {
                    'success': True,
                    'new_enrollment_id': new_enrollment.pk,
                    'student_name': enrollment.student.full_name,
                    'message': f"{enrollment.student.full_name} promoted successfully{details_text}.",
                    'warnings': warnings,
                    'stream_preserved': stream_preserved,
                    'combination_preserved': combination_preserved
                }
                
        except Exception as e:
            logger.error(f"Error promoting student {enrollment.pk}: {e}", exc_info=True)
            return {
                'success': False, 
                'errors': [f"System error: {str(e)}"],
                'warnings': []
            }
    
    def post(self, request):
        """Process promotion requests with enhanced validation and response."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        enrollment_ids = request.POST.getlist('enrollments')
        to_class_id = request.POST.get('to_class')
        to_academic_year_id = request.POST.get('to_academic_year')
        remarks = request.POST.get('remarks', '')
        preserve_stream = request.POST.get('preserve_stream') == 'true'
        preserve_combination = request.POST.get('preserve_combination') == 'true'
        
        if not enrollment_ids:
            error_msg = 'Please select at least one student to promote.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        if not to_class_id:
            error_msg = 'Please select the target class level.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        if not to_academic_year_id:
            error_msg = 'Please select the target academic year.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        try:
            to_class = get_object_or_404(ClassLevel, pk=to_class_id)
            to_academic_year = get_object_or_404(AcademicYear, pk=to_academic_year_id)
        except Exception as e:
            error_msg = f'Invalid target class or academic year: {str(e)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        enrollments = StudentEnrollment.objects.filter(
            pk__in=enrollment_ids,
            status='active'
        ).select_related('student', 'class_level', 'academic_year')
        
        if not enrollments.exists():
            error_msg = 'No valid active enrollments found for the selected students.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        promoted_students = []
        failed_students = []
        all_warnings = []
        
        with transaction.atomic():
            for enrollment in enrollments:
                result = self.promote_single_student(
                    enrollment, to_class, to_academic_year,
                    remarks, preserve_stream, preserve_combination
                )
                
                if result['success']:
                    promoted_students.append({
                        'name': result['student_name'],
                        'message': result.get('message', 'Promoted successfully'),
                        'warnings': result.get('warnings', [])
                    })
                    if result.get('warnings'):
                        all_warnings.extend(result['warnings'])
                else:
                    failed_students.append({
                        'name': enrollment.student.full_name,
                        'errors': result.get('errors', ['Unknown error']),
                        'warnings': result.get('warnings', [])
                    })
                    if result.get('warnings'):
                        all_warnings.extend(result['warnings'])
        
        promoted_count = len(promoted_students)
        failed_count = len(failed_students)
        
        # Determine if any students were promoted
        has_success = promoted_count > 0
        has_failures = failed_count > 0
        
        if has_success and not has_failures:
            message = f"✅ Successfully promoted {promoted_count} student(s)."
            message_type = 'success'
            should_reload = True
        elif has_success and has_failures:
            message = f"⚠️ Partially successful: {promoted_count} promoted, {failed_count} failed."
            message_type = 'warning'
            should_reload = True  # Reload to show updated promoted students
        else:
            message = f"❌ Failed to promote {failed_count} student(s)."
            message_type = 'error'
            should_reload = False  # Don't reload if no promotions succeeded
        
        if all_warnings:
            message += f" {len(all_warnings)} warning(s) occurred."
        
        if is_ajax:
            return JsonResponse({
                'success': has_success,
                'message': message,
                'message_type': message_type,
                'promoted_count': promoted_count,
                'failed_count': failed_count,
                'promoted_students': promoted_students,
                'failed_students': failed_students,
                'warnings': all_warnings,
                'reload': should_reload
            })
        
        # Non-AJAX response
        if has_success:
            messages.success(request, message)
            for student in promoted_students:
                messages.info(request, student['message'])
                for warning in student['warnings']:
                    messages.warning(request, warning)
        
        if has_failures:
            for failed in failed_students:
                for error in failed['errors']:
                    messages.error(request, error)
                for warning in failed['warnings']:
                    messages.warning(request, warning)
        
        return redirect('management:promotion_list')


class PromotionBulkView(ManagementRequiredMixin, View):
    """View for bulk promotion of entire class with enhanced validation."""
    
    def post(self, request):
        """Process bulk promotion for an entire class."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        from_class_id = request.POST.get('from_class')
        from_academic_year_id = request.POST.get('from_academic_year')
        to_class_id = request.POST.get('to_class')
        to_academic_year_id = request.POST.get('to_academic_year')
        remarks = request.POST.get('remarks', '')
        preserve_stream = request.POST.get('preserve_stream') == 'true'
        preserve_combination = request.POST.get('preserve_combination') == 'true'
        
        if not all([from_class_id, from_academic_year_id, to_class_id, to_academic_year_id]):
            error_msg = 'Missing required parameters. Please ensure all fields are selected.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        try:
            from_class = get_object_or_404(ClassLevel, pk=from_class_id)
            from_academic_year = get_object_or_404(AcademicYear, pk=from_academic_year_id)
            to_class = get_object_or_404(ClassLevel, pk=to_class_id)
            to_academic_year = get_object_or_404(AcademicYear, pk=to_academic_year_id)
        except Exception as e:
            error_msg = f'Invalid parameters: {str(e)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        if to_class.educational_level != from_class.educational_level:
            error_msg = f'Cannot promote from {from_class.name} to {to_class.name}. Promotion must be within the same educational level.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        if to_class.order <= from_class.order:
            error_msg = f'Cannot promote from {from_class.name} (Order: {from_class.order}) to {to_class.name} (Order: {to_class.order}). Promotion must be to a higher class level.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        if to_academic_year.start_date <= from_academic_year.start_date:
            error_msg = f'Target academic year {to_academic_year.name} must be after source academic year {from_academic_year.name}.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        enrollments = StudentEnrollment.objects.filter(
            class_level=from_class,
            academic_year=from_academic_year,
            status='active'
        ).select_related('student', 'class_level', 'academic_year')
        
        if not enrollments.exists():
            error_msg = f'No active students found in {from_class.name} for {from_academic_year.name}.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        promoted_students = []
        failed_students = []
        all_warnings = []
        
        promotion_processor = PromotionProcessView()
        
        with transaction.atomic():
            for enrollment in enrollments:
                result = promotion_processor.promote_single_student(
                    enrollment, to_class, to_academic_year,
                    remarks, preserve_stream, preserve_combination
                )
                
                if result['success']:
                    promoted_students.append({
                        'name': result['student_name'],
                        'message': result.get('message', 'Promoted successfully'),
                        'warnings': result.get('warnings', [])
                    })
                    if result.get('warnings'):
                        all_warnings.extend(result['warnings'])
                else:
                    failed_students.append({
                        'name': enrollment.student.full_name,
                        'errors': result.get('errors', ['Unknown error']),
                        'warnings': result.get('warnings', [])
                    })
                    if result.get('warnings'):
                        all_warnings.extend(result['warnings'])
        
        promoted_count = len(promoted_students)
        failed_count = len(failed_students)
        
        has_success = promoted_count > 0
        has_failures = failed_count > 0
        
        if has_success and not has_failures:
            message = f"✅ Successfully promoted all {promoted_count} student(s) from {from_class.name} to {to_class.name}."
            message_type = 'success'
            should_reload = True
        elif has_success and has_failures:
            message = f"⚠️ Bulk promotion partially successful: {promoted_count} promoted, {failed_count} failed from {from_class.name}."
            message_type = 'warning'
            should_reload = True
        else:
            message = f"❌ Bulk promotion failed. Could not promote any students from {from_class.name}."
            message_type = 'error'
            should_reload = False
        
        if all_warnings:
            message += f" {len(all_warnings)} warning(s) occurred."
        
        if is_ajax:
            return JsonResponse({
                'success': has_success,
                'message': message,
                'message_type': message_type,
                'promoted_count': promoted_count,
                'failed_count': failed_count,
                'promoted_students': promoted_students,
                'failed_students': failed_students,
                'warnings': all_warnings,
                'reload': should_reload
            })
        
        if has_success:
            messages.success(request, message)
            for student in promoted_students:
                messages.info(request, student['message'])
                for warning in student['warnings']:
                    messages.warning(request, warning)
        
        if has_failures:
            for failed in failed_students:
                for error in failed['errors']:
                    messages.error(request, error)
                for warning in failed['warnings']:
                    messages.warning(request, warning)
        
        return redirect('management:promotion_list')


class PromotionRevertView(ManagementRequiredMixin, View):
    """View to revert a promotion with validation."""
    
    def validate_revert(self, promoted_enrollment):
        """Validate if a promotion can be reverted."""
        errors = []
        warnings = []
        
        if promoted_enrollment.status != 'promoted':
            errors.append("This enrollment is not marked as promoted.")
        
        next_enrollment = StudentEnrollment.objects.filter(
            student=promoted_enrollment.student,
            academic_year__start_date__gt=promoted_enrollment.academic_year.start_date
        ).order_by('academic_year__start_date').first()
        
        if not next_enrollment:
            warnings.append(
                "No subsequent enrollment found for this promotion. "
                "The student will be marked as active without a target enrollment to delete."
            )
        
        return errors, warnings, next_enrollment
    
    def post(self, request, enrollment_id):
        """Revert a promotion with validation."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        promoted_enrollment = get_object_or_404(StudentEnrollment, pk=enrollment_id)
        
        errors, warnings, next_enrollment = self.validate_revert(promoted_enrollment)
        
        if errors:
            error_msg = ' '.join(errors)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:promotion_list')
        
        try:
            with transaction.atomic():
                student_name = promoted_enrollment.student.full_name
                
                promoted_enrollment.status = 'active'
                promoted_enrollment.remarks = (promoted_enrollment.remarks or '') + \
                    f"\nPromotion reverted on {timezone.now().date()} by {request.user.username}"
                promoted_enrollment.save()
                
                reverted_details = []
                if next_enrollment:
                    stream_count = StudentStreamAssignment.objects.filter(enrollment=next_enrollment).count()
                    StudentStreamAssignment.objects.filter(enrollment=next_enrollment).delete()
                    if stream_count > 0:
                        reverted_details.append(f"removed {stream_count} stream assignment(s)")
                    
                    combo_count = StudentCombinationAssignment.objects.filter(enrollment=next_enrollment).count()
                    StudentCombinationAssignment.objects.filter(enrollment=next_enrollment).delete()
                    if combo_count > 0:
                        reverted_details.append(f"removed {combo_count} combination assignment(s)")
                    
                    next_enrollment.delete()
                    reverted_details.append("deleted next year enrollment")
                
                details_text = f" ({', '.join(reverted_details)})" if reverted_details else ""
                message = f"Promotion reverted for {student_name}{details_text}."
                
                if warnings:
                    message += f" Warnings: {'; '.join(warnings)}"
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'warnings': warnings,
                        'reload': True
                    })
                
                messages.success(request, message)
                for warning in warnings:
                    messages.warning(request, warning)
                
                return redirect('management:promotion_list')
                
        except Exception as e:
            logger.error(f"Error reverting promotion {enrollment_id}: {e}", exc_info=True)
            error_msg = f"Error reverting promotion: {str(e)}"
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'reload': False
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:promotion_list')