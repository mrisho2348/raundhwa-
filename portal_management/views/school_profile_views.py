# portal_management/views/school_profile_views.py

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from core.mixins import ManagementRequiredMixin
from core.models import EducationalLevel, SchoolProfile, Staff
from portal_management.forms.school_profile_form import SchoolProfileForm
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

class SchoolProfileListView(ManagementRequiredMixin, View):
    """List all school profiles."""
    template_name = 'portal_management/school_profiles/list.html'
    
    def get(self, request):
        # Start with base queryset
        profiles = SchoolProfile.objects.select_related(
            'educational_level', 'contact_person__user'
        ).order_by('code')
        
        # Store original for reference
        all_profiles = profiles
        
        # Apply filters
        level_filter = request.GET.get('level')
        active_filter = request.GET.get('active')
        search = request.GET.get('search', '')
        
        # Apply educational level filter
        if level_filter:
            profiles = profiles.filter(educational_level_id=level_filter)
        
        # Apply active status filter
        if active_filter == 'true':
            profiles = profiles.filter(is_active=True)
        elif active_filter == 'false':
            profiles = profiles.filter(is_active=False)
        
        # Apply search filter
        if search:
            profiles = profiles.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(registration_number__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        # Calculate statistics
        # Show filtered counts or total counts based on whether filters are applied
        if level_filter or active_filter or search:
            # Show filtered statistics
            total_count = profiles.count()
            active_count = profiles.filter(is_active=True).count()
            inactive_count = profiles.filter(is_active=False).count()
        else:
            # Show total statistics
            total_count = all_profiles.count()
            active_count = all_profiles.filter(is_active=True).count()
            inactive_count = all_profiles.filter(is_active=False).count()
        
        # Get educational levels for filter dropdown
        educational_levels = EducationalLevel.objects.order_by('name')
        
        context = {
            'profiles': profiles,
            'total_count': total_count,
            'active_count': active_count,
            'inactive_count': inactive_count,
            'level_filter': level_filter,
            'active_filter': active_filter,
            'search': search,
            'educational_levels': educational_levels,
        }
        
        return render(request, self.template_name, context)


class SchoolProfileCreateView(ManagementRequiredMixin, View):
    """Create a new school profile with validation."""
    template_name = 'portal_management/school_profiles/form.html'
    
    def get(self, request):
        form = SchoolProfileForm()
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add School Profile',
            'is_edit': False,
        })
    
    def post(self, request):
        """Handle POST request with comprehensive validation."""
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        form = SchoolProfileForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Additional validation
                    profile = self.validate_and_save_profile(form, request)
                    
                    # Prepare success response
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': f'School profile "{profile.name}" created successfully.',
                            'profile_id': profile.pk,
                            'redirect_url': self.get_redirect_url(request, profile)
                        })
                    else:
                        messages.success(
                            request,
                            f'School profile "{profile.name}" created successfully.'
                        )
                        return redirect(self.get_redirect_url(request, profile))
                        
            except ValidationError as e:
                error_message = str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': {'__all__': [error_message]}
                    }, status=400)
                else:
                    messages.error(request, error_message)
                    
            except Exception as e:
                error_message = f'Error creating school profile: {str(e)}'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': {'__all__': [error_message]}
                    }, status=500)
                else:
                    messages.error(request, error_message)
        else:
            # Form has validation errors
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': self.get_form_errors(form)
                }, status=400)
            else:
                messages.error(request, 'Please correct the errors below.')
        
        # Return form with errors
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add School Profile',
            'is_edit': False,
        })
    
    def validate_and_save_profile(self, form, request):
        """Validate business rules and save profile."""
        profile = form.save(commit=False)
        
        # Validate uniqueness of code and registration number
        self.validate_unique_fields(profile)
        
        # Validate active profile per educational level
        self.validate_active_profile_limit(profile)
        
        # Validate contact person if provided
        if profile.contact_person:
            self.validate_contact_person(profile.contact_person)
        
        # Validate email format if provided
        if profile.email:
            try:
                validate_email(profile.email)
            except ValidationError:
                raise ValidationError('Invalid email address format.')
        
        # Validate phone numbers (basic validation)
        if profile.phone:
            self.validate_phone_number(profile.phone)
        if profile.alternative_phone:
            self.validate_phone_number(profile.alternative_phone)
        
        # Validate website URL format
        if profile.website:
            self.validate_website_url(profile.website)
        
        profile.save()
        return profile
    
    def validate_unique_fields(self, profile):
        """Validate unique constraints for code and registration number."""
        # Check if code already exists (excluding current profile if updating)
        if SchoolProfile.objects.filter(
            code=profile.code
        ).exclude(pk=profile.pk).exists():
            raise ValidationError(
                f'A school profile with code "{profile.code}" already exists.'
            )
        
        # Check if registration number already exists
        if SchoolProfile.objects.filter(
            registration_number=profile.registration_number
        ).exclude(pk=profile.pk).exists():
            raise ValidationError(
                f'A school profile with registration number '
                f'"{profile.registration_number}" already exists.'
            )
    
    def validate_active_profile_limit(self, profile):
        """Ensure only one active profile per educational level."""
        if profile.is_active:
            # Check for existing active profile at the same educational level
            existing_active = SchoolProfile.objects.filter(
                educational_level=profile.educational_level,
                is_active=True
            ).exclude(pk=profile.pk)
            
            if existing_active.exists():
                level_name = profile.educational_level.name if profile.educational_level else 'Main'
                raise ValidationError(
                    f'An active school profile already exists for {level_name} level. '
                    f'Please deactivate the existing profile first.'
                )
    
    def validate_contact_person(self, contact_person):
        """Validate that the contact person exists and has appropriate role."""
      
        
        if not Staff.objects.filter(pk=contact_person.pk).exists():
            raise ValidationError('Selected contact person does not exist.')
        
        # Optional: Check if the staff member has appropriate role
        if not contact_person.is_head_of_institution:
            # You can add a warning but not block creation
            pass
    
    def validate_phone_number(self, phone):
        """Validate phone number format."""
        import re
        # Basic phone validation - adjust regex as needed
        phone_pattern = r'^[\+]?[0-9\s\-\(\)]{10,15}$'
        if not re.match(phone_pattern, phone):
            raise ValidationError('Invalid phone number format.')
    
    def validate_website_url(self, website):
        """Validate website URL format."""
        import re
        url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        if not re.match(url_pattern, website):
            raise ValidationError('Invalid website URL format. Use http:// or https://')
    
    def get_redirect_url(self, request, profile):
        """Determine redirect URL based on action."""
        action = request.POST.get('action', 'save')
        
        if action == 'save_and_continue':
            return reverse('management:school_profile_edit', kwargs={'pk': profile.pk})
        elif action == 'save_and_add':
            return reverse('management:school_profile_create')
        else:
            return reverse('management:school_profile_detail', kwargs={'pk': profile.pk})
    
    def get_form_errors(self, form):
        """Convert form errors to a JSON-serializable format."""
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = [str(error) for error in field_errors]
        return errors


