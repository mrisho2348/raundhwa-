# portal_management/views/staff_leave_views.py

import logging
from datetime import date, timedelta
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Count, Sum, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.core.exceptions import ValidationError
from django.db.models import Avg
from core.mixins import ManagementRequiredMixin
from core.models import StaffLeave, Staff, AcademicYear, CustomUser

logger = logging.getLogger(__name__)


class StaffLeaveListView(ManagementRequiredMixin, View):
    """View to list all staff leaves with filtering and search."""
    template_name = 'portal_management/hr/leaves/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = StaffLeave.objects.all().select_related(
            'staff', 'reviewed_by', 'substitute'
        )
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=search) |
                Q(staff__last_name__icontains=search) |
                Q(staff__employee_id__icontains=search) |
                Q(reason__icontains=search) |
                Q(review_remarks__icontains=search)
            )
        
        # Staff filter
        staff_id = request.GET.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Leave type filter
        leave_type = request.GET.get('leave_type')
        if leave_type:
            queryset = queryset.filter(leave_type=leave_type)
        
        # Status filter
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Date range filter
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        if from_date:
            queryset = queryset.filter(start_date__gte=from_date)
        if to_date:
            queryset = queryset.filter(end_date__lte=to_date)
        
        return queryset.order_by('-start_date')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        pending = queryset.filter(status='pending').count()
        approved = queryset.filter(status='approved').count()
        rejected = queryset.filter(status='rejected').count()
        cancelled = queryset.filter(status='cancelled').count()
        
        # Get current active leaves
        today = timezone.now().date()
        active_leaves = queryset.filter(
            status='approved',
            start_date__lte=today,
            end_date__gte=today
        ).count()
        
        # Get upcoming leaves (starting in next 7 days)
        next_week = today + timedelta(days=7)
        upcoming_leaves = queryset.filter(
            status='approved',
            start_date__gte=today,
            start_date__lte=next_week
        ).count()
        
        # Total duration in days
        total_days = sum(leave.duration_days for leave in queryset.filter(status='approved'))
        
        return {
            'total_leaves': total,
            'pending_leaves': pending,
            'approved_leaves': approved,
            'rejected_leaves': rejected,
            'cancelled_leaves': cancelled,
            'active_leaves': active_leaves,
            'upcoming_leaves': upcoming_leaves,
            'total_days': total_days,
        }

    def get(self, request):
        """Handle GET request - display staff leave list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        leaves = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Generate page range for pagination
        page_range = []
        if total_pages <= 7:
            page_range = range(1, total_pages + 1)
        else:
            if page <= 4:
                page_range = list(range(1, 6)) + ['...'] + [total_pages]
            elif page >= total_pages - 3:
                page_range = [1, '...'] + list(range(total_pages - 4, total_pages + 1))
            else:
                page_range = [1, '...'] + list(range(page - 1, page + 2)) + ['...'] + [total_pages]
        
        # Get filter data
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        
        context = {
            'leaves': leaves,
            'staff_members': staff_members,
            'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
            'status_choices': StaffLeave.STATUS_CHOICES,
            **self.get_statistics(queryset),
            'search_query': request.GET.get('search', ''),
            'selected_staff': request.GET.get('staff', ''),
            'selected_leave_type': request.GET.get('leave_type', ''),
            'selected_status': request.GET.get('status', ''),
            'selected_from_date': request.GET.get('from_date', ''),
            'selected_to_date': request.GET.get('to_date', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
            'page_range': page_range,
        }
        
        return render(request, self.template_name, context)


class StaffLeaveCreateView(ManagementRequiredMixin, View):
    """View to create a new staff leave application."""
    template_name = 'portal_management/hr/leaves/form.html'

    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors

    def _validate_leave_data(self, data):
        """Validate staff leave data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        leave_type = data.get('leave_type')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        reason = data.get('reason', '').strip()
        substitute_id = data.get('substitute')
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not leave_type:
            errors['leave_type'] = ['Leave type is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        if not end_date:
            errors['end_date'] = ['End date is required.']
        
        if not reason:
            errors['reason'] = ['Reason for leave is required.']
        
        # Convert dates
        if start_date and end_date:
            try:
                start = date.fromisoformat(start_date)
                end = date.fromisoformat(end_date)
                
                if end < start:
                    errors['end_date'] = ['End date cannot be before start date.']
                
                # Check for overlapping leaves
                if staff_id and not errors:
                    overlapping = StaffLeave.objects.filter(
                        staff_id=staff_id,
                        status__in=['pending', 'approved'],
                        start_date__lte=end,
                        end_date__gte=start
                    )
                    if overlapping.exists():
                        overlap = overlapping.first()
                        errors['__all__'] = errors.get('__all__', []) + [
                            f'This leave period overlaps with an existing leave record '
                            f'({overlap.start_date} to {overlap.end_date}, '
                            f'{overlap.get_status_display()}).'
                        ]
                
            except ValueError:
                errors['end_date'] = ['Invalid date format.']
        
        # Validate substitute
        if substitute_id and staff_id and substitute_id == staff_id:
            errors['substitute'] = ['Staff member cannot be their own substitute.']
        
        return errors

    def get(self, request):
        """Display the create staff leave form."""
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        
        context = {
            'staff_members': staff_members,
            'title': 'Apply for Leave',
            'is_edit': False,
            'leave': None,
            'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
            'status_choices': StaffLeave.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff leave form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        staff_id = request.POST.get('staff')
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason', '').strip()
        substitute_id = request.POST.get('substitute')
        
        # Validate data
        errors = self._validate_leave_data(request.POST)
        
        if errors:
            if is_ajax:
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'leave_type' in errors:
                    message = errors['leave_type'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                elif 'end_date' in errors:
                    message = errors['end_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'title': 'Apply for Leave',
                'is_edit': False,
                'leave': None,
                'form_data': request.POST,
                'errors': errors,
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                substitute = Staff.objects.get(pk=substitute_id) if substitute_id else None
                
                leave = StaffLeave(
                    staff=staff,
                    leave_type=leave_type,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                    status='pending',  # New leaves start as pending
                    substitute=substitute
                )
                leave.full_clean()
                leave.save()
                
                message = f'Leave application for {staff.get_full_name()} submitted successfully!'
                message += f'\n\nLeave Type: {leave.get_leave_type_display()}'
                message += f'\nDuration: {leave.duration_days} day(s)'
                message += f'\nPeriod: {leave.start_date} to {leave.end_date}'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_leave_detail', args=[leave.pk]),
                        'leave': {
                            'id': leave.pk,
                            'staff': staff.get_full_name(),
                            'leave_type': leave.get_leave_type_display(),
                            'start_date': leave.start_date.strftime('%Y-%m-%d'),
                            'end_date': leave.end_date.strftime('%Y-%m-%d'),
                            'duration': leave.duration_days,
                            'status': leave.get_status_display(),
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_detail', pk=leave.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'title': 'Apply for Leave',
                'is_edit': False,
                'leave': None,
                'form_data': request.POST,
                'errors': formatted_errors,
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff leave: {e}", exc_info=True)
            error_msg = f'Error creating leave application: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'title': 'Apply for Leave',
                'is_edit': False,
                'leave': None,
                'form_data': request.POST,
                'errors': [error_msg],
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })


class StaffLeaveDetailView(ManagementRequiredMixin, View):
    """View to display staff leave details."""
    template_name = 'portal_management/hr/leaves/detail.html'

    def get(self, request, pk):
        """Display staff leave details."""
        leave = get_object_or_404(
            StaffLeave.objects.select_related(
                'staff', 'reviewed_by', 'substitute'
            ),
            pk=pk
        )
        
        # Calculate duration
        duration = leave.duration_days
        
        # Check if leave is active (currently ongoing)
        today = timezone.now().date()
        is_active_leave = (
            leave.status == 'approved' and
            leave.start_date <= today <= leave.end_date
        )
        
        # Check if leave is upcoming
        is_upcoming = (
            leave.status == 'approved' and
            leave.start_date > today
        )
        
        # Check if leave is completed
        is_completed = (
            leave.status == 'approved' and
            leave.end_date < today
        )
        
        # Get staff's leave history
        staff_leaves = StaffLeave.objects.filter(
            staff=leave.staff
        ).exclude(pk=leave.pk).order_by('-start_date')[:5]
        
        # Get staff's leave statistics
        staff_stats = StaffLeave.objects.filter(
            staff=leave.staff,
            status='approved'
        ).aggregate(
            total_leaves=Count('id'),
            total_days=Sum('duration_days'),
            avg_duration=Avg('duration_days')
        )
        
        # Get pending leaves count for the same staff
        pending_count = StaffLeave.objects.filter(
            staff=leave.staff,
            status='pending'
        ).count()
        
        context = {
            'leave': leave,
            'duration': duration,
            'today': today,
            'is_active_leave': is_active_leave,
            'is_upcoming': is_upcoming,
            'is_completed': is_completed,
            'staff_leaves': staff_leaves,
            'staff_stats': staff_stats,
            'pending_count': pending_count,
            'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
            'status_choices': StaffLeave.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)


class StaffLeaveUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff leave application."""
    template_name = 'portal_management/hr/leaves/form.html'

    def _format_errors(self, errors):
        """Format validation errors into a consistent structure."""
        formatted_errors = {}
        
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                if isinstance(error_list, (list, tuple)):
                    formatted_errors[field] = [str(error) for error in error_list]
                else:
                    formatted_errors[field] = [str(error_list)]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        
        return formatted_errors

    def _validate_leave_data(self, data, leave_id=None):
        """Validate staff leave data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        leave_type = data.get('leave_type')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        reason = data.get('reason', '').strip()
        substitute_id = data.get('substitute')
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not leave_type:
            errors['leave_type'] = ['Leave type is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        if not end_date:
            errors['end_date'] = ['End date is required.']
        
        if not reason:
            errors['reason'] = ['Reason for leave is required.']
        
        # Convert dates
        if start_date and end_date:
            try:
                start = date.fromisoformat(start_date)
                end = date.fromisoformat(end_date)
                
                if end < start:
                    errors['end_date'] = ['End date cannot be before start date.']
                
                # Check for overlapping leaves (excluding current)
                if staff_id and not errors:
                    overlapping = StaffLeave.objects.filter(
                        staff_id=staff_id,
                        status__in=['pending', 'approved'],
                        start_date__lte=end,
                        end_date__gte=start
                    ).exclude(pk=leave_id)
                    if overlapping.exists():
                        overlap = overlapping.first()
                        errors['__all__'] = errors.get('__all__', []) + [
                            f'This leave period overlaps with an existing leave record '
                            f'({overlap.start_date} to {overlap.end_date}, '
                            f'{overlap.get_status_display()}).'
                        ]
                
            except ValueError:
                errors['end_date'] = ['Invalid date format.']
        
        # Validate substitute
        if substitute_id and staff_id and substitute_id == staff_id:
            errors['substitute'] = ['Staff member cannot be their own substitute.']
        
        return errors

    def get(self, request, pk):
        """Display the edit staff leave form."""
        leave = get_object_or_404(StaffLeave, pk=pk)
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        
        context = {
            'leave': leave,
            'staff_members': staff_members,
            'title': f'Edit Leave Application: {leave.staff.get_full_name()}',
            'is_edit': True,
            'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
            'status_choices': StaffLeave.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff leave form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        leave = get_object_or_404(StaffLeave, pk=pk)
        
        # Get form data
        staff_id = request.POST.get('staff')
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason', '').strip()
        substitute_id = request.POST.get('substitute')
        
        # Validate data
        errors = self._validate_leave_data(request.POST, leave.pk)
        
        if errors:
            if is_ajax:
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'leave_type' in errors:
                    message = errors['leave_type'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                elif 'end_date' in errors:
                    message = errors['end_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'leave': leave,
                'staff_members': staff_members,
                'title': f'Edit Leave Application: {leave.staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                substitute = Staff.objects.get(pk=substitute_id) if substitute_id else None
                
                # Update leave
                leave.staff = staff
                leave.leave_type = leave_type
                leave.start_date = start_date
                leave.end_date = end_date
                leave.reason = reason
                leave.substitute = substitute
                
                # If status is being changed to approved/rejected, add review details
                if leave.status == 'pending' and request.POST.get('status') in ['approved', 'rejected']:
                    leave.status = request.POST.get('status')
                    leave.reviewed_by = self._get_reviewer_staff(request.user)
                    leave.reviewed_at = timezone.now()
                    leave.review_remarks = request.POST.get('review_remarks', '')
                
                leave.full_clean()
                leave.save()
                
                message = f'Leave application for {staff.get_full_name()} updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_leave_detail', args=[leave.pk]),
                        'leave': {
                            'id': leave.pk,
                            'staff': staff.get_full_name(),
                            'leave_type': leave.get_leave_type_display(),
                            'start_date': leave.start_date.strftime('%Y-%m-%d'),
                            'end_date': leave.end_date.strftime('%Y-%m-%d'),
                            'duration': leave.duration_days,
                            'status': leave.get_status_display(),
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_detail', pk=leave.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'leave': leave,
                'staff_members': staff_members,
                'title': f'Edit Leave Application: {leave.staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })
            
        except Exception as e:
            logger.error(f"Error updating staff leave {pk}: {e}", exc_info=True)
            error_msg = f'Error updating leave application: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            return render(request, self.template_name, {
                'leave': leave,
                'staff_members': staff_members,
                'title': f'Edit Leave Application: {leave.staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
                'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
                'status_choices': StaffLeave.STATUS_CHOICES,
            })
    
    def _get_reviewer_staff(self, user):
        """Get the Staff instance for a user."""
        if not user or not user.is_authenticated:
            return None
        
        try:
            # Try to get staff profile through the user's staff_profile relation
            if hasattr(user, 'staff_profile') and user.staff_profile:
                return user.staff_profile
            
            # If no direct relation, try to find staff by user ID
            staff = Staff.objects.filter(user=user).first()
            if staff:
                return staff
            
            # Create a system staff record if needed? No, just return None
            return None
            
        except Exception as e:
            logger.warning(f"Could not get staff profile for user {user}: {e}")
            return None


class StaffLeaveApproveView(ManagementRequiredMixin, View):
    """View to approve a staff leave application."""
    
    def _get_reviewer_staff(self, user):
        """Get the Staff instance for a user."""
        if not user or not user.is_authenticated:
            return None
        
        try:
            # Try to get staff profile through the user's staff_profile relation
            if hasattr(user, 'staff_profile') and user.staff_profile:
                return user.staff_profile
            
            # If no direct relation, try to find staff by user ID
            staff = Staff.objects.filter(user=user).first()
            if staff:
                return staff
            
            return None
            
        except Exception as e:
            logger.warning(f"Could not get staff profile for user {user}: {e}")
            return None
    
    def post(self, request, pk):
        """Approve a pending leave application."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            leave = get_object_or_404(StaffLeave, pk=pk)
            
            # Validate leave status
            if leave.status != 'pending':
                error_msg = f'Cannot approve a leave that is already {leave.get_status_display().lower()}.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                messages.error(request, error_msg)
                return redirect('management:staff_leave_detail', pk=pk)
            
            # Get reviewer staff
            reviewer = self._get_reviewer_staff(request.user)
            
            if not reviewer:
                error_msg = 'Unable to determine reviewer. Please ensure your user account is linked to a staff profile.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                messages.error(request, error_msg)
                return redirect('management:staff_leave_detail', pk=pk)
            
            with transaction.atomic():
                leave.status = 'approved'
                leave.reviewed_by = reviewer
                leave.reviewed_at = timezone.now()
                leave.review_remarks = request.POST.get('review_remarks', '').strip()
                
                # Validate the leave before saving
                leave.full_clean()
                leave.save()
                
                message = f'Leave application for {leave.staff.get_full_name()} has been approved.'
                message += f'\n\nLeave Period: {leave.start_date} to {leave.end_date} ({leave.duration_days} days)'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_detail', pk=leave.pk)
                
        except ValidationError as e:
            error_msg = str(e)
            if hasattr(e, 'message_dict'):
                error_msg = '; '.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
            
            logger.error(f"Validation error approving staff leave {pk}: {error_msg}")
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': f'Error approving leave: {error_msg}'
                }, status=400)
            
            messages.error(request, f'Error approving leave: {error_msg}')
            return redirect('management:staff_leave_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error approving staff leave {pk}: {e}", exc_info=True)
            error_msg = f'Error approving leave: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)


class StaffLeaveRejectView(ManagementRequiredMixin, View):
    """View to reject a staff leave application."""
    
    def _get_reviewer_staff(self, user):
        """Get the Staff instance for a user."""
        if not user or not user.is_authenticated:
            return None
        
        try:
            # Try to get staff profile through the user's staff_profile relation
            if hasattr(user, 'staff_profile') and user.staff_profile:
                return user.staff_profile
            
            # If no direct relation, try to find staff by user ID
            staff = Staff.objects.filter(user=user).first()
            if staff:
                return staff
            
            return None
            
        except Exception as e:
            logger.warning(f"Could not get staff profile for user {user}: {e}")
            return None
    
    def post(self, request, pk):
        """Reject a pending leave application."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            leave = get_object_or_404(StaffLeave, pk=pk)
            
            # Validate leave status
            if leave.status != 'pending':
                error_msg = f'Cannot reject a leave that is already {leave.get_status_display().lower()}.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                messages.error(request, error_msg)
                return redirect('management:staff_leave_detail', pk=pk)
            
            # Get review remarks
            review_remarks = request.POST.get('review_remarks', '').strip()
            
            if not review_remarks:
                error_msg = 'Please provide a reason for rejection.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                messages.error(request, error_msg)
                return redirect('management:staff_leave_detail', pk=pk)
            
            # Get reviewer staff
            reviewer = self._get_reviewer_staff(request.user)
            
            if not reviewer:
                error_msg = 'Unable to determine reviewer. Please ensure your user account is linked to a staff profile.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg
                    }, status=400)
                messages.error(request, error_msg)
                return redirect('management:staff_leave_detail', pk=pk)
            
            with transaction.atomic():
                leave.status = 'rejected'
                leave.reviewed_by = reviewer
                leave.reviewed_at = timezone.now()
                leave.review_remarks = review_remarks
                
                # Validate the leave before saving
                leave.full_clean()
                leave.save()
                
                message = f'Leave application for {leave.staff.get_full_name()} has been rejected.'
                if leave.review_remarks:
                    message += f'\n\nReason: {leave.review_remarks}'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_detail', pk=leave.pk)
                
        except ValidationError as e:
            error_msg = str(e)
            if hasattr(e, 'message_dict'):
                error_msg = '; '.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
            
            logger.error(f"Validation error rejecting staff leave {pk}: {error_msg}")
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': f'Error rejecting leave: {error_msg}'
                }, status=400)
            
            messages.error(request, f'Error rejecting leave: {error_msg}')
            return redirect('management:staff_leave_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error rejecting staff leave {pk}: {e}", exc_info=True)
            error_msg = f'Error rejecting leave: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)


class StaffLeaveCancelView(ManagementRequiredMixin, View):
    """View to cancel a pending leave application."""
    
    def post(self, request, pk):
        """Cancel a pending leave application."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        leave = get_object_or_404(StaffLeave, pk=pk)
        
        if leave.status != 'pending':
            error_msg = f'Cannot cancel a leave that is already {leave.get_status_display().lower()}.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)
        
        try:
            with transaction.atomic():
                leave.status = 'cancelled'
                leave.save()
                
                message = f'Leave application for {leave.staff.get_full_name()} has been cancelled.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_detail', pk=leave.pk)
                
        except Exception as e:
            logger.error(f"Error cancelling staff leave {pk}: {e}", exc_info=True)
            error_msg = f'Error cancelling leave: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)


class StaffLeaveDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff leave application."""
    
    def check_dependencies(self, leave):
        """Check if leave can be deleted."""
        if leave.status == 'approved' and leave.start_date <= timezone.now().date():
            return ['Approved leave that has started or is in progress cannot be deleted.']
        return []

    def post(self, request, pk):
        """Handle staff leave deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        leave = get_object_or_404(StaffLeave, pk=pk)
        
        # Check dependencies
        dependencies = self.check_dependencies(leave)
        
        if dependencies:
            error_msg = f'Cannot delete leave application: {", ".join(dependencies)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'has_dependencies': True,
                    'dependencies': dependencies
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)
        
        try:
            with transaction.atomic():
                staff_name = leave.staff.get_full_name()
                leave_type = leave.get_leave_type_display()
                leave_period = f"{leave.start_date} to {leave.end_date}"
                
                leave.delete()
                
                message = f'Leave application for {staff_name} ({leave_type}, {leave_period}) deleted successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_leave_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff leave {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting leave application: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_leave_detail', pk=pk)


class StaffLeaveSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff leaves (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff leaves for autocomplete."""
        term = request.GET.get('term', '').strip()
        staff_id = request.GET.get('staff')
        status = request.GET.get('status')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = StaffLeave.objects.all().select_related('staff')
        
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if term:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(leave_type__icontains=term) |
                Q(reason__icontains=term)
            )
        
        queryset = queryset.order_by('-start_date')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        leaves = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': leave.pk,
                'text': f"{leave.staff.get_full_name()} - {leave.get_leave_type_display()} ({leave.start_date} to {leave.end_date})",
                'staff': leave.staff.get_full_name(),
                'staff_id': leave.staff.pk,
                'leave_type': leave.get_leave_type_display(),
                'start_date': leave.start_date.strftime('%Y-%m-%d'),
                'end_date': leave.end_date.strftime('%Y-%m-%d'),
                'duration': leave.duration_days,
                'status': leave.get_status_display(),
                'status_code': leave.status,
            }
            for leave in leaves
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })


class StaffLeaveCalendarView(ManagementRequiredMixin, View):
    """View to display staff leave calendar."""
    template_name = 'portal_management/hr/leaves/calendar.html'

    def get(self, request):
        """Display staff leave calendar view."""
        # Get year and month from request parameters
        year = request.GET.get('year')
        month = request.GET.get('month')
        
        # Use current year/month if not provided or invalid
        current_date = timezone.now().date()
        
        try:
            if year and month:
                year = int(year)
                month = int(month)
                # Validate month range
                if month < 1 or month > 12:
                    year = current_date.year
                    month = current_date.month
            else:
                year = current_date.year
                month = current_date.month
        except (ValueError, TypeError):
            year = current_date.year
            month = current_date.month
        
        # Get first day of the selected month
        start_date = date(year, month, 1)
        
        # Get last day of the selected month
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        # Get all approved leaves for the selected month (including those that span into the month)
        leaves = StaffLeave.objects.filter(
            status='approved',
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related('staff', 'substitute').order_by('staff__first_name', 'staff__last_name')
        
        # Build calendar grid
        calendar_weeks = []
        current_day = start_date
        
        # Calculate offset for first day (0 = Monday, 6 = Sunday)
        # Adjust to make Sunday the first day of the week
        first_weekday = current_day.weekday()
        start_offset = (first_weekday + 1) % 7  # Days to subtract to get to Sunday
        
        # Add days from previous month to fill the first week
        if start_offset > 0:
            prev_month_date = current_day - timedelta(days=start_offset)
            first_week = []
            for i in range(start_offset):
                day_date = prev_month_date + timedelta(days=i)
                day_leaves = []
                
                # Check if any leave covers this day
                for leave in leaves:
                    if leave.start_date <= day_date <= leave.end_date:
                        day_leaves.append(leave)
                
                first_week.append({
                    'date': day_date,
                    'day': day_date.day,
                    'is_current_month': False,
                    'is_today': day_date == current_date,
                    'leaves': day_leaves
                })
            calendar_weeks.append(first_week)
        
        # Add days of the current month
        week = []
        while current_day <= end_date:
            # Find leaves for this day
            day_leaves = []
            for leave in leaves:
                if leave.start_date <= current_day <= leave.end_date:
                    day_leaves.append(leave)
            
            week.append({
                'date': current_day,
                'day': current_day.day,
                'is_current_month': True,
                'is_today': current_day == current_date,
                'leaves': day_leaves
            })
            
            # When we have 7 days, add the week to calendar_weeks and start a new week
            if len(week) == 7:
                calendar_weeks.append(week)
                week = []
            
            current_day += timedelta(days=1)
        
        # Add remaining days of the last week
        if week:
            calendar_weeks.append(week)
        
        # Fill the last week with days from next month if needed
        if calendar_weeks and len(calendar_weeks[-1]) < 7:
            remaining = 7 - len(calendar_weeks[-1])
            next_month_date = end_date + timedelta(days=1)
            for i in range(remaining):
                day_date = next_month_date + timedelta(days=i)
                day_leaves = []
                
                # Check if any leave covers this day (for leaves that extend into next month)
                for leave in leaves:
                    if leave.start_date <= day_date <= leave.end_date:
                        day_leaves.append(leave)
                
                calendar_weeks[-1].append({
                    'date': day_date,
                    'day': day_date.day,
                    'is_current_month': False,
                    'is_today': day_date == current_date,
                    'leaves': day_leaves
                })
        
        # Group leaves by staff for the sidebar
        staff_leaves = {}
        for leave in leaves:
            staff_id = leave.staff_id
            if staff_id not in staff_leaves:
                staff_leaves[staff_id] = {
                    'staff': leave.staff,
                    'leaves': []
                }
            staff_leaves[staff_id]['leaves'].append(leave)
        
        # Sort staff leaves by name
        staff_leaves_list = sorted(staff_leaves.values(), key=lambda x: x['staff'].get_full_name())
        
        # Calculate previous and next month dates for navigation
        if month == 1:
            previous_month = date(year - 1, 12, 1)
        else:
            previous_month = date(year, month - 1, 1)
        
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        
        # Prepare leave data for the template with all required attributes
        # This ensures each leave has all the data attributes the template expects
        for week in calendar_weeks:
            for day in week:
                for leave in day['leaves']:
                    # Add additional attributes that the template expects
                    leave.get_leave_type_display_cached = leave.get_leave_type_display()
                    # The template expects these data attributes to be available via JavaScript
                    # They will be rendered in the HTML attributes
        
        # Also prepare staff leaves list with additional data
        staff_leaves_with_details = []
        for staff_data in staff_leaves_list:
            staff_leaves_with_details.append({
                'staff': staff_data['staff'],
                'leaves': staff_data['leaves'],
                'leave_count': len(staff_data['leaves'])
            })
        
        context = {
            'calendar_weeks': calendar_weeks,
            'staff_leaves': staff_leaves_with_details,
            'current_month': start_date,
            'previous_month': previous_month,
            'next_month': next_month,
            'year': year,
            'month': month,
            'leave_type_choices': StaffLeave.LEAVE_TYPE_CHOICES,
            'today': current_date,
        }
        
        return render(request, self.template_name, context)