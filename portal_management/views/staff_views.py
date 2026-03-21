# portal_management/views/staff_views.py

import logging
from datetime import date, datetime, timedelta
import re
from django.db import transaction
from django.contrib import messages
from django.db import models
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from core.mixins import ManagementRequiredMixin
from core.models import AcademicYear, ClassLevel, ClassTeacherAssignment, Staff, CustomUser, StaffRole, StaffRoleAssignment, StaffTeachingAssignment, StreamClass, Subject, UserType, Department, StaffDepartmentAssignment
from django.core.cache import cache
from django.utils.timesince import timesince

User = get_user_model()
logger = logging.getLogger(__name__)


class StaffListView(ManagementRequiredMixin, View):
    """View to list all staff members with filtering and search."""
    template_name = 'portal_management/staff/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = Staff.objects.all().select_related('user')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(middle_name__icontains=search) |
                Q(employee_id__icontains=search) |
                Q(phone_number__icontains=search)
            )
        
        # Employment type filter
        employment_type = request.GET.get('employment_type')
        if employment_type:
            queryset = queryset.filter(employment_type=employment_type)
        
        # Gender filter
        gender = request.GET.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)
        
        # Has user account filter
        has_user = request.GET.get('has_user')
        if has_user == 'yes':
            queryset = queryset.filter(user__isnull=False)
        elif has_user == 'no':
            queryset = queryset.filter(user__isnull=True)
        
        # Department filter (through assignments)
        department_id = request.GET.get('department')
        if department_id:
            queryset = queryset.filter(
                department_assignments__department_id=department_id,
                department_assignments__is_active=True
            ).distinct()
        
        return queryset.order_by('first_name', 'last_name')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        with_user_account = queryset.filter(user__isnull=False).count()
        without_user_account = queryset.filter(user__isnull=True).count()
        permanent_staff = queryset.filter(employment_type='permanent').count()
        contract_staff = queryset.filter(employment_type='contract').count()
        
        return {
            'total_staff': total,
            'with_user_account': with_user_account,
            'without_user_account': without_user_account,
            'permanent_staff': permanent_staff,
            'contract_staff': contract_staff,
        }

    def get(self, request):
        """Handle GET request - display staff list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        staff_members = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get departments for filter
        departments = Department.objects.all().order_by('name')
        
        context = {
            'staff_members': staff_members,
            'departments': departments,
            'total_staff': total_count,
            'with_user_account': queryset.filter(user__isnull=False).count(),
            'without_user_account': queryset.filter(user__isnull=True).count(),
            'permanent_staff': queryset.filter(employment_type='permanent').count(),
            'contract_staff': queryset.filter(employment_type='contract').count(),
            'search_query': request.GET.get('search', ''),
            'selected_employment_type': request.GET.get('employment_type', ''),
            'selected_gender': request.GET.get('gender', ''),
            'selected_has_user': request.GET.get('has_user', ''),
            'selected_department': request.GET.get('department', ''),
            'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            'gender_choices': Staff.GENDER_CHOICES,
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)





class StaffCreateView(ManagementRequiredMixin, View):
    """View to create a new staff member."""
    template_name = 'portal_management/staff/form.html'

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

    def _convert_to_date(self, date_string):
        """Convert string date to date object."""
        if not date_string:
            return None
        try:
            return datetime.strptime(date_string, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def _validate_password(self, password):
        """Validate password strength."""
        errors = []
        
        if len(password) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        if not re.search(r'[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter.')
        
        if not re.search(r'[a-z]', password):
            errors.append('Password must contain at least one lowercase letter.')
        
        if not re.search(r'[0-9]', password):
            errors.append('Password must contain at least one number.')
        
        return errors

    def _validate_staff_data(self, data):
        """Validate staff data before saving."""
        errors = {}
        
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        gender = data.get('gender')
        phone_number = data.get('phone_number', '').strip()
        employment_type = data.get('employment_type')
        joining_date_str = data.get('joining_date')
        date_of_birth_str = data.get('date_of_birth')
        create_user_account = data.get('create_user_account') == 'true'
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        
        # Convert dates
        joining_date = self._convert_to_date(joining_date_str)
        date_of_birth = self._convert_to_date(date_of_birth_str)
        today = timezone.now().date()
        
        # Validate name fields
        if not first_name and not last_name:
            errors['__all__'] = errors.get('__all__', []) + [
                'At least first name or last name is required.'
            ]
        
        # Validate phone number uniqueness
        if phone_number:
            if Staff.objects.filter(phone_number=phone_number).exists():
                errors['phone_number'] = ['Staff member with this phone number already exists.']
        
        # Validate joining date
        if joining_date:
            if joining_date > today:
                errors['joining_date'] = ['Joining date cannot be in the future.']
        
        # Validate date of birth
        if date_of_birth:
            if date_of_birth > today:
                errors['date_of_birth'] = ['Date of birth cannot be in the future.']
            age = today.year - date_of_birth.year
            # Adjust age if birthday hasn't occurred yet this year
            if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
                age -= 1
            if age < 18:
                errors['date_of_birth'] = ['Staff member must be at least 18 years old.']
            if age > 70:
                errors['date_of_birth'] = ['Staff member cannot be older than 70 years.']
        
        # Validate employment type
        valid_employment_types = [et[0] for et in Staff.EMPLOYMENT_TYPE_CHOICES]
        if employment_type and employment_type not in valid_employment_types:
            errors['employment_type'] = ['Invalid employment type selected.']
        
        # Validate user account data if creating
        if create_user_account:
            if not username:
                errors['username'] = ['Username is required when creating a user account.']
            elif User.objects.filter(username=username).exists():
                errors['username'] = ['Username already exists. Please choose a different username.']
            
            if email:
                if User.objects.filter(email=email).exists():
                    errors['email'] = ['Email already exists. Please use a different email address.']
            
            if not password:
                errors['password'] = ['Password is required when creating a user account.']
            else:
                password_errors = self._validate_password(password)
                if password_errors:
                    errors['password'] = password_errors
            
            if password != confirm_password:
                errors['confirm_password'] = ['Passwords do not match.']
        
        return errors

    def get(self, request):
        """Display the create staff form."""
        departments = Department.objects.all().order_by('name')
        context = {
            'departments': departments,
            'title': 'Create Staff Member',
            'is_edit': False,
            'staff': None,
            'gender_choices': Staff.GENDER_CHOICES,
            'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
            'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        middle_name = request.POST.get('middle_name', '').strip()
        gender = request.POST.get('gender')
        date_of_birth = request.POST.get('date_of_birth')
        phone_number = request.POST.get('phone_number', '').strip()
        marital_status = request.POST.get('marital_status')
        employment_type = request.POST.get('employment_type')
        work_place = request.POST.get('work_place', '').strip()
        joining_date = request.POST.get('joining_date')
        create_user_account = request.POST.get('create_user_account') == 'true'
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        department_ids = request.POST.getlist('departments')
        
        # Validate data
        errors = self._validate_staff_data(request.POST)
        
        # Validate departments
        if not department_ids:
            errors['departments'] = errors.get('departments', []) + ['At least one department assignment is required.']
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'username' in errors:
                    message = errors['username'][0]
                elif 'password' in errors:
                    message = errors['password'][0]
                elif 'phone_number' in errors:
                    message = errors['phone_number'][0]
                elif 'joining_date' in errors:
                    message = errors['joining_date'][0]
                elif 'date_of_birth' in errors:
                    message = errors['date_of_birth'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'departments': departments,
                'title': 'Create Staff Member',
                'is_edit': False,
                'staff': None,
                'form_data': request.POST,
                'errors': errors,
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })
        
        try:
            with transaction.atomic():
                # Create user account if requested
                user = None
                if create_user_account:
                    user = User.objects.create_user(
                        username=username,
                        email=email if email else '',
                        password=password,
                        user_type=UserType.STAFF,
                        first_name=first_name,
                        last_name=last_name,
                        is_active=True
                    )
                
                # Create staff member
                staff = Staff(
                    user=user,
                    first_name=first_name,
                    last_name=last_name,
                    middle_name=middle_name,
                    gender=gender,
                    date_of_birth=date_of_birth if date_of_birth else None,
                    phone_number=phone_number,
                    marital_status=marital_status,
                    employment_type=employment_type,
                    work_place=work_place,
                    joining_date=joining_date if joining_date else None,
                )
                staff.full_clean()
                staff.save()
                
                # Assign departments
                for dept_id in department_ids:
                    department = Department.objects.get(pk=dept_id)
                    StaffDepartmentAssignment.objects.create(
                        staff=staff,
                        department=department,
                        start_date=timezone.now().date(),
                        is_active=True,
                        remarks='Initial assignment'
                    )
                
                # Build success message
                message = f'Staff member "{staff.get_full_name()}" created successfully!'
                if create_user_account:
                    message += f'\n\nUser Account Details:\n'
                    message += f'Username: {username}\n'
                    message += f'Password: {password}\n'
                    message += f'Email: {email if email else "Not provided"}\n'
                    message += f'\nPlease provide these credentials to the staff member. They will be prompted to change their password on first login.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_detail', args=[staff.pk]),
                        'staff': {
                            'id': staff.pk,
                            'name': staff.get_full_name(),
                            'employee_id': staff.employee_id,
                            'phone_number': staff.phone_number,
                            'has_user_account': user is not None,
                            'username': username if user else None,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_detail', pk=staff.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'departments': departments,
                'title': 'Create Staff Member',
                'is_edit': False,
                'staff': None,
                'form_data': request.POST,
                'errors': formatted_errors,
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff: {e}", exc_info=True)
            error_msg = f'Error creating staff: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'departments': departments,
                'title': 'Create Staff Member',
                'is_edit': False,
                'staff': None,
                'form_data': request.POST,
                'errors': [error_msg],
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })


class StaffUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff member."""
    template_name = 'portal_management/staff/form.html'

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

    def _convert_to_date(self, date_string):
        """Convert string date to date object."""
        if not date_string:
            return None
        try:
            return datetime.strptime(date_string, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    def _validate_password(self, password):
        """Validate password strength."""
        errors = []
        
        if len(password) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        if not re.search(r'[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter.')
        
        if not re.search(r'[a-z]', password):
            errors.append('Password must contain at least one lowercase letter.')
        
        if not re.search(r'[0-9]', password):
            errors.append('Password must contain at least one number.')
        
        return errors

    def _validate_staff_data(self, data, staff_id=None):
        """Validate staff data before saving."""
        errors = {}
        
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        phone_number = data.get('phone_number', '').strip()
        employment_type = data.get('employment_type')
        joining_date_str = data.get('joining_date')
        date_of_birth_str = data.get('date_of_birth')
        update_user_account = data.get('update_user_account') == 'true'
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        new_password = data.get('new_password', '')
        
        # Convert dates
        joining_date = self._convert_to_date(joining_date_str)
        date_of_birth = self._convert_to_date(date_of_birth_str)
        today = timezone.now().date()
        
        # Validate name fields
        if not first_name and not last_name:
            errors['__all__'] = errors.get('__all__', []) + [
                'At least first name or last name is required.'
            ]
        
        # Validate phone number uniqueness (excluding current staff)
        if phone_number:
            if Staff.objects.exclude(pk=staff_id).filter(phone_number=phone_number).exists():
                errors['phone_number'] = ['Staff member with this phone number already exists.']
        
        # Validate joining date
        if joining_date:
            if joining_date > today:
                errors['joining_date'] = ['Joining date cannot be in the future.']
        
        # Validate date of birth
        if date_of_birth:
            if date_of_birth > today:
                errors['date_of_birth'] = ['Date of birth cannot be in the future.']
            age = today.year - date_of_birth.year
            # Adjust age if birthday hasn't occurred yet this year
            if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
                age -= 1
            if age < 18:
                errors['date_of_birth'] = ['Staff member must be at least 18 years old.']
            if age > 70:
                errors['date_of_birth'] = ['Staff member cannot be older than 70 years.']
        
        # Validate user account data if updating
        if update_user_account:
            if not username:
                errors['username'] = ['Username is required when updating user account.']
            elif staff_id:
                staff = Staff.objects.get(pk=staff_id)
                if staff.user and staff.user.username != username:
                    if User.objects.filter(username=username).exists():
                        errors['username'] = ['Username already exists. Please choose a different username.']
            
            if email:
                staff = Staff.objects.get(pk=staff_id)
                if staff.user and staff.user.email != email:
                    if User.objects.filter(email=email).exists():
                        errors['email'] = ['Email already exists. Please use a different email address.']
            
            if new_password:
                password_errors = self._validate_password(new_password)
                if password_errors:
                    errors['new_password'] = password_errors
        
        return errors

    def get(self, request, pk):
        """Display the edit staff form."""
        staff = get_object_or_404(Staff, pk=pk)
        departments = Department.objects.all().order_by('name')
        
        # Get current department assignments
        current_departments = staff.department_assignments.filter(
            is_active=True
        ).values_list('department_id', flat=True)
        
        context = {
            'staff': staff,
            'departments': departments,
            'current_departments': list(current_departments),
            'title': f'Edit Staff: {staff.get_full_name()}',
            'is_edit': True,
            'gender_choices': Staff.GENDER_CHOICES,
            'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
            'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        staff = get_object_or_404(Staff, pk=pk)
        
        # Get form data
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        middle_name = request.POST.get('middle_name', '').strip()
        gender = request.POST.get('gender')
        date_of_birth = request.POST.get('date_of_birth')
        phone_number = request.POST.get('phone_number', '').strip()
        marital_status = request.POST.get('marital_status')
        employment_type = request.POST.get('employment_type')
        work_place = request.POST.get('work_place', '').strip()
        joining_date = request.POST.get('joining_date')
        update_user_account = request.POST.get('update_user_account') == 'true'
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        new_password = request.POST.get('new_password', '')
        department_ids = request.POST.getlist('departments')
        
        # Validate data
        errors = self._validate_staff_data(request.POST, staff.pk)
        
        # Validate departments
        if not department_ids:
            errors['departments'] = errors.get('departments', []) + ['At least one department assignment is required.']
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'username' in errors:
                    message = errors['username'][0]
                elif 'new_password' in errors:
                    message = errors['new_password'][0]
                elif 'phone_number' in errors:
                    message = errors['phone_number'][0]
                elif 'joining_date' in errors:
                    message = errors['joining_date'][0]
                elif 'date_of_birth' in errors:
                    message = errors['date_of_birth'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            departments = Department.objects.all().order_by('name')
            current_departments = staff.department_assignments.filter(is_active=True).values_list('department_id', flat=True)
            return render(request, self.template_name, {
                'staff': staff,
                'departments': departments,
                'current_departments': list(current_departments),
                'title': f'Edit Staff: {staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })
        
        try:
            with transaction.atomic():
                # Update staff information
                staff.first_name = first_name
                staff.last_name = last_name
                staff.middle_name = middle_name
                staff.gender = gender
                staff.date_of_birth = date_of_birth if date_of_birth else None
                staff.phone_number = phone_number
                staff.marital_status = marital_status
                staff.employment_type = employment_type
                staff.work_place = work_place
                staff.joining_date = joining_date if joining_date else None
                
                # Update or create user account
                user_updated = False
                if update_user_account:
                    if staff.user:
                        # Update existing user
                        staff.user.username = username
                        staff.user.email = email if email else ''
                        staff.user.first_name = first_name
                        staff.user.last_name = last_name
                        
                        if new_password:
                            staff.user.set_password(new_password)
                            user_updated = True
                        
                        staff.user.save()
                    else:
                        # Create new user account
                        staff.user = User.objects.create_user(
                            username=username,
                            email=email if email else '',
                            password=new_password if new_password else User.objects.make_random_password(),
                            user_type=UserType.STAFF,
                            first_name=first_name,
                            last_name=last_name,
                            is_active=True
                        )
                        user_updated = True
                
                staff.full_clean()
                staff.save()
                
                # Update department assignments
                # Deactivate current assignments that are no longer selected
                staff.department_assignments.filter(is_active=True).exclude(
                    department_id__in=department_ids
                ).update(is_active=False, end_date=timezone.now().date())
                
                # Create new assignments for newly selected departments
                current_active = staff.department_assignments.filter(
                    is_active=True
                ).values_list('department_id', flat=True)
                
                for dept_id in department_ids:
                    if int(dept_id) not in current_active:
                        StaffDepartmentAssignment.objects.create(
                            staff=staff,
                            department_id=dept_id,
                            start_date=timezone.now().date(),
                            is_active=True,
                            remarks='Department assignment updated'
                        )
                
                # Build success message
                message = f'Staff member "{staff.get_full_name()}" updated successfully!'
                if update_user_account and staff.user:
                    if user_updated and new_password:
                        message += f'\n\nUser Account Updated:\n'
                        message += f'Username: {username}\n'
                        message += f'New Password: {new_password}\n'
                        message += f'Email: {email if email else "Not provided"}\n'
                        message += f'\nPlease provide these new credentials to the staff member.'
                    elif not staff.user:
                        message += f'\n\nUser Account Created:\n'
                        message += f'Username: {username}\n'
                        message += f'Email: {email if email else "Not provided"}\n'
                        message += f'\nPlease provide these credentials to the staff member.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_detail', args=[staff.pk]),
                        'staff': {
                            'id': staff.pk,
                            'name': staff.get_full_name(),
                            'employee_id': staff.employee_id,
                            'phone_number': staff.phone_number,
                            'has_user_account': staff.user is not None,
                            'username': staff.user.username if staff.user else None,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_detail', pk=staff.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            departments = Department.objects.all().order_by('name')
            current_departments = staff.department_assignments.filter(is_active=True).values_list('department_id', flat=True)
            return render(request, self.template_name, {
                'staff': staff,
                'departments': departments,
                'current_departments': list(current_departments),
                'title': f'Edit Staff: {staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })
            
        except Exception as e:
            logger.error(f"Error updating staff {pk}: {e}", exc_info=True)
            error_msg = f'Error updating staff: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            departments = Department.objects.all().order_by('name')
            current_departments = staff.department_assignments.filter(is_active=True).values_list('department_id', flat=True)
            return render(request, self.template_name, {
                'staff': staff,
                'departments': departments,
                'current_departments': list(current_departments),
                'title': f'Edit Staff: {staff.get_full_name()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
                'gender_choices': Staff.GENDER_CHOICES,
                'marital_status_choices': Staff.MARITAL_STATUS_CHOICES,
                'employment_type_choices': Staff.EMPLOYMENT_TYPE_CHOICES,
            })


class StaffDetailView(ManagementRequiredMixin, View):
    """View to display staff details."""
    template_name = 'portal_management/staff/detail.html'

    def get(self, request, pk):
        """Display staff details."""
        staff = get_object_or_404(Staff, pk=pk)
        
        # Get department assignments
        department_assignments = staff.department_assignments.filter(is_active=True).select_related('department')
        
        # Get role assignments
        role_assignments = staff.role_assignments.filter(is_active=True).select_related('role')
        
        # Get teaching assignments (if staff is a teacher)
        teaching_assignments = staff.teaching_assignments.filter(
            academic_year__is_active=True
        ).select_related('subject', 'class_level', 'stream_class', 'academic_year')
        
        # Calculate age
        age = None
        if staff.date_of_birth:
            today = timezone.now().date()
            age = today.year - staff.date_of_birth.year
            if (today.month, today.day) < (staff.date_of_birth.month, staff.date_of_birth.day):
                age -= 1
        
        context = {
            'staff': staff,
            'department_assignments': department_assignments,
            'role_assignments': role_assignments,
            'teaching_assignments': teaching_assignments,
            'age': age,
        }
        return render(request, self.template_name, context)
    

class StaffDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff member."""
    
    def check_dependencies(self, staff):
        """Check if staff has dependencies that prevent deletion."""
        dependencies = []
        
        # Check for department assignments
        dept_count = staff.department_assignments.filter(is_active=True).count()
        if dept_count > 0:
            dependencies.append(f'{dept_count} active department assignment(s)')
        
        # Check for role assignments
        role_count = staff.role_assignments.filter(is_active=True).count()
        if role_count > 0:
            dependencies.append(f'{role_count} active role assignment(s)')
        
        # Check for teaching assignments
        teaching_count = staff.teaching_assignments.filter(
            academic_year__is_active=True
        ).count()
        if teaching_count > 0:
            dependencies.append(f'{teaching_count} active teaching assignment(s)')
        
        # Check for class teacher assignments
        class_teacher_count = staff.class_teacher_assignments.filter(
            academic_year__is_active=True,
            is_active=True
        ).count()
        if class_teacher_count > 0:
            dependencies.append(f'{class_teacher_count} active class teacher assignment(s)')
        
        return dependencies

    def post(self, request, pk):
        """Handle staff deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        staff = get_object_or_404(Staff, pk=pk)
        staff_name = staff.get_full_name()
        
        # Check for dependencies
        dependencies = self.check_dependencies(staff)
        
        if dependencies:
            error_msg = (
                f'Cannot delete "{staff_name}" because they have associated {", ".join(dependencies)}. '
                f'Please remove these associations first.'
            )
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'has_dependencies': True,
                    'dependencies': dependencies
                }, status=400)
            
            messages.error(request, error_msg)
            return redirect('management:staff_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # If staff has a user account, deactivate it but don't delete
                if staff.user:
                    staff.user.is_active = False
                    staff.user.save()
                
                staff.delete()
            
            message = f'Staff member "{staff_name}" deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:staff_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting staff: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_detail', pk=pk)


class StaffCheckDependenciesView(ManagementRequiredMixin, View):
    """AJAX view to check if a staff member has dependencies."""
    
    def get(self, request, pk):
        """Return dependency information for a staff member."""
        staff = get_object_or_404(Staff, pk=pk)
        
        dependencies = []
        
        # Check for department assignments
        dept_count = staff.department_assignments.filter(is_active=True).count()
        if dept_count > 0:
            dependencies.append(f'{dept_count} active department assignment(s)')
        
        # Check for role assignments
        role_count = staff.role_assignments.filter(is_active=True).count()
        if role_count > 0:
            dependencies.append(f'{role_count} active role assignment(s)')
        
        # Check for teaching assignments
        teaching_count = staff.teaching_assignments.filter(
            academic_year__is_active=True
        ).count()
        if teaching_count > 0:
            dependencies.append(f'{teaching_count} active teaching assignment(s)')
        
        return JsonResponse({
            'has_dependencies': len(dependencies) > 0,
            'dependencies': dependencies,
            'staff_id': staff.pk,
            'staff_name': staff.get_full_name(),
        })


class StaffSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff members (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff members for autocomplete."""
        term = request.GET.get('term', '').strip()
        department_id = request.GET.get('department')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = Staff.objects.all()
        
        if department_id:
            queryset = queryset.filter(
                department_assignments__department_id=department_id,
                department_assignments__is_active=True
            )
        
        if term:
            queryset = queryset.filter(
                Q(first_name__icontains=term) |
                Q(last_name__icontains=term) |
                Q(middle_name__icontains=term) |
                Q(employee_id__icontains=term) |
                Q(phone_number__icontains=term)
            )
        
        queryset = queryset.order_by('first_name', 'last_name')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        staff_members = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': staff.pk,
                'text': f"{staff.get_full_name()} ({staff.employee_id})",
                'name': staff.get_full_name(),
                'employee_id': staff.employee_id,
                'phone_number': staff.phone_number,
                'employment_type': staff.get_employment_type_display(),
            }
            for staff in staff_members
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })



class StaffRoleListView(ManagementRequiredMixin, View):
    """View to list all staff roles with filtering and search."""
    template_name = 'portal_management/hr/roles/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = StaffRole.objects.all().select_related('group')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Portal category filter
        portal_category = request.GET.get('portal_category')
        if portal_category:
            queryset = queryset.filter(portal_category=portal_category)
        
        # Has group filter
        has_group = request.GET.get('has_group')
        if has_group == 'yes':
            queryset = queryset.filter(group__isnull=False)
        elif has_group == 'no':
            queryset = queryset.filter(group__isnull=True)
        
        return queryset.order_by('name')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        with_group = queryset.filter(group__isnull=False).count()
        without_group = queryset.filter(group__isnull=True).count()
        
        # Count by portal categories
        portal_stats = {}
        for portal_code, portal_name in StaffRole.PORTAL_CHOICES:
            portal_stats[portal_code] = queryset.filter(portal_category=portal_code).count()
        
        return {
            'total_roles': total,
            'with_group': with_group,
            'without_group': without_group,
            'portal_stats': portal_stats,
        }

    def get(self, request):
        """Handle GET request - display staff role list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        roles = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        context = {
            'roles': roles,
            'total_roles': total_count,
            'with_group': queryset.filter(group__isnull=False).count(),
            'without_group': queryset.filter(group__isnull=True).count(),
            'portal_choices': StaffRole.PORTAL_CHOICES,
            'search_query': request.GET.get('search', ''),
            'selected_portal_category': request.GET.get('portal_category', ''),
            'selected_has_group': request.GET.get('has_group', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class StaffRoleCreateView(ManagementRequiredMixin, View):
    """View to create a new staff role."""
    template_name = 'portal_management/hr/roles/form.html'

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

    def _validate_role_data(self, data):
        """Validate staff role data before saving."""
        errors = {}
        
        name = data.get('name', '').strip()
        portal_category = data.get('portal_category')
        group_name = data.get('group_name', '').strip()
        create_group = data.get('create_group') == 'true'
        
        # Validate name
        if not name:
            errors['name'] = ['Role name is required.']
        elif StaffRole.objects.filter(name__iexact=name).exists():
            errors['name'] = ['A role with this name already exists.']
        
        # Validate portal category
        valid_portal_categories = [pc[0] for pc in StaffRole.PORTAL_CHOICES]
        if portal_category and portal_category not in valid_portal_categories:
            errors['portal_category'] = ['Invalid portal category selected.']
        
        # Validate group creation
        if create_group:
            if not group_name:
                errors['group_name'] = ['Group name is required when creating a new group.']
            elif Group.objects.filter(name=group_name).exists():
                errors['group_name'] = ['A group with this name already exists.']
        
        return errors

    def get(self, request):
        """Display the create staff role form."""
        context = {
            'title': 'Create Staff Role',
            'is_edit': False,
            'role': None,
            'portal_choices': StaffRole.PORTAL_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff role form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        portal_category = request.POST.get('portal_category')
        create_group = request.POST.get('create_group') == 'true'
        group_name = request.POST.get('group_name', '').strip()
        
        # Validate data
        errors = self._validate_role_data(request.POST)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if 'name' in errors:
                    message = errors['name'][0]
                elif 'portal_category' in errors:
                    message = errors['portal_category'][0]
                elif 'group_name' in errors:
                    message = errors['group_name'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            return render(request, self.template_name, {
                'title': 'Create Staff Role',
                'is_edit': False,
                'role': None,
                'form_data': request.POST,
                'errors': errors,
                'portal_choices': StaffRole.PORTAL_CHOICES,
            })
        
        try:
            with transaction.atomic():
                # Create group if requested
                group = None
                if create_group:
                    group = Group.objects.create(name=group_name)
                
                # Create staff role
                role = StaffRole(
                    name=name,
                    description=description,
                    portal_category=portal_category,
                    group=group
                )
                role.full_clean()
                role.save()
                
                message = f'Staff role "{role.name}" created successfully!'
                if create_group:
                    message += f'\n\nGroup "{group_name}" was also created and linked to this role.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_role_detail', args=[role.pk]),
                        'role': {
                            'id': role.pk,
                            'name': role.name,
                            'portal_category': role.get_portal_category_display(),
                            'has_group': group is not None,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_detail', pk=role.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            return render(request, self.template_name, {
                'title': 'Create Staff Role',
                'is_edit': False,
                'role': None,
                'form_data': request.POST,
                'errors': formatted_errors,
                'portal_choices': StaffRole.PORTAL_CHOICES,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff role: {e}", exc_info=True)
            error_msg = f'Error creating staff role: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            return render(request, self.template_name, {
                'title': 'Create Staff Role',
                'is_edit': False,
                'role': None,
                'form_data': request.POST,
                'errors': [error_msg],
                'portal_choices': StaffRole.PORTAL_CHOICES,
            })


class StaffRoleDetailView(ManagementRequiredMixin, View):
    """View to display staff role details."""
    template_name = 'portal_management/hr/roles/detail.html'

    def get(self, request, pk):
        """Display staff role details."""
        role = get_object_or_404(StaffRole, pk=pk)
        
        # Get staff members assigned to this role
        staff_assignments = StaffRoleAssignment.objects.filter(
            role=role,
            is_active=True
        ).select_related('staff', 'staff__user')[:20]
        
        # Get count of active assignments
        active_assignments_count = StaffRoleAssignment.objects.filter(
            role=role,
            is_active=True
        ).count()
        
        context = {
            'role': role,
            'staff_assignments': staff_assignments,
            'active_assignments_count': active_assignments_count,
            'portal_choices': StaffRole.PORTAL_CHOICES,
        }
        return render(request, self.template_name, context)


class StaffRoleUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff role."""
    template_name = 'portal_management/hr/roles/form.html'

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

    def _validate_role_data(self, data, role_id=None):
        """Validate staff role data before saving."""
        errors = {}
        
        name = data.get('name', '').strip()
        portal_category = data.get('portal_category')
        group_action = data.get('group_action')
        new_group_name = data.get('new_group_name', '').strip()
        
        # Validate name
        if not name:
            errors['name'] = ['Role name is required.']
        elif StaffRole.objects.exclude(pk=role_id).filter(name__iexact=name).exists():
            errors['name'] = ['A role with this name already exists.']
        
        # Validate portal category
        valid_portal_categories = [pc[0] for pc in StaffRole.PORTAL_CHOICES]
        if portal_category and portal_category not in valid_portal_categories:
            errors['portal_category'] = ['Invalid portal category selected.']
        
        # Validate group actions
        if group_action == 'create':
            if not new_group_name:
                errors['new_group_name'] = ['Group name is required when creating a new group.']
            elif Group.objects.filter(name=new_group_name).exists():
                errors['new_group_name'] = ['A group with this name already exists.']
        elif group_action == 'link' and not role_id:
            # Check if group exists (would be handled by select)
            pass
        
        return errors

    def get(self, request, pk):
        """Display the edit staff role form."""
        role = get_object_or_404(StaffRole, pk=pk)
        
        # Get all available groups
        available_groups = Group.objects.all().order_by('name')
        
        context = {
            'role': role,
            'title': f'Edit Staff Role: {role.name}',
            'is_edit': True,
            'portal_choices': StaffRole.PORTAL_CHOICES,
            'available_groups': available_groups,
            'has_group': role.group is not None,
            'group_name': role.group.name if role.group else '',
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff role form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        role = get_object_or_404(StaffRole, pk=pk)
        
        # Get form data
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        portal_category = request.POST.get('portal_category')
        group_action = request.POST.get('group_action')
        existing_group_id = request.POST.get('existing_group')
        new_group_name = request.POST.get('new_group_name', '').strip()
        
        # Validate data
        errors = self._validate_role_data(request.POST, role.pk)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if 'name' in errors:
                    message = errors['name'][0]
                elif 'portal_category' in errors:
                    message = errors['portal_category'][0]
                elif 'new_group_name' in errors:
                    message = errors['new_group_name'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            available_groups = Group.objects.all().order_by('name')
            return render(request, self.template_name, {
                'role': role,
                'title': f'Edit Staff Role: {role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
                'portal_choices': StaffRole.PORTAL_CHOICES,
                'available_groups': available_groups,
                'has_group': role.group is not None,
                'group_name': role.group.name if role.group else '',
            })
        
        try:
            with transaction.atomic():
                # Update role basic info
                role.name = name
                role.description = description
                role.portal_category = portal_category
                
                # Handle group changes
                if group_action == 'keep':
                    # Keep existing group
                    pass
                elif group_action == 'remove':
                    # Remove group link
                    role.group = None
                elif group_action == 'link':
                    # Link to existing group
                    if existing_group_id:
                        role.group = Group.objects.get(pk=existing_group_id)
                elif group_action == 'create':
                    # Create new group
                    if new_group_name:
                        new_group = Group.objects.create(name=new_group_name)
                        role.group = new_group
                
                role.full_clean()
                role.save()
                
                message = f'Staff role "{role.name}" updated successfully!'
                
                if group_action == 'create' and new_group_name:
                    message += f'\n\nGroup "{new_group_name}" was created and linked to this role.'
                elif group_action == 'remove':
                    message += f'\n\nThe linked group was removed from this role.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_role_detail', args=[role.pk]),
                        'role': {
                            'id': role.pk,
                            'name': role.name,
                            'portal_category': role.get_portal_category_display(),
                            'has_group': role.group is not None,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_detail', pk=role.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            available_groups = Group.objects.all().order_by('name')
            return render(request, self.template_name, {
                'role': role,
                'title': f'Edit Staff Role: {role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
                'portal_choices': StaffRole.PORTAL_CHOICES,
                'available_groups': available_groups,
                'has_group': role.group is not None,
                'group_name': role.group.name if role.group else '',
            })
            
        except Exception as e:
            logger.error(f"Error updating staff role {pk}: {e}", exc_info=True)
            error_msg = f'Error updating staff role: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            available_groups = Group.objects.all().order_by('name')
            return render(request, self.template_name, {
                'role': role,
                'title': f'Edit Staff Role: {role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
                'portal_choices': StaffRole.PORTAL_CHOICES,
                'available_groups': available_groups,
                'has_group': role.group is not None,
                'group_name': role.group.name if role.group else '',
            })


class StaffRoleDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff role."""
    
    def check_dependencies(self, role):
        """Check if role has dependencies that prevent deletion."""
        dependencies = []
        
        # Check for active staff assignments
        assignment_count = StaffRoleAssignment.objects.filter(
            role=role,
            is_active=True
        ).count()
        
        if assignment_count > 0:
            dependencies.append(f'{assignment_count} active staff assignment(s)')
        
        return dependencies

    def post(self, request, pk):
        """Handle staff role deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        role = get_object_or_404(StaffRole, pk=pk)
        role_name = role.name
        
        # Check for dependencies
        dependencies = self.check_dependencies(role)
        
        if dependencies:
            error_msg = (
                f'Cannot delete "{role_name}" because it has associated {", ".join(dependencies)}. '
                f'Please remove these associations first.'
            )
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'has_dependencies': True,
                    'dependencies': dependencies
                }, status=400)
            
            messages.error(request, error_msg)
            return redirect('management:staff_role_detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Note: We don't delete the associated group automatically
                # to avoid affecting other systems that might use the group
                role.delete()
            
            message = f'Staff role "{role_name}" deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:staff_role_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff role {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting staff role: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_role_detail', pk=pk)


class StaffRoleCheckDependenciesView(ManagementRequiredMixin, View):
    """AJAX view to check if a staff role has dependencies."""
    
    def get(self, request, pk):
        """Return dependency information for a staff role."""
        role = get_object_or_404(StaffRole, pk=pk)
        
        dependencies = []
        
        # Check for active staff assignments
        assignment_count = StaffRoleAssignment.objects.filter(
            role=role,
            is_active=True
        ).count()
        
        if assignment_count > 0:
            dependencies.append(f'{assignment_count} active staff assignment(s)')
        
        return JsonResponse({
            'has_dependencies': len(dependencies) > 0,
            'dependencies': dependencies,
            'role_id': role.pk,
            'role_name': role.name,
        })


class StaffRoleSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff roles (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff roles for autocomplete."""
        term = request.GET.get('term', '').strip()
        portal_category = request.GET.get('portal_category')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = StaffRole.objects.all()
        
        if portal_category:
            queryset = queryset.filter(portal_category=portal_category)
        
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) |
                Q(description__icontains=term)
            )
        
        queryset = queryset.order_by('name')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        roles = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': role.pk,
                'text': f"{role.name} ({role.get_portal_category_display()})",
                'name': role.name,
                'portal_category': role.portal_category,
                'portal_category_display': role.get_portal_category_display(),
                'has_group': role.group is not None,
            }
            for role in roles
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })


class StaffRoleAssignmentListView(ManagementRequiredMixin, View):
    """View to list all staff role assignments with filtering and search."""
    template_name = 'portal_management/hr/role_assignments/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = StaffRoleAssignment.objects.all().select_related(
            'staff', 'role'
        ).prefetch_related('staff__user')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=search) |
                Q(staff__last_name__icontains=search) |
                Q(staff__employee_id__icontains=search) |
                Q(role__name__icontains=search)
            )
        
        # Staff filter
        staff_id = request.GET.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Role filter
        role_id = request.GET.get('role')
        if role_id:
            queryset = queryset.filter(role_id=role_id)
        
        # Status filter
        status = request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True, end_date__isnull=True)
        elif status == 'inactive':
            queryset = queryset.filter(Q(is_active=False) | Q(end_date__isnull=False))
        elif status == 'expired':
            queryset = queryset.filter(end_date__lt=timezone.now().date(), is_active=False)
        
        return queryset.order_by('-start_date')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        active = queryset.filter(is_active=True, end_date__isnull=True).count()
        inactive = queryset.filter(Q(is_active=False) | Q(end_date__isnull=False)).count()
        expired = queryset.filter(end_date__lt=timezone.now().date(), is_active=False).count()
        
        return {
            'total_assignments': total,
            'active_assignments': active,
            'inactive_assignments': inactive,
            'expired_assignments': expired,
        }

    def get(self, request):
        """Handle GET request - display staff role assignment list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        assignments = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get all staff and roles for filters
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        roles = StaffRole.objects.all().order_by('name')
        
        context = {
            'assignments': assignments,
            'staff_members': staff_members,
            'roles': roles,
            'total_assignments': total_count,
            'active_assignments': queryset.filter(is_active=True, end_date__isnull=True).count(),
            'inactive_assignments': queryset.filter(Q(is_active=False) | Q(end_date__isnull=False)).count(),
            'expired_assignments': queryset.filter(end_date__lt=timezone.now().date(), is_active=False).count(),
            'search_query': request.GET.get('search', ''),
            'selected_staff': request.GET.get('staff', ''),
            'selected_role': request.GET.get('role', ''),
            'selected_status': request.GET.get('status', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class StaffRoleAssignmentCreateView(ManagementRequiredMixin, View):
    """View to create a new staff role assignment."""
    template_name = 'portal_management/hr/role_assignments/form.html'

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

    def _validate_assignment_data(self, data):
        """Validate staff role assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        role_id = data.get('role')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not role_id:
            errors['role'] = ['Role is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Check for existing active assignment for the same staff and role
        if staff_id and role_id and is_active:
            conflict = StaffRoleAssignment.objects.filter(
                staff_id=staff_id,
                role_id=role_id,
                is_active=True
            )
            if conflict.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    f'This staff member already has an active assignment for this role.'
                ]
        
        # Check if staff member has a user account (required for roles with portal access)
        if staff_id and role_id:
            staff = Staff.objects.get(pk=staff_id)
            role = StaffRole.objects.get(pk=role_id)
            if role.portal_category != 'none' and not staff.user:
                errors['__all__'] = errors.get('__all__', []) + [
                    f'Cannot assign a role with portal access to a staff member without a user account. '
                    f'Please create a user account for this staff member first.'
                ]
        
        return errors

    def get(self, request):
        """Display the create staff role assignment form."""
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        roles = StaffRole.objects.all().order_by('name')
        
        context = {
            'staff_members': staff_members,
            'roles': roles,
            'title': 'Assign Role to Staff',
            'is_edit': False,
            'assignment': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff role assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        staff_id = request.POST.get('staff')
        role_id = request.POST.get('role')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'role' in errors:
                    message = errors['role'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'roles': roles,
                'title': 'Assign Role to Staff',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                role = StaffRole.objects.get(pk=role_id)
                
                assignment = StaffRoleAssignment(
                    staff=staff,
                    role=role,
                    start_date=start_date,
                    end_date=end_date if end_date else None,
                    is_active=is_active,
                    remarks=remarks
                )
                assignment.full_clean()
                assignment.save()
                
                message = f'Role "{role.name}" assigned to {staff.get_full_name()} successfully!'
                
                if is_active and role.portal_category != 'none' and staff.user:
                    message += f' Staff member has been added to the "{role.group.name}" group.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_role_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': staff.get_full_name(),
                            'role': role.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_assignment_detail', pk=assignment.pk)
                
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
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'roles': roles,
                'title': 'Assign Role to Staff',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff role assignment: {e}", exc_info=True)
            error_msg = f'Error creating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'roles': roles,
                'title': 'Assign Role to Staff',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class StaffRoleAssignmentDetailView(ManagementRequiredMixin, View):
    """View to display staff role assignment details."""
    template_name = 'portal_management/hr/role_assignments/detail.html'

    def get(self, request, pk):
        """Display staff role assignment details."""
        assignment = get_object_or_404(StaffRoleAssignment, pk=pk)
        
        # Calculate duration
        duration = None
        end_date = assignment.end_date or timezone.now().date()
        duration = (end_date - assignment.start_date).days + 1
        
        # Check if assignment is expired
        is_expired = assignment.end_date and assignment.end_date < timezone.now().date()
        
        context = {
            'assignment': assignment,
            'duration': duration,
            'is_expired': is_expired,
            'staff': assignment.staff,
            'role': assignment.role,
        }
        return render(request, self.template_name, context)


class StaffRoleAssignmentUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff role assignment."""
    template_name = 'portal_management/hr/role_assignments/form.html'

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

    def _validate_assignment_data(self, data, assignment_id=None):
        """Validate staff role assignment data before saving."""
        errors = {}
        
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Validate that if is_active is True, there's no end_date
        if is_active and end_date:
            errors['__all__'] = errors.get('__all__', []) + [
                'Active assignments cannot have an end date. Please set end date to blank or mark as inactive.'
            ]
        
        return errors

    def get(self, request, pk):
        """Display the edit staff role assignment form."""
        assignment = get_object_or_404(StaffRoleAssignment, pk=pk)
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        roles = StaffRole.objects.all().order_by('name')
        
        context = {
            'assignment': assignment,
            'staff_members': staff_members,
            'roles': roles,
            'title': f'Edit Role Assignment: {assignment.staff.get_full_name()} - {assignment.role.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff role assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffRoleAssignment, pk=pk)
        
        # Get form data (staff and role cannot be changed after creation)
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST, assignment.pk)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
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
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'roles': roles,
                'title': f'Edit Role Assignment: {assignment.staff.get_full_name()} - {assignment.role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                # Check if status is changing from active to inactive
                was_active = assignment.is_active
                
                assignment.start_date = start_date
                assignment.end_date = end_date if end_date else None
                assignment.is_active = is_active
                assignment.remarks = remarks
                
                assignment.full_clean()
                assignment.save()
                
                message = f'Role assignment for {assignment.staff.get_full_name()} updated successfully!'
                
                if was_active != is_active and assignment.role.portal_category != 'none' and assignment.staff.user:
                    if is_active:
                        message += f' Staff member has been added to the "{assignment.role.group.name}" group.'
                    else:
                        message += f' Staff member has been removed from the "{assignment.role.group.name}" group.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_role_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': assignment.staff.get_full_name(),
                            'role': assignment.role.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_assignment_detail', pk=assignment.pk)
                
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
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'roles': roles,
                'title': f'Edit Role Assignment: {assignment.staff.get_full_name()} - {assignment.role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error updating staff role assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error updating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            roles = StaffRole.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'roles': roles,
                'title': f'Edit Role Assignment: {assignment.staff.get_full_name()} - {assignment.role.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class StaffRoleAssignmentDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff role assignment."""
    
    def post(self, request, pk):
        """Handle staff role assignment deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffRoleAssignment, pk=pk)
        assignment_info = f"{assignment.staff.get_full_name()} - {assignment.role.name}"
        
        try:
            with transaction.atomic():
                # Store info for message
                staff_name = assignment.staff.get_full_name()
                role_name = assignment.role.name
                was_active = assignment.is_active
                
                assignment.delete()
                
                message = f'Role assignment "{role_name}" for {staff_name} deleted successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_assignment_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff role assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_role_assignment_detail', pk=pk)


class StaffRoleAssignmentEndView(ManagementRequiredMixin, View):
    """View to end an active staff role assignment."""
    
    def post(self, request, pk):
        """End an active staff role assignment (set end date to today)."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffRoleAssignment, pk=pk)
        
        if not assignment.is_active:
            error_msg = 'This assignment is already inactive.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:staff_role_assignment_detail', pk=pk)
        
        try:
            with transaction.atomic():
                assignment.end_date = timezone.now().date()
                assignment.is_active = False
                assignment.save()
                
                message = f'Role assignment for {assignment.staff.get_full_name()} has been ended.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_role_assignment_detail', pk=assignment.pk)
                
        except Exception as e:
            logger.error(f"Error ending staff role assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error ending assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_role_assignment_detail', pk=pk)


class StaffRoleAssignmentSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff role assignments (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff role assignments for autocomplete."""
        term = request.GET.get('term', '').strip()
        staff_id = request.GET.get('staff')
        role_id = request.GET.get('role')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = StaffRoleAssignment.objects.all().select_related('staff', 'role')
        
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        if role_id:
            queryset = queryset.filter(role_id=role_id)
        
        if term:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(role__name__icontains=term)
            )
        
        queryset = queryset.order_by('-start_date')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        assignments = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': assignment.pk,
                'text': f"{assignment.staff.get_full_name()} - {assignment.role.name} ({assignment.start_date.strftime('%b %d, %Y')})",
                'staff': assignment.staff.get_full_name(),
                'role': assignment.role.name,
                'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                'is_active': assignment.is_active,
            }
            for assignment in assignments
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })
    


class StaffDepartmentAssignmentListView(ManagementRequiredMixin, View):
    """View to list all staff department assignments with filtering and search."""
    template_name = 'portal_management/hr/department_assignments/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = StaffDepartmentAssignment.objects.all().select_related(
            'staff', 'department'
        )
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=search) |
                Q(staff__last_name__icontains=search) |
                Q(staff__employee_id__icontains=search) |
                Q(department__name__icontains=search) |
                Q(department__code__icontains=search)
            )
        
        # Staff filter
        staff_id = request.GET.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Department filter
        department_id = request.GET.get('department')
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        
        # Role filter (Head of Department)
        is_head = request.GET.get('is_head')
        if is_head == 'yes':
            queryset = queryset.filter(is_head=True)
        elif is_head == 'no':
            queryset = queryset.filter(is_head=False)
        
        # Status filter
        status = request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True, end_date__isnull=True)
        elif status == 'inactive':
            queryset = queryset.filter(Q(is_active=False) | Q(end_date__isnull=False))
        
        return queryset.order_by('-start_date')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        active = queryset.filter(is_active=True, end_date__isnull=True).count()
        inactive = queryset.filter(Q(is_active=False) | Q(end_date__isnull=False)).count()
        heads = queryset.filter(is_head=True, is_active=True).count()
        
        return {
            'total_assignments': total,
            'active_assignments': active,
            'inactive_assignments': inactive,
            'heads_of_department': heads,
        }

    def get(self, request):
        """Handle GET request - display staff department assignment list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        assignments = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get all staff and departments for filters
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        departments = Department.objects.all().order_by('name')
        
        context = {
            'assignments': assignments,
            'staff_members': staff_members,
            'departments': departments,
            'total_assignments': total_count,
            'active_assignments': queryset.filter(is_active=True, end_date__isnull=True).count(),
            'inactive_assignments': queryset.filter(Q(is_active=False) | Q(end_date__isnull=False)).count(),
            'heads_of_department': queryset.filter(is_head=True, is_active=True).count(),
            'search_query': request.GET.get('search', ''),
            'selected_staff': request.GET.get('staff', ''),
            'selected_department': request.GET.get('department', ''),
            'selected_is_head': request.GET.get('is_head', ''),
            'selected_status': request.GET.get('status', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class StaffDepartmentAssignmentCreateView(ManagementRequiredMixin, View):
    """View to create a new staff department assignment."""
    template_name = 'portal_management/hr/department_assignments/form.html'

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

    def _validate_assignment_data(self, data):
        """Validate staff department assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        department_id = data.get('department')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        is_head = data.get('is_head') == 'true'
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not department_id:
            errors['department'] = ['Department is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Check for existing active assignment for the same staff and department
        if staff_id and department_id and is_active:
            conflict = StaffDepartmentAssignment.objects.filter(
                staff_id=staff_id,
                department_id=department_id,
                is_active=True
            )
            if conflict.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    f'This staff member already has an active assignment in this department.'
                ]
        
        # Check if there's already a head of department for this department
        if department_id and is_head and is_active:
            existing_head = StaffDepartmentAssignment.objects.filter(
                department_id=department_id,
                is_head=True,
                is_active=True
            ).exclude(staff_id=staff_id)
            if existing_head.exists():
                existing_head_name = existing_head.first().staff.get_full_name()
                errors['is_head'] = [f'Department already has a Head of Department: {existing_head_name}.']
        
        return errors

    def get(self, request):
        """Display the create staff department assignment form."""
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        departments = Department.objects.all().order_by('name')
        
        context = {
            'staff_members': staff_members,
            'departments': departments,
            'title': 'Assign Staff to Department',
            'is_edit': False,
            'assignment': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff department assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        staff_id = request.POST.get('staff')
        department_id = request.POST.get('department')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        is_head = request.POST.get('is_head') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'department' in errors:
                    message = errors['department'][0]
                elif 'is_head' in errors:
                    message = errors['is_head'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'departments': departments,
                'title': 'Assign Staff to Department',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                department = Department.objects.get(pk=department_id)
                
                assignment = StaffDepartmentAssignment(
                    staff=staff,
                    department=department,
                    start_date=start_date,
                    end_date=end_date if end_date else None,
                    is_active=is_active,
                    is_head=is_head,
                    remarks=remarks
                )
                assignment.full_clean()
                assignment.save()
                
                message = f'{staff.get_full_name()} assigned to {department.name} successfully!'
                if is_head:
                    message += f' {staff.get_full_name()} is now the Head of Department.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_department_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': staff.get_full_name(),
                            'department': department.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                            'is_head': assignment.is_head,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_department_assignment_detail', pk=assignment.pk)
                
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
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'departments': departments,
                'title': 'Assign Staff to Department',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff department assignment: {e}", exc_info=True)
            error_msg = f'Error creating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'departments': departments,
                'title': 'Assign Staff to Department',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': [error_msg],
            })


from django.utils.timesince import timesince
from datetime import date, timedelta
from django.utils import timezone

class StaffDepartmentAssignmentDetailView(ManagementRequiredMixin, View):
    """View to display staff department assignment details."""
    template_name = 'portal_management/hr/department_assignments/detail.html'

    def get(self, request, pk):
        """Display staff department assignment details."""
        assignment = get_object_or_404(
            StaffDepartmentAssignment.objects.select_related(
                'staff', 
                'staff__user', 
                'department'
            ),
            pk=pk
        )
        
        # Calculate duration
        end_date = assignment.end_date or timezone.now().date()
        duration = (end_date - assignment.start_date).days + 1
        
        # Check if assignment is expired
        is_expired = assignment.end_date and assignment.end_date < timezone.now().date()
        
        # Get department statistics
        department = assignment.department
        dept_assignments = StaffDepartmentAssignment.objects.filter(
            department=department
        ).select_related('staff')
        
        department_total_staff = dept_assignments.count()
        department_active_staff = dept_assignments.filter(is_active=True).count()
        
        # Calculate other staff (active staff excluding current assignment if active)
        department_other_staff = department_active_staff
        if assignment.is_active:
            department_other_staff = department_active_staff - 1
        
        # Get Head of Department
        hod = dept_assignments.filter(
            is_head=True,
            is_active=True
        ).select_related('staff').first()
        
        # Get other assignments
        other_assignments = dept_assignments.exclude(pk=assignment.pk).select_related('staff')[:5]
        
        # Get staff's other assignments
        staff_other_assignments = StaffDepartmentAssignment.objects.filter(
            staff=assignment.staff,
            is_active=True
        ).exclude(pk=assignment.pk).select_related('department')[:3]
        
        # Calculate timesince values using Django's timesince function
        today = timezone.now()
        
        context = {
            # Core assignment data
            'assignment': assignment,
            'duration': duration,
            'is_expired': is_expired,
            'staff': assignment.staff,
            'department': assignment.department,
            'is_hod': assignment.is_head and assignment.is_active,
            
            # Department statistics
            'department_total_staff': department_total_staff,
            'department_active_staff': department_active_staff,
            'department_other_staff': max(department_other_staff, 0),
            'department_hod': hod,
            'department_has_hod': hod is not None,
            'department_hod_name': hod.staff.get_full_name() if hod else None,
            
            # Other assignments
            'other_assignments': other_assignments,
            'other_assignments_count': other_assignments.count(),
            'staff_other_assignments': staff_other_assignments,
            'staff_other_assignments_count': staff_other_assignments.count(),
            
            # Staff details
            'staff_full_name': assignment.staff.get_full_name(),
            'staff_employee_id': assignment.staff.employee_id,
            'staff_phone': assignment.staff.phone_number or 'Not specified',
            'staff_email': assignment.staff.user.email if assignment.staff.user else 'Not specified',
            'staff_employment_type': assignment.staff.get_employment_type_display(),
            'staff_joining_date': assignment.staff.joining_date,
            
            # Department details
            'department_code': assignment.department.code,
            'department_created_at': assignment.department.created_at,
            'department_description': assignment.department.description,
            
            # Assignment details
            'assignment_id': assignment.pk,
            'start_date': assignment.start_date,
            'end_date': assignment.end_date,
            'is_active': assignment.is_active,
            'is_head': assignment.is_head,
            'remarks': assignment.remarks,
            'created_at': assignment.created_at,
            'updated_at': assignment.updated_at,
            
            # Status text
            'status_text': 'Active' if assignment.is_active and not is_expired else ('Expired' if is_expired else 'Inactive'),
            'status_icon': 'check-circle-fill' if assignment.is_active and not is_expired else ('calendar-x' if is_expired else 'pause-circle'),
            'role_text': 'Head of Department' if assignment.is_head else 'Staff Member',
            
            # Date formatting
            'start_date_formatted': assignment.start_date.strftime('%B %d, %Y'),
            'start_date_short': assignment.start_date.strftime('%b %d, %Y'),
            'end_date_formatted': assignment.end_date.strftime('%B %d, %Y') if assignment.end_date else None,
            'end_date_short': assignment.end_date.strftime('%b %d, %Y') if assignment.end_date else None,
            'created_at_formatted': assignment.created_at.strftime('%B %d, %Y'),
            'created_at_short': assignment.created_at.strftime('%b %d, %Y'),
            'updated_at_formatted': assignment.updated_at.strftime('%B %d, %Y'),
            'updated_at_short': assignment.updated_at.strftime('%b %d, %Y'),
            
            # Timesince as strings (formatted in Python)
            'created_timesince': timesince(assignment.created_at, today),
            'updated_timesince': timesince(assignment.updated_at, today),
            'department_created_timesince': timesince(assignment.department.created_at, today),
        }
        
        return render(request, self.template_name, context)



class StaffDepartmentAssignmentUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff department assignment."""
    template_name = 'portal_management/hr/department_assignments/form.html'

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

    def _validate_assignment_data(self, data, assignment_id=None):
        """Validate staff department assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        department_id = data.get('department')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        is_head = data.get('is_head') == 'true'
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not department_id:
            errors['department'] = ['Department is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Check for existing active assignment for the same staff and department (excluding current)
        if staff_id and department_id and is_active:
            conflict = StaffDepartmentAssignment.objects.filter(
                staff_id=staff_id,
                department_id=department_id,
                is_active=True
            ).exclude(pk=assignment_id)
            if conflict.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    f'This staff member already has an active assignment in this department.'
                ]
        
        # Check if there's already a head of department for this department (excluding current)
        if department_id and is_head and is_active:
            existing_head = StaffDepartmentAssignment.objects.filter(
                department_id=department_id,
                is_head=True,
                is_active=True
            ).exclude(pk=assignment_id)
            if existing_head.exists():
                existing_head_name = existing_head.first().staff.get_full_name()
                errors['is_head'] = [f'Department already has a Head of Department: {existing_head_name}.']
        
        return errors

    def get(self, request, pk):
        """Display the edit staff department assignment form."""
        assignment = get_object_or_404(StaffDepartmentAssignment, pk=pk)
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        departments = Department.objects.all().order_by('name')
        
        context = {
            'assignment': assignment,
            'staff_members': staff_members,
            'departments': departments,
            'title': f'Edit Department Assignment: {assignment.staff.get_full_name()} - {assignment.department.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff department assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffDepartmentAssignment, pk=pk)
        
        # Get form data
        staff_id = request.POST.get('staff')
        department_id = request.POST.get('department')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        is_head = request.POST.get('is_head') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST, assignment.pk)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'department' in errors:
                    message = errors['department'][0]
                elif 'is_head' in errors:
                    message = errors['is_head'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'departments': departments,
                'title': f'Edit Department Assignment: {assignment.staff.get_full_name()} - {assignment.department.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                # Update assignment
                assignment.staff_id = staff_id
                assignment.department_id = department_id
                assignment.start_date = start_date
                assignment.end_date = end_date if end_date else None
                assignment.is_active = is_active
                assignment.is_head = is_head
                assignment.remarks = remarks
                
                assignment.full_clean()
                assignment.save()
                
                message = f'Department assignment for {assignment.staff.get_full_name()} updated successfully!'
                if is_head:
                    message += f' {assignment.staff.get_full_name()} is now the Head of Department.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_department_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': assignment.staff.get_full_name(),
                            'department': assignment.department.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                            'is_head': assignment.is_head,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_department_assignment_detail', pk=assignment.pk)
                
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
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'departments': departments,
                'title': f'Edit Department Assignment: {assignment.staff.get_full_name()} - {assignment.department.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error updating staff department assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error updating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            departments = Department.objects.all().order_by('name')
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'departments': departments,
                'title': f'Edit Department Assignment: {assignment.staff.get_full_name()} - {assignment.department.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class StaffDepartmentAssignmentDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff department assignment."""
    
    def post(self, request, pk):
        """Handle staff department assignment deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffDepartmentAssignment, pk=pk)
        assignment_info = f"{assignment.staff.get_full_name()} - {assignment.department.name}"
        
        try:
            with transaction.atomic():
                # Store info for message
                staff_name = assignment.staff.get_full_name()
                department_name = assignment.department.name
                
                assignment.delete()
                
                message = f'Department assignment for {staff_name} in {department_name} deleted successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_department_assignment_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff department assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_department_assignment_detail', pk=pk)


class StaffDepartmentAssignmentEndView(ManagementRequiredMixin, View):
    """View to end an active staff department assignment."""
    
    def post(self, request, pk):
        """End an active staff department assignment (set end date to today)."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffDepartmentAssignment, pk=pk)
        
        if not assignment.is_active:
            error_msg = 'This assignment is already inactive.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:staff_department_assignment_detail', pk=pk)
        
        try:
            with transaction.atomic():
                assignment.end_date = timezone.now().date()
                assignment.is_active = False
                assignment.save()
                
                message = f'Department assignment for {assignment.staff.get_full_name()} in {assignment.department.name} has been ended.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_department_assignment_detail', pk=assignment.pk)
                
        except Exception as e:
            logger.error(f"Error ending staff department assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error ending assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_department_assignment_detail', pk=pk)


class StaffDepartmentAssignmentSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff department assignments (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff department assignments for autocomplete."""
        term = request.GET.get('term', '').strip()
        staff_id = request.GET.get('staff')
        department_id = request.GET.get('department')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = StaffDepartmentAssignment.objects.all().select_related('staff', 'department')
        
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        
        if term:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(department__name__icontains=term)
            )
        
        queryset = queryset.order_by('-start_date')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        assignments = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': assignment.pk,
                'text': f"{assignment.staff.get_full_name()} - {assignment.department.name} ({assignment.start_date.strftime('%b %d, %Y')})",
                'staff': assignment.staff.get_full_name(),
                'department': assignment.department.name,
                'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                'is_active': assignment.is_active,
                'is_head': assignment.is_head,
            }
            for assignment in assignments
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })





class StaffTeachingAssignmentListView(ManagementRequiredMixin, View):
    """View to list all staff teaching assignments with filtering and search."""
    template_name = 'portal_management/hr/teaching_assignments/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = StaffTeachingAssignment.objects.all().select_related(
            'staff', 'subject', 'class_level', 'stream_class', 'academic_year'
        ).prefetch_related(
            'staff__department_assignments',
            'subject__educational_level'
        )
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=search) |
                Q(staff__last_name__icontains=search) |
                Q(staff__employee_id__icontains=search) |
                Q(subject__name__icontains=search) |
                Q(subject__code__icontains=search) |
                Q(class_level__name__icontains=search) |
                Q(stream_class__name__icontains=search)
            )
        
        # Staff filter
        staff_id = request.GET.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Subject filter
        subject_id = request.GET.get('subject')
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        
        # Class level filter
        class_level_id = request.GET.get('class_level')
        if class_level_id:
            queryset = queryset.filter(class_level_id=class_level_id)
        
        # Stream filter
        stream_id = request.GET.get('stream')
        if stream_id:
            queryset = queryset.filter(stream_class_id=stream_id)
        
        # Academic year filter
        academic_year_id = request.GET.get('academic_year')
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        return queryset.order_by('-academic_year__start_date', 'class_level', 'subject')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        
        # Get the active academic year
        active_year = AcademicYear.objects.filter(is_active=True).first()
        active_assignments = 0
        if active_year:
            active_assignments = queryset.filter(academic_year=active_year).count()
        
        # Staff count with assignments (unique staff members)
        staff_count = queryset.values('staff').distinct().count()
        
        # Subjects with assignments
        subject_count = queryset.values('subject').distinct().count()
        
        return {
            'total_assignments': total,
            'active_assignments': active_assignments,
            'staff_count': staff_count,
            'subject_count': subject_count,
        }

    def get(self, request):
        """Handle GET request - display staff teaching assignment list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        assignments = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get filter data
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        subjects = Subject.objects.all().order_by('name')
        class_levels = ClassLevel.objects.all().order_by('educational_level', 'order')
        streams = StreamClass.objects.all().order_by('class_level', 'stream_letter')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        # Get statistics
        stats = self.get_statistics(queryset)
        
        context = {
            'assignments': assignments,
            'staff_members': staff_members,
            'subjects': subjects,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            **stats,
            'search_query': request.GET.get('search', ''),
            'selected_staff': request.GET.get('staff', ''),
            'selected_subject': request.GET.get('subject', ''),
            'selected_class_level': request.GET.get('class_level', ''),
            'selected_stream': request.GET.get('stream', ''),
            'selected_academic_year': request.GET.get('academic_year', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class StaffTeachingAssignmentCreateView(ManagementRequiredMixin, View):
    """View to create a new staff teaching assignment."""
    template_name = 'portal_management/hr/teaching_assignments/form.html'

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

    def _validate_assignment_data(self, data):
        """Validate staff teaching assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        subject_id = data.get('subject')
        class_level_id = data.get('class_level')
        stream_id = data.get('stream')
        academic_year_id = data.get('academic_year')
        periods_per_week = data.get('periods_per_week', 0)
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not subject_id:
            errors['subject'] = ['Subject is required.']
        
        if not class_level_id:
            errors['class_level'] = ['Class level is required.']
        
        if not academic_year_id:
            errors['academic_year'] = ['Academic year is required.']
        
        # Validate periods per week
        if periods_per_week:
            try:
                periods = int(periods_per_week)
                if periods < 0:
                    errors['periods_per_week'] = ['Periods per week cannot be negative.']
                elif periods > 40:  # Reasonable maximum
                    errors['periods_per_week'] = ['Periods per week cannot exceed 40.']
            except ValueError:
                errors['periods_per_week'] = ['Please enter a valid number.']
        
        # Validate stream belongs to class level
        if stream_id and class_level_id:
            try:
                stream = StreamClass.objects.get(pk=stream_id)
                if stream.class_level_id != int(class_level_id):
                    errors['stream'] = [
                        f'Stream "{stream}" does not belong to the selected class level.'
                    ]
            except StreamClass.DoesNotExist:
                errors['stream'] = ['Selected stream does not exist.']
        
        # Validate subject belongs to the same educational level as class level
        if subject_id and class_level_id:
            try:
                subject = Subject.objects.get(pk=subject_id)
                class_level = ClassLevel.objects.get(pk=class_level_id)
                if subject.educational_level != class_level.educational_level:
                    errors['subject'] = [
                        f'Subject "{subject}" belongs to "{subject.educational_level}" '
                        f'but the selected class level is in "{class_level.educational_level}".'
                    ]
            except (Subject.DoesNotExist, ClassLevel.DoesNotExist):
                pass  # Will be caught by required field validation
        
        # Check for duplicate assignment
        if staff_id and subject_id and class_level_id and academic_year_id:
            duplicate = StaffTeachingAssignment.objects.filter(
                staff_id=staff_id,
                subject_id=subject_id,
                class_level_id=class_level_id,
                stream_class_id=stream_id or None,
                academic_year_id=academic_year_id,
            )
            if duplicate.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    'A teaching assignment already exists for this '
                    'staff/subject/class/stream/year combination.'
                ]
        
        return errors

    def get(self, request):
        """Display the create staff teaching assignment form."""
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        subjects = Subject.objects.all().order_by('name')
        class_levels = ClassLevel.objects.all().select_related('educational_level')
        streams = StreamClass.objects.all().select_related('class_level')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        # Get active academic year for default selection
        active_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        context = {
            'staff_members': staff_members,
            'subjects': subjects,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            'active_academic_year': active_academic_year,
            'title': 'Create Teaching Assignment',
            'is_edit': False,
            'assignment': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create staff teaching assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        staff_id = request.POST.get('staff')
        subject_id = request.POST.get('subject')
        class_level_id = request.POST.get('class_level')
        stream_id = request.POST.get('stream')
        academic_year_id = request.POST.get('academic_year')
        periods_per_week = request.POST.get('periods_per_week', 0)
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'subject' in errors:
                    message = errors['subject'][0]
                elif 'class_level' in errors:
                    message = errors['class_level'][0]
                elif 'stream' in errors:
                    message = errors['stream'][0]
                elif 'academic_year' in errors:
                    message = errors['academic_year'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Teaching Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                subject = Subject.objects.get(pk=subject_id)
                class_level = ClassLevel.objects.get(pk=class_level_id)
                academic_year = AcademicYear.objects.get(pk=academic_year_id)
                
                assignment = StaffTeachingAssignment(
                    staff=staff,
                    subject=subject,
                    class_level=class_level,
                    stream_class_id=stream_id or None,
                    academic_year=academic_year,
                    periods_per_week=int(periods_per_week) if periods_per_week else 0,
                    remarks=remarks
                )
                assignment.full_clean()
                assignment.save()
                
                stream_text = f" - {assignment.stream_class}" if assignment.stream_class else ""
                message = (
                    f'{staff.get_full_name()} assigned to teach {subject.name} '
                    f'in {class_level.name}{stream_text} for {academic_year} successfully!'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_teaching_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': staff.get_full_name(),
                            'subject': subject.name,
                            'class_level': class_level.name,
                            'stream': assignment.stream_class.name if assignment.stream_class else None,
                            'academic_year': academic_year.name,
                            'periods_per_week': assignment.periods_per_week,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_teaching_assignment_detail', pk=assignment.pk)
                
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
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Teaching Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error creating staff teaching assignment: {e}", exc_info=True)
            error_msg = f'Error creating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Teaching Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class StaffTeachingAssignmentDetailView(ManagementRequiredMixin, View):
    """View to display staff teaching assignment details."""
    template_name = 'portal_management/hr/teaching_assignments/detail.html'

    def get(self, request, pk):
        """Display staff teaching assignment details."""
        assignment = get_object_or_404(
            StaffTeachingAssignment.objects.select_related(
                'staff', 'subject', 'class_level', 'stream_class', 'academic_year'
            ),
            pk=pk
        )
        
        # Get related information
        staff = assignment.staff
        staff_teaching_load = StaffTeachingAssignment.objects.filter(
            staff=staff,
            academic_year=assignment.academic_year
        ).count()
        
        staff_total_periods = StaffTeachingAssignment.objects.filter(
            staff=staff,
            academic_year=assignment.academic_year
        ).aggregate(total=models.Sum('periods_per_week'))['total'] or 0
        
        # Get other staff teaching the same subject in the same class/stream
        similar_assignments = StaffTeachingAssignment.objects.filter(
            subject=assignment.subject,
            class_level=assignment.class_level,
            academic_year=assignment.academic_year
        ).exclude(pk=pk).select_related('staff')[:5]
        
        context = {
            'assignment': assignment,
            'staff': staff,
            'subject': assignment.subject,
            'class_level': assignment.class_level,
            'stream': assignment.stream_class,
            'academic_year': assignment.academic_year,
            'staff_teaching_load': staff_teaching_load,
            'staff_total_periods': staff_total_periods,
            'similar_assignments': similar_assignments,
        }
        return render(request, self.template_name, context)


class StaffTeachingAssignmentUpdateView(ManagementRequiredMixin, View):
    """View to update an existing staff teaching assignment."""
    template_name = 'portal_management/hr/teaching_assignments/form.html'

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

    def _validate_assignment_data(self, data, assignment_id=None):
        """Validate staff teaching assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        subject_id = data.get('subject')
        class_level_id = data.get('class_level')
        stream_id = data.get('stream')
        academic_year_id = data.get('academic_year')
        periods_per_week = data.get('periods_per_week', 0)
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not subject_id:
            errors['subject'] = ['Subject is required.']
        
        if not class_level_id:
            errors['class_level'] = ['Class level is required.']
        
        if not academic_year_id:
            errors['academic_year'] = ['Academic year is required.']
        
        # Validate periods per week
        if periods_per_week:
            try:
                periods = int(periods_per_week)
                if periods < 0:
                    errors['periods_per_week'] = ['Periods per week cannot be negative.']
                elif periods > 40:  # Reasonable maximum
                    errors['periods_per_week'] = ['Periods per week cannot exceed 40.']
            except ValueError:
                errors['periods_per_week'] = ['Please enter a valid number.']
        
        # Validate stream belongs to class level
        if stream_id and class_level_id:
            try:
                stream = StreamClass.objects.get(pk=stream_id)
                if stream.class_level_id != int(class_level_id):
                    errors['stream'] = [
                        f'Stream "{stream}" does not belong to the selected class level.'
                    ]
            except StreamClass.DoesNotExist:
                errors['stream'] = ['Selected stream does not exist.']
        
        # Validate subject belongs to the same educational level as class level
        if subject_id and class_level_id:
            try:
                subject = Subject.objects.get(pk=subject_id)
                class_level = ClassLevel.objects.get(pk=class_level_id)
                if subject.educational_level != class_level.educational_level:
                    errors['subject'] = [
                        f'Subject "{subject}" belongs to "{subject.educational_level}" '
                        f'but the selected class level is in "{class_level.educational_level}".'
                    ]
            except (Subject.DoesNotExist, ClassLevel.DoesNotExist):
                pass
        
        # Check for duplicate assignment (excluding current)
        if staff_id and subject_id and class_level_id and academic_year_id:
            duplicate = StaffTeachingAssignment.objects.filter(
                staff_id=staff_id,
                subject_id=subject_id,
                class_level_id=class_level_id,
                stream_class_id=stream_id or None,
                academic_year_id=academic_year_id,
            ).exclude(pk=assignment_id)
            if duplicate.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    'A teaching assignment already exists for this '
                    'staff/subject/class/stream/year combination.'
                ]
        
        return errors

    def get(self, request, pk):
        """Display the edit staff teaching assignment form."""
        assignment = get_object_or_404(
            StaffTeachingAssignment.objects.select_related(
                'staff', 'subject', 'class_level', 'stream_class', 'academic_year'
            ),
            pk=pk
        )
        
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        subjects = Subject.objects.all().order_by('name')
        class_levels = ClassLevel.objects.all().select_related('educational_level')
        streams = StreamClass.objects.all().select_related('class_level')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        context = {
            'assignment': assignment,
            'staff_members': staff_members,
            'subjects': subjects,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            'title': f'Edit Teaching Assignment: {assignment.staff.get_full_name()} - {assignment.subject.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit staff teaching assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffTeachingAssignment, pk=pk)
        
        # Get form data
        staff_id = request.POST.get('staff')
        subject_id = request.POST.get('subject')
        class_level_id = request.POST.get('class_level')
        stream_id = request.POST.get('stream')
        academic_year_id = request.POST.get('academic_year')
        periods_per_week = request.POST.get('periods_per_week', 0)
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST, assignment.pk)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'subject' in errors:
                    message = errors['subject'][0]
                elif 'class_level' in errors:
                    message = errors['class_level'][0]
                elif 'stream' in errors:
                    message = errors['stream'][0]
                elif 'academic_year' in errors:
                    message = errors['academic_year'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Teaching Assignment: {assignment.staff.get_full_name()} - {assignment.subject.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                # Update assignment
                assignment.staff_id = staff_id
                assignment.subject_id = subject_id
                assignment.class_level_id = class_level_id
                assignment.stream_class_id = stream_id or None
                assignment.academic_year_id = academic_year_id
                assignment.periods_per_week = int(periods_per_week) if periods_per_week else 0
                assignment.remarks = remarks
                
                assignment.full_clean()
                assignment.save()
                
                stream_text = f" - {assignment.stream_class}" if assignment.stream_class else ""
                message = (
                    f'Teaching assignment for {assignment.staff.get_full_name()} updated successfully! '
                    f'Now teaching {assignment.subject.name} in {assignment.class_level.name}{stream_text} '
                    f'for {assignment.academic_year}.'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:staff_teaching_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': assignment.staff.get_full_name(),
                            'subject': assignment.subject.name,
                            'class_level': assignment.class_level.name,
                            'stream': assignment.stream_class.name if assignment.stream_class else None,
                            'academic_year': assignment.academic_year.name,
                            'periods_per_week': assignment.periods_per_week,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:staff_teaching_assignment_detail', pk=assignment.pk)
                
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
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Teaching Assignment: {assignment.staff.get_full_name()} - {assignment.subject.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error updating staff teaching assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error updating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            subjects = Subject.objects.all().order_by('name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'subjects': subjects,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Teaching Assignment: {assignment.staff.get_full_name()} - {assignment.subject.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class StaffTeachingAssignmentDeleteView(ManagementRequiredMixin, View):
    """View to delete a staff teaching assignment."""
    
    def post(self, request, pk):
        """Handle staff teaching assignment deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(StaffTeachingAssignment, pk=pk)
        assignment_info = f"{assignment.staff.get_full_name()} - {assignment.subject.name}"
        
        try:
            with transaction.atomic():
                # Store info for message
                staff_name = assignment.staff.get_full_name()
                subject_name = assignment.subject.name
                class_name = assignment.class_level.name
                stream_name = f" - {assignment.stream_class}" if assignment.stream_class else ""
                year_name = assignment.academic_year.name
                
                assignment.delete()
                
                message = (
                    f'Teaching assignment for {staff_name} teaching {subject_name} '
                    f'in {class_name}{stream_name} for {year_name} deleted successfully!'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:staff_teaching_assignment_list')
            
        except Exception as e:
            logger.error(f"Error deleting staff teaching assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:staff_teaching_assignment_detail', pk=pk)


class StaffTeachingAssignmentSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching staff teaching assignments (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered staff teaching assignments for autocomplete."""
        term = request.GET.get('term', '').strip()
        staff_id = request.GET.get('staff')
        subject_id = request.GET.get('subject')
        class_level_id = request.GET.get('class_level')
        academic_year_id = request.GET.get('academic_year')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = StaffTeachingAssignment.objects.all().select_related(
            'staff', 'subject', 'class_level', 'stream_class', 'academic_year'
        )
        
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        
        if class_level_id:
            queryset = queryset.filter(class_level_id=class_level_id)
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        if term:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(subject__name__icontains=term) |
                Q(subject__code__icontains=term) |
                Q(class_level__name__icontains=term)
            )
        
        queryset = queryset.order_by('-academic_year__start_date', 'class_level')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        assignments = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': assignment.pk,
                'text': (
                    f"{assignment.staff.get_full_name()} - {assignment.subject.name} "
                    f"({assignment.class_level.name}) - {assignment.academic_year.name}"
                ),
                'staff': assignment.staff.get_full_name(),
                'subject': assignment.subject.name,
                'class_level': assignment.class_level.name,
                'stream': assignment.stream_class.name if assignment.stream_class else None,
                'academic_year': assignment.academic_year.name,
                'periods_per_week': assignment.periods_per_week,
            }
            for assignment in assignments
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })


class StaffTeachingAssignmentLoadView(ManagementRequiredMixin, View):
    """View to display staff teaching load summary."""
    template_name = 'portal_management/hr/teaching_assignments/load.html'

    def get(self, request):
        """Display staff teaching load for a selected academic year."""
        academic_year_id = request.GET.get('academic_year')
        
        if academic_year_id:
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        else:
            academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not academic_year:
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            context = {
                'academic_years': academic_years,
                'no_active_year': True,
            }
            return render(request, self.template_name, context)
        
        # Get all staff teaching assignments for this academic year
        assignments = StaffTeachingAssignment.objects.filter(
            academic_year=academic_year
        ).select_related(
            'staff', 'subject', 'class_level', 'stream_class'
        ).order_by('staff__first_name', 'staff__last_name')
        
        # Group by staff
        staff_load = {}
        for assignment in assignments:
            staff_id = assignment.staff_id
            if staff_id not in staff_load:
                staff_load[staff_id] = {
                    'staff': assignment.staff,
                    'assignments': [],
                    'total_periods': 0,
                }
            staff_load[staff_id]['assignments'].append(assignment)
            staff_load[staff_id]['total_periods'] += assignment.periods_per_week
        
        # Convert to list and sort by total periods (descending)
        staff_load_list = sorted(
            staff_load.values(),
            key=lambda x: x['total_periods'],
            reverse=True
        )
        
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        context = {
            'staff_load': staff_load_list,
            'academic_year': academic_year,
            'academic_years': academic_years,
            'selected_academic_year': academic_year.id,
            'total_assignments': assignments.count(),
            'staff_count': len(staff_load_list),
        }
        
        return render(request, self.template_name, context)        




class ClassTeacherAssignmentListView(ManagementRequiredMixin, View):
    """View to list all class teacher assignments with filtering and search."""
    template_name = 'portal_management/hr/class_teacher_assignments/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = ClassTeacherAssignment.objects.all().select_related(
            'staff', 'class_level', 'stream_class', 'academic_year'
        ).prefetch_related(
            'staff__department_assignments'
        )
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=search) |
                Q(staff__last_name__icontains=search) |
                Q(staff__employee_id__icontains=search) |
                Q(class_level__name__icontains=search) |
                Q(stream_class__name__icontains=search) |
                Q(academic_year__name__icontains=search)
            )
        
        # Staff filter
        staff_id = request.GET.get('staff')
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        # Class level filter
        class_level_id = request.GET.get('class_level')
        if class_level_id:
            queryset = queryset.filter(class_level_id=class_level_id)
        
        # Stream filter
        stream_id = request.GET.get('stream')
        if stream_id:
            queryset = queryset.filter(stream_class_id=stream_id)
        
        # Academic year filter
        academic_year_id = request.GET.get('academic_year')
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        # Status filter
        status = request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True, end_date__isnull=True)
        elif status == 'inactive':
            queryset = queryset.filter(Q(is_active=False) | Q(end_date__isnull=False))
        
        return queryset.order_by('-academic_year__start_date', 'class_level')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        
        # Get the active academic year
        active_year = AcademicYear.objects.filter(is_active=True).first()
        active_assignments = 0
        if active_year:
            active_assignments = queryset.filter(
                academic_year=active_year, 
                is_active=True
            ).count()
        
        # Staff count with class teacher assignments (unique staff members)
        staff_count = queryset.filter(is_active=True).values('staff').distinct().count()
        
        # Classes with class teacher assignments
        class_count = queryset.values('class_level').distinct().count()
        
        # Assignments ending soon (within next 30 days)
        today = timezone.now().date()
        thirty_days_later = today + timezone.timedelta(days=30)
        ending_soon = queryset.filter(
            end_date__isnull=False,
            end_date__gte=today,
            end_date__lte=thirty_days_later,
            is_active=True
        ).count()
        
        return {
            'total_assignments': total,
            'active_assignments': active_assignments,
            'staff_count': staff_count,
            'class_count': class_count,
            'ending_soon': ending_soon,
        }

    def get(self, request):
        """Handle GET request - display class teacher assignment list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        assignments = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get filter data
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        class_levels = ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order')
        streams = StreamClass.objects.all().select_related('class_level').order_by('class_level', 'stream_letter')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        # Get statistics
        stats = self.get_statistics(queryset)
        
        context = {
            'assignments': assignments,
            'staff_members': staff_members,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            **stats,
            'search_query': request.GET.get('search', ''),
            'selected_staff': request.GET.get('staff', ''),
            'selected_class_level': request.GET.get('class_level', ''),
            'selected_stream': request.GET.get('stream', ''),
            'selected_academic_year': request.GET.get('academic_year', ''),
            'selected_status': request.GET.get('status', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class ClassTeacherAssignmentCreateView(ManagementRequiredMixin, View):
    """View to create a new class teacher assignment."""
    template_name = 'portal_management/hr/class_teacher_assignments/form.html'

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

    def _validate_assignment_data(self, data):
        """Validate class teacher assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        class_level_id = data.get('class_level')
        stream_id = data.get('stream')
        academic_year_id = data.get('academic_year')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not class_level_id:
            errors['class_level'] = ['Class level is required.']
        
        if not academic_year_id:
            errors['academic_year'] = ['Academic year is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Validate stream belongs to class level
        if stream_id and class_level_id:
            try:
                stream = StreamClass.objects.get(pk=stream_id)
                if stream.class_level_id != int(class_level_id):
                    errors['stream'] = [
                        f'Stream "{stream}" does not belong to the selected class level.'
                    ]
            except StreamClass.DoesNotExist:
                errors['stream'] = ['Selected stream does not exist.']
        
        # Check for duplicate assignment
        if class_level_id and academic_year_id:
            duplicate = ClassTeacherAssignment.objects.filter(
                class_level_id=class_level_id,
                stream_class_id=stream_id or None,
                academic_year_id=academic_year_id,
            )
            if duplicate.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    'A class teacher is already assigned to this class/stream/year combination.'
                ]
        
        # Check if staff is already a class teacher for another class in same year
        if staff_id and academic_year_id and is_active:
            conflict = ClassTeacherAssignment.objects.filter(
                staff_id=staff_id,
                academic_year_id=academic_year_id,
                is_active=True
            )
            if conflict.exists():
                conflict_assignment = conflict.first()
                conflict_display = f"{conflict_assignment.class_level.name}"
                if conflict_assignment.stream_class:
                    conflict_display += f" - {conflict_assignment.stream_class.name}"
                errors['__all__'] = errors.get('__all__', []) + [
                    f'{self._get_staff_name(staff_id)} is already an active class teacher '
                    f'for {conflict_display} in {self._get_academic_year_name(academic_year_id)}. '
                    f'A staff member cannot be class teacher for two different classes in the same academic year.'
                ]
        
        return errors

    def _get_staff_name(self, staff_id):
        """Helper to get staff name for error messages."""
        try:
            staff = Staff.objects.get(pk=staff_id)
            return staff.get_full_name()
        except Staff.DoesNotExist:
            return 'This staff member'

    def _get_academic_year_name(self, year_id):
        """Helper to get academic year name for error messages."""
        try:
            year = AcademicYear.objects.get(pk=year_id)
            return year.name
        except AcademicYear.DoesNotExist:
            return 'this academic year'

    def get(self, request):
        """Display the create class teacher assignment form."""
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        class_levels = ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order')
        streams = StreamClass.objects.all().select_related('class_level').order_by('class_level', 'stream_letter')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        # Get active academic year for default selection
        active_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        context = {
            'staff_members': staff_members,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            'active_academic_year': active_academic_year,
            'title': 'Create Class Teacher Assignment',
            'is_edit': False,
            'assignment': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create class teacher assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Get form data
        staff_id = request.POST.get('staff')
        class_level_id = request.POST.get('class_level')
        stream_id = request.POST.get('stream')
        academic_year_id = request.POST.get('academic_year')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'class_level' in errors:
                    message = errors['class_level'][0]
                elif 'stream' in errors:
                    message = errors['stream'][0]
                elif 'academic_year' in errors:
                    message = errors['academic_year'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Class Teacher Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                staff = Staff.objects.get(pk=staff_id)
                class_level = ClassLevel.objects.get(pk=class_level_id)
                academic_year = AcademicYear.objects.get(pk=academic_year_id)
                
                assignment = ClassTeacherAssignment(
                    staff=staff,
                    class_level=class_level,
                    stream_class_id=stream_id or None,
                    academic_year=academic_year,
                    start_date=start_date,
                    end_date=end_date if end_date else None,
                    is_active=is_active,
                    remarks=remarks
                )
                assignment.full_clean()
                assignment.save()
                
                stream_text = f" - {assignment.stream_class}" if assignment.stream_class else ""
                message = (
                    f'{staff.get_full_name()} assigned as Class Teacher for '
                    f'{class_level.name}{stream_text} for {academic_year.name} successfully!'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:class_teacher_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': staff.get_full_name(),
                            'class_level': class_level.name,
                            'stream': assignment.stream_class.name if assignment.stream_class else None,
                            'academic_year': academic_year.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:class_teacher_assignment_detail', pk=assignment.pk)
                
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
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Class Teacher Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error creating class teacher assignment: {e}", exc_info=True)
            error_msg = f'Error creating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            active_academic_year = AcademicYear.objects.filter(is_active=True).first()
            
            return render(request, self.template_name, {
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'active_academic_year': active_academic_year,
                'title': 'Create Class Teacher Assignment',
                'is_edit': False,
                'assignment': None,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class ClassTeacherAssignmentDetailView(ManagementRequiredMixin, View):
    """View to display class teacher assignment details."""
    template_name = 'portal_management/hr/class_teacher_assignments/detail.html'

    def get(self, request, pk):
        """Display class teacher assignment details."""
        assignment = get_object_or_404(
            ClassTeacherAssignment.objects.select_related(
                'staff', 'class_level', 'stream_class', 'academic_year'
            ),
            pk=pk
        )
        
        # Get related information
        staff = assignment.staff
        staff_class_teacher_count = ClassTeacherAssignment.objects.filter(
            staff=staff,
            academic_year=assignment.academic_year,
            is_active=True
        ).count()
        
        staff_total_assignments = ClassTeacherAssignment.objects.filter(
            staff=staff
        ).count()
        
        # Get other class teachers in the same academic year
        other_class_teachers = ClassTeacherAssignment.objects.filter(
            academic_year=assignment.academic_year,
            is_active=True
        ).exclude(pk=pk).select_related('staff', 'class_level', 'stream_class')[:10]
        
        # Calculate duration
        duration = None
        end_date = assignment.end_date or timezone.now().date()
        duration = (end_date - assignment.start_date).days + 1 if assignment.start_date else None
        
        # Check if assignment is expired
        is_expired = assignment.end_date and assignment.end_date < timezone.now().date()
        
        context = {
            'assignment': assignment,
            'staff': staff,
            'class_level': assignment.class_level,
            'stream': assignment.stream_class,
            'academic_year': assignment.academic_year,
            'staff_class_teacher_count': staff_class_teacher_count,
            'staff_total_assignments': staff_total_assignments,
            'other_class_teachers': other_class_teachers,
            'duration': duration,
            'is_expired': is_expired,
        }
        return render(request, self.template_name, context)


class ClassTeacherAssignmentUpdateView(ManagementRequiredMixin, View):
    """View to update an existing class teacher assignment."""
    template_name = 'portal_management/hr/class_teacher_assignments/form.html'

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

    def _validate_assignment_data(self, data, assignment_id=None):
        """Validate class teacher assignment data before saving."""
        errors = {}
        
        staff_id = data.get('staff')
        class_level_id = data.get('class_level')
        stream_id = data.get('stream')
        academic_year_id = data.get('academic_year')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        is_active = data.get('is_active') == 'true'
        
        # Validate required fields
        if not staff_id:
            errors['staff'] = ['Staff member is required.']
        
        if not class_level_id:
            errors['class_level'] = ['Class level is required.']
        
        if not academic_year_id:
            errors['academic_year'] = ['Academic year is required.']
        
        if not start_date:
            errors['start_date'] = ['Start date is required.']
        
        # Validate dates
        if start_date and end_date:
            if end_date <= start_date:
                errors['end_date'] = ['End date must be after start date.']
        
        # Validate stream belongs to class level
        if stream_id and class_level_id:
            try:
                stream = StreamClass.objects.get(pk=stream_id)
                if stream.class_level_id != int(class_level_id):
                    errors['stream'] = [
                        f'Stream "{stream}" does not belong to the selected class level.'
                    ]
            except StreamClass.DoesNotExist:
                errors['stream'] = ['Selected stream does not exist.']
        
        # Check for duplicate assignment (excluding current)
        if class_level_id and academic_year_id:
            duplicate = ClassTeacherAssignment.objects.filter(
                class_level_id=class_level_id,
                stream_class_id=stream_id or None,
                academic_year_id=academic_year_id,
            ).exclude(pk=assignment_id)
            if duplicate.exists():
                errors['__all__'] = errors.get('__all__', []) + [
                    'A class teacher is already assigned to this class/stream/year combination.'
                ]
        
        # Check if staff is already a class teacher for another class in same year
        if staff_id and academic_year_id and is_active:
            conflict = ClassTeacherAssignment.objects.filter(
                staff_id=staff_id,
                academic_year_id=academic_year_id,
                is_active=True
            ).exclude(pk=assignment_id)
            if conflict.exists():
                conflict_assignment = conflict.first()
                conflict_display = f"{conflict_assignment.class_level.name}"
                if conflict_assignment.stream_class:
                    conflict_display += f" - {conflict_assignment.stream_class.name}"
                errors['__all__'] = errors.get('__all__', []) + [
                    f'{self._get_staff_name(staff_id)} is already an active class teacher '
                    f'for {conflict_display} in {self._get_academic_year_name(academic_year_id)}. '
                    f'A staff member cannot be class teacher for two different classes in the same academic year.'
                ]
        
        return errors

    def _get_staff_name(self, staff_id):
        """Helper to get staff name for error messages."""
        try:
            staff = Staff.objects.get(pk=staff_id)
            return staff.get_full_name()
        except Staff.DoesNotExist:
            return 'This staff member'

    def _get_academic_year_name(self, year_id):
        """Helper to get academic year name for error messages."""
        try:
            year = AcademicYear.objects.get(pk=year_id)
            return year.name
        except AcademicYear.DoesNotExist:
            return 'this academic year'

    def get(self, request, pk):
        """Display the edit class teacher assignment form."""
        assignment = get_object_or_404(
            ClassTeacherAssignment.objects.select_related(
                'staff', 'class_level', 'stream_class', 'academic_year'
            ),
            pk=pk
        )
        
        staff_members = Staff.objects.all().order_by('first_name', 'last_name')
        class_levels = ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order')
        streams = StreamClass.objects.all().select_related('class_level').order_by('class_level', 'stream_letter')
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        context = {
            'assignment': assignment,
            'staff_members': staff_members,
            'class_levels': class_levels,
            'streams': streams,
            'academic_years': academic_years,
            'title': f'Edit Class Teacher Assignment: {assignment.staff.get_full_name()} - {assignment.class_level.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit class teacher assignment form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(ClassTeacherAssignment, pk=pk)
        
        # Get form data
        staff_id = request.POST.get('staff')
        class_level_id = request.POST.get('class_level')
        stream_id = request.POST.get('stream')
        academic_year_id = request.POST.get('academic_year')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        remarks = request.POST.get('remarks', '').strip()
        
        # Validate data
        errors = self._validate_assignment_data(request.POST, assignment.pk)
        
        if errors:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in errors:
                    message = errors['__all__'][0]
                elif 'staff' in errors:
                    message = errors['staff'][0]
                elif 'class_level' in errors:
                    message = errors['class_level'][0]
                elif 'stream' in errors:
                    message = errors['stream'][0]
                elif 'academic_year' in errors:
                    message = errors['academic_year'][0]
                elif 'start_date' in errors:
                    message = errors['start_date'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)
            
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Class Teacher Assignment: {assignment.staff.get_full_name()} - {assignment.class_level.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors,
            })
        
        try:
            with transaction.atomic():
                # Update assignment
                assignment.staff_id = staff_id
                assignment.class_level_id = class_level_id
                assignment.stream_class_id = stream_id or None
                assignment.academic_year_id = academic_year_id
                assignment.start_date = start_date
                assignment.end_date = end_date if end_date else None
                assignment.is_active = is_active
                assignment.remarks = remarks
                
                assignment.full_clean()
                assignment.save()
                
                stream_text = f" - {assignment.stream_class}" if assignment.stream_class else ""
                message = (
                    f'Class teacher assignment for {assignment.staff.get_full_name()} updated successfully! '
                    f'Now assigned as Class Teacher for {assignment.class_level.name}{stream_text} '
                    f'for {assignment.academic_year.name}.'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:class_teacher_assignment_detail', args=[assignment.pk]),
                        'assignment': {
                            'id': assignment.pk,
                            'staff': assignment.staff.get_full_name(),
                            'class_level': assignment.class_level.name,
                            'stream': assignment.stream_class.name if assignment.stream_class else None,
                            'academic_year': assignment.academic_year.name,
                            'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                            'is_active': assignment.is_active,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:class_teacher_assignment_detail', pk=assignment.pk)
                
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
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Class Teacher Assignment: {assignment.staff.get_full_name()} - {assignment.class_level.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors,
            })
            
        except Exception as e:
            logger.error(f"Error updating class teacher assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error updating assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            staff_members = Staff.objects.all().order_by('first_name', 'last_name')
            class_levels = ClassLevel.objects.all().select_related('educational_level')
            streams = StreamClass.objects.all().select_related('class_level')
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            
            return render(request, self.template_name, {
                'assignment': assignment,
                'staff_members': staff_members,
                'class_levels': class_levels,
                'streams': streams,
                'academic_years': academic_years,
                'title': f'Edit Class Teacher Assignment: {assignment.staff.get_full_name()} - {assignment.class_level.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg],
            })


class ClassTeacherAssignmentDeleteView(ManagementRequiredMixin, View):
    """View to delete a class teacher assignment."""
    
    def post(self, request, pk):
        """Handle class teacher assignment deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(ClassTeacherAssignment, pk=pk)
        
        try:
            with transaction.atomic():
                # Store info for message
                staff_name = assignment.staff.get_full_name()
                class_name = assignment.class_level.name
                stream_name = f" - {assignment.stream_class}" if assignment.stream_class else ""
                year_name = assignment.academic_year.name
                
                assignment.delete()
                
                message = (
                    f'Class teacher assignment for {staff_name} in {class_name}{stream_name} '
                    f'for {year_name} deleted successfully!'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:class_teacher_assignment_list')
            
        except Exception as e:
            logger.error(f"Error deleting class teacher assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:class_teacher_assignment_detail', pk=pk)


class ClassTeacherAssignmentEndView(ManagementRequiredMixin, View):
    """View to end an active class teacher assignment."""
    
    def post(self, request, pk):
        """End an active class teacher assignment (set end date to today)."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        assignment = get_object_or_404(ClassTeacherAssignment, pk=pk)
        
        if not assignment.is_active:
            error_msg = 'This assignment is already inactive.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:class_teacher_assignment_detail', pk=pk)
        
        try:
            with transaction.atomic():
                assignment.end_date = timezone.now().date()
                assignment.is_active = False
                assignment.save()
                
                message = f'Class teacher assignment for {assignment.staff.get_full_name()} in {assignment.class_level.name} has been ended.'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:class_teacher_assignment_detail', pk=assignment.pk)
                
        except Exception as e:
            logger.error(f"Error ending class teacher assignment {pk}: {e}", exc_info=True)
            error_msg = f'Error ending assignment: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:class_teacher_assignment_detail', pk=pk)


class ClassTeacherAssignmentSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching class teacher assignments (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered class teacher assignments for autocomplete."""
        term = request.GET.get('term', '').strip()
        staff_id = request.GET.get('staff')
        class_level_id = request.GET.get('class_level')
        academic_year_id = request.GET.get('academic_year')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = ClassTeacherAssignment.objects.all().select_related(
            'staff', 'class_level', 'stream_class', 'academic_year'
        )
        
        if staff_id:
            queryset = queryset.filter(staff_id=staff_id)
        
        if class_level_id:
            queryset = queryset.filter(class_level_id=class_level_id)
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        if term:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=term) |
                Q(staff__last_name__icontains=term) |
                Q(class_level__name__icontains=term) |
                Q(stream_class__name__icontains=term)
            )
        
        queryset = queryset.order_by('-academic_year__start_date', 'class_level')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        assignments = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': assignment.pk,
                'text': (
                    f"{assignment.staff.get_full_name()} - "
                    f"{assignment.class_level.name}{assignment.stream_class.name if assignment.stream_class else ''} "
                    f"({assignment.academic_year.name})"
                ),
                'staff': assignment.staff.get_full_name(),
                'class_level': assignment.class_level.name,
                'stream': assignment.stream_class.name if assignment.stream_class else None,
                'academic_year': assignment.academic_year.name,
                'start_date': assignment.start_date.strftime('%Y-%m-%d'),
                'is_active': assignment.is_active,
            }
            for assignment in assignments
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })


class ClassTeacherAssignmentLoadView(ManagementRequiredMixin, View):
    """View to display class teacher load summary."""
    template_name = 'portal_management/hr/class_teacher_assignments/load.html'

    def get(self, request):
        """Display class teacher assignments for a selected academic year."""
        academic_year_id = request.GET.get('academic_year')
        
        if academic_year_id:
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        else:
            academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not academic_year:
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            context = {
                'academic_years': academic_years,
                'no_active_year': True,
            }
            return render(request, self.template_name, context)
        
        # Get all class teacher assignments for this academic year
        assignments = ClassTeacherAssignment.objects.filter(
            academic_year=academic_year,
            is_active=True
        ).select_related(
            'staff', 'class_level', 'stream_class', 'class_level__educational_level'
        ).order_by(
            'class_level__educational_level__level_type',  # Order by level type (NURSERY, PRIMARY, O_LEVEL, A_LEVEL)
            'class_level__order', 
            'stream_class'
        )
        
        # Group by class level
        classes_with_teachers = {}
        for assignment in assignments:
            class_key = f"{assignment.class_level.id}"
            if class_key not in classes_with_teachers:
                classes_with_teachers[class_key] = {
                    'class_level': assignment.class_level,
                    'assignments': []
                }
            classes_with_teachers[class_key]['assignments'].append(assignment)
        
        # Convert to list and sort by educational level type and class order
        # Define order for level types
        level_type_order = {
            'NURSERY': 1,
            'PRIMARY': 2,
            'O_LEVEL': 3,
            'A_LEVEL': 4,
        }
        
        classes_list = sorted(
            classes_with_teachers.values(),
            key=lambda x: (
                level_type_order.get(x['class_level'].educational_level.level_type, 999),
                x['class_level'].order
            )
        )
        
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        # Calculate stream count
        stream_count = 0
        for class_data in classes_list:
            for assignment in class_data['assignments']:
                if assignment.stream_class:
                    stream_count += 1
        
        context = {
            'classes_with_teachers': classes_list,
            'academic_year': academic_year,
            'academic_years': academic_years,
            'selected_academic_year': academic_year.id,
            'total_assignments': assignments.count(),
            'total_classes': len(classes_list),
            'stream_count': stream_count,
        }
        
        return render(request, self.template_name, context)