class SchoolProfileUpdateView(ManagementRequiredMixin, View):
    """Update an existing school profile with validation."""
    template_name = 'portal_management/school_profiles/form.html'
    
    def get(self, request, pk):
        profile = get_object_or_404(SchoolProfile, pk=pk)
        form = SchoolProfileForm(instance=profile)
        
        return render(request, self.template_name, {
            'form': form,
            'profile': profile,
            'title': f'Edit - {profile.name}',
            'is_edit': True,
        })
    
    def post(self, request, pk):
        """Handle POST request with comprehensive validation."""
        profile = get_object_or_404(SchoolProfile, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        form = SchoolProfileForm(request.POST, request.FILES, instance=profile)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Validate and save with business rules
                    updated_profile = self.validate_and_update_profile(form, request, profile)
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': f'School profile "{updated_profile.name}" updated successfully.',
                            'profile_id': updated_profile.pk,
                            'redirect_url': self.get_redirect_url(request, updated_profile)
                        })
                    else:
                        messages.success(
                            request,
                            f'School profile "{updated_profile.name}" updated successfully.'
                        )
                        return redirect(self.get_redirect_url(request, updated_profile))
                        
            except ValidationError as e:
                error_message = str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': {'__all__': [error_message]}
                    }, status=400)
                else:
                    messages.error(request, error_message)
                    
            except Exception as e:
                error_message = f'Error updating school profile: {str(e)}'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_message,
                        'errors': {'__all__': [error_message]}
                    }, status=500)
                else:
                    messages.error(request, error_message)
        else:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': self.get_form_errors(form)
                }, status=400)
            else:
                messages.error(request, 'Please correct the errors below.')
        
        return render(request, self.template_name, {
            'form': form,
            'profile': profile,
            'title': f'Edit - {profile.name}',
            'is_edit': True,
        })
    
    def validate_and_update_profile(self, form, request, profile):
        """Validate business rules and update profile."""
        updated_profile = form.save(commit=False)
        
        # Store original status for comparison
        original_is_active = profile.is_active
        original_educational_level = profile.educational_level
        
        # Validate uniqueness (excluding current profile)
        self.validate_unique_fields(updated_profile, profile.pk)
        
        # Validate active profile per educational level
        self.validate_active_profile_limit(updated_profile, profile.pk)
        
        # Validate contact person if provided
        if updated_profile.contact_person:
            self.validate_contact_person(updated_profile.contact_person)
        
        # Validate email format if provided
        if updated_profile.email:
            try:
                validate_email(updated_profile.email)
            except ValidationError:
                raise ValidationError('Invalid email address format.')
        
        # Validate phone numbers
        if updated_profile.phone:
            self.validate_phone_number(updated_profile.phone)
        if updated_profile.alternative_phone:
            self.validate_phone_number(updated_profile.alternative_phone)
        
        # Validate website URL
        if updated_profile.website:
            self.validate_website_url(updated_profile.website)
        
        updated_profile.save()
        return updated_profile
    
    def validate_unique_fields(self, profile, exclude_pk):
        """Validate unique constraints for code and registration number."""
        # Check if code already exists (excluding current profile)
        if SchoolProfile.objects.filter(
            code=profile.code
        ).exclude(pk=exclude_pk).exists():
            raise ValidationError(
                f'A school profile with code "{profile.code}" already exists.'
            )
        
        # Check if registration number already exists
        if SchoolProfile.objects.filter(
            registration_number=profile.registration_number
        ).exclude(pk=exclude_pk).exists():
            raise ValidationError(
                f'A school profile with registration number '
                f'"{profile.registration_number}" already exists.'
            )
    
    def validate_active_profile_limit(self, profile, exclude_pk):
        """Ensure only one active profile per educational level."""
        if profile.is_active:
            # Check for existing active profile at the same educational level
            existing_active = SchoolProfile.objects.filter(
                educational_level=profile.educational_level,
                is_active=True
            ).exclude(pk=exclude_pk)
            
            if existing_active.exists():
                level_name = profile.educational_level.name if profile.educational_level else 'Main'
                raise ValidationError(
                    f'An active school profile already exists for {level_name} level. '
                    f'Please deactivate the existing profile first.'
                )
    
    def validate_contact_person(self, contact_person):
        """Validate that the contact person exists."""
        
        
        if not Staff.objects.filter(pk=contact_person.pk).exists():
            raise ValidationError('Selected contact person does not exist.')
    
    def validate_phone_number(self, phone):
        """Validate phone number format."""
        import re
        phone_pattern = r'^[\+]?[0-9\s\-\(\)]{10,15}$'
        if not re.match(phone_pattern, phone):
            raise ValidationError('Invalid phone number format.')
    
    def validate_website_url(self, website):
        """Validate website URL format."""
        import re
        url_pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
        if not re.match(url_pattern, website):
            raise ValidationError('Invalid website URL format. Use http:// or https://')
    
    def get_redirect_url(self, request, profile):
        """Determine redirect URL based on action."""
        action = request.POST.get('action', 'save')
        
        if action == 'save_and_continue':
            return reverse('management:school_profile_edit', kwargs={'pk': profile.pk})
        else:
            return reverse('management:school_profile_detail', kwargs={'pk': profile.pk})
    
    def get_form_errors(self, form):
        """Convert form errors to a JSON-serializable format."""
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = [str(error) for error in field_errors]
        return errors
 

class SchoolProfileDetailView(ManagementRequiredMixin, View):
    """Display school profile details."""
    template_name = 'portal_management/school_profiles/detail.html'
    
    def get(self, request, pk):
        profile = get_object_or_404(SchoolProfile, pk=pk)
        
        # Get additional statistics
        stats = {
            'total_students': profile.students.count() if hasattr(profile, 'students') else 0,
            'total_staff': profile.contact_person.count() if profile.contact_person else 0,
            'total_classes': profile.classes.count() if hasattr(profile, 'classes') else 0,
        }
        
        return render(request, self.template_name, {
            'profile': profile,
            'stats': stats,
            'title': f'{profile.name} - Details'
        })




class SchoolProfileDeleteView(ManagementRequiredMixin, View):
    """Delete a school profile."""
    
    def post(self, request, pk):
        profile = get_object_or_404(SchoolProfile, pk=pk)
        profile_name = profile.name
        
        # Check if profile is in use
        if hasattr(profile, 'class_levels') and profile.class_levels.exists():
            class_count = profile.class_levels.count()
            messages.error(
                request,
                f'Cannot delete "{profile_name}" because it is linked to '
                f'{class_count} class level(s). Please reassign these class levels first.'
            )
            return redirect('management:school_profile_detail', pk=pk)
        
        try:
            with transaction.atomic():
                profile.delete()
                messages.success(
                    request,
                    f'School profile "{profile_name}" deleted successfully.'
                )
        except Exception as e:
            messages.error(request, f'Error deleting school profile: {e}')
        
        return redirect('management:school_profile_list')


class SchoolProfileToggleActiveView(ManagementRequiredMixin, View):
    """Toggle active status of a school profile with validation."""
    
    def post(self, request, pk):
        """Toggle the active status of a school profile."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            profile = get_object_or_404(SchoolProfile, pk=pk)
            
            with transaction.atomic():
                if profile.is_active:
                    # Deactivating - always allowed
                    profile.is_active = False
                    profile.save()
                    message = f'School profile "{profile.name}" has been deactivated.'
                else:
                    # Activating - check if another active profile exists for same level
                    existing_active = SchoolProfile.objects.filter(
                        educational_level=profile.educational_level,
                        is_active=True
                    ).exclude(pk=profile.pk)
                    
                    if existing_active.exists():
                        level_name = profile.educational_level.name if profile.educational_level else 'Main'
                        raise ValidationError(
                            f'Cannot activate. An active school profile already exists '
                            f'for {level_name} level. Please deactivate it first.'
                        )
                    
                    profile.is_active = True
                    profile.save()
                    message = f'School profile "{profile.name}" has been activated.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'is_active': profile.is_active
                })
            else:
                messages.success(request, message)
                return redirect('management:school_profile_list')
                
        except ValidationError as e:
            error_message = str(e)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_message
                }, status=400)
            else:
                messages.error(request, error_message)
                return redirect('management:school_profile_list')
                
        except Exception as e:
            error_message = f'Error toggling status: {str(e)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_message
                }, status=500)
            else:
                messages.error(request, error_message)
                return redirect('management:school_profile_list')



class SchoolProfileSetDefaultView(ManagementRequiredMixin, View):
    """Set a school profile as the default/active main profile."""
    
    def post(self, request, pk):
        profile = get_object_or_404(SchoolProfile, pk=pk)
        
        try:
            with transaction.atomic():
                # If this is a main school profile (no educational level)
                if profile.educational_level is None:
                    # Deactivate all other main school profiles
                    SchoolProfile.objects.filter(
                        educational_level__isnull=True
                    ).exclude(pk=pk).update(is_active=False)
                    
                    # Activate this one
                    profile.is_active = True
                    profile.save()
                    
                    messages.success(
                        request,
                        f'"{profile.name}" is now the default school profile.'
                    )
                else:
                    messages.warning(
                        request,
                        'Only main school profiles (without educational level) '
                        'can be set as default.'
                    )
        except Exception as e:
            messages.error(request, f'Error setting default profile: {e}')
        
        return redirect('management:school_profile_detail', pk=pk)