# portal_management/views/division_scale_views.py

import logging
from decimal import Decimal
from django.db import models, transaction
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import DivisionScale, EducationalLevel

logger = logging.getLogger(__name__)


class DivisionScaleListView(ManagementRequiredMixin, View):
    """View to list all division scales with filtering and search."""
    template_name = 'portal_management/academic/division_scales/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = DivisionScale.objects.all().select_related('education_level')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(division__icontains=search) |
                Q(description__icontains=search) |
                Q(education_level__name__icontains=search)
            )
        
        # Educational level filter
        education_level_id = request.GET.get('education_level')
        if education_level_id:
            queryset = queryset.filter(education_level_id=education_level_id)
        
        # Division filter
        division = request.GET.get('division')
        if division:
            queryset = queryset.filter(division=division)
        
        return queryset.order_by('education_level', 'min_points')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        
        # Get educational levels with division scales (O-Level and A-Level only)
        educational_levels = EducationalLevel.objects.filter(
            level_type__in=['O_LEVEL', 'A_LEVEL'],
            division_scales__isnull=False
        ).distinct().count()
        
        return {
            'total_scales': total,
            'educational_levels_with_scales': educational_levels,
        }

    def get(self, request):
        """Handle GET request - display division scale list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        scales = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get all educational levels (O-Level and A-Level only) for filter dropdown
        educational_levels = EducationalLevel.objects.filter(
            level_type__in=['O_LEVEL', 'A_LEVEL']
        ).order_by('code')
        
        context = {
            'scales': scales,
            'educational_levels': educational_levels,
            'total_scales': total_count,
            'educational_levels_with_scales': EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL'],
                division_scales__isnull=False
            ).distinct().count(),
            'search_query': request.GET.get('search', ''),
            'selected_education_level': request.GET.get('education_level', ''),
            'selected_division': request.GET.get('division', ''),
            'division_choices': DivisionScale.DIVISION_CHOICES,
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class DivisionScaleCreateView(ManagementRequiredMixin, View):
    """View to create a new division scale."""
    template_name = 'portal_management/academic/division_scales/form.html'

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

    def _validate_division_data(self, education_level, division, min_points, max_points, scale_id=None):
        """
        Comprehensive validation for division scale.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert values if needed
        if isinstance(min_points, str):
            try:
                min_points = int(min_points)
            except:
                errors['min_points'] = ['Invalid minimum points value.']
        
        if isinstance(max_points, str):
            try:
                max_points = int(max_points)
            except:
                errors['max_points'] = ['Invalid maximum points value.']
        
        # Validate min_points < max_points
        if min_points >= max_points:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Minimum points ({min_points}) must be less than maximum points ({max_points}).'
            ]
        
        # Validate points are within reasonable range (0-30 for typical O-Level/A-Level)
        if min_points < 0:
            errors['min_points'] = ['Minimum points cannot be negative.']
        
        if max_points < 0:
            errors['max_points'] = ['Maximum points cannot be negative.']
        
        if max_points > 30:
            errors['max_points'] = ['Maximum points cannot exceed 30.']
        
        # Check for overlapping point ranges for the same education level
        overlapping = DivisionScale.objects.filter(
            education_level=education_level,
            min_points__lt=max_points,
            max_points__gt=min_points,
        ).exclude(pk=scale_id)
        
        if overlapping.exists():
            overlapping_scale = overlapping.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Points range {min_points}–{max_points} overlaps with existing division '
                f'"{overlapping_scale.get_division_display()}" ({overlapping_scale.min_points}–{overlapping_scale.max_points}).'
            ]
        
        # Check if division already exists for this educational level
        if DivisionScale.objects.filter(
            education_level=education_level,
            division=division
        ).exclude(pk=scale_id).exists():
            errors['division'] = [f'Division "{division}" already exists for {education_level.name}.']
        
        # Validate division value
        valid_divisions = [d[0] for d in DivisionScale.DIVISION_CHOICES]
        if division not in valid_divisions:
            errors['division'] = [f'Invalid division. Must be one of: {", ".join(valid_divisions)}.']
        
        return len(errors) == 0, errors

    def get(self, request):
        """Display the create division scale form."""
        educational_levels = EducationalLevel.objects.filter(
            level_type__in=['O_LEVEL', 'A_LEVEL']
        ).order_by('code')
        
        context = {
            'educational_levels': educational_levels,
            'division_choices': DivisionScale.DIVISION_CHOICES,
            'title': 'Create Division Scale',
            'is_edit': False,
            'scale': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create division scale form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        education_level_id = request.POST.get('education_level')
        division = request.POST.get('division')
        min_points = request.POST.get('min_points')
        max_points = request.POST.get('max_points')
        description = request.POST.get('description', '')
        
        # Validate required fields
        if not all([education_level_id, division, min_points, max_points]):
            errors = {}
            if not education_level_id:
                errors['education_level'] = ['Educational level is required.']
            if not division:
                errors['division'] = ['Division is required.']
            if not min_points:
                errors['min_points'] = ['Minimum points is required.']
            if not max_points:
                errors['max_points'] = ['Maximum points is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': 'Create Division Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            education_level = get_object_or_404(EducationalLevel, pk=education_level_id)
            
            # Validate educational level type
            if education_level.level_type not in ['O_LEVEL', 'A_LEVEL']:
                error_msg = f'Division scales are only applicable to O-Level and A-Level. {education_level.name} is {education_level.get_level_type_display()}.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': {'education_level': [error_msg]}
                    }, status=400)
                
                educational_levels = EducationalLevel.objects.filter(
                    level_type__in=['O_LEVEL', 'A_LEVEL']
                ).order_by('code')
                return render(request, self.template_name, {
                    'educational_levels': educational_levels,
                    'division_choices': DivisionScale.DIVISION_CHOICES,
                    'title': 'Create Division Scale',
                    'is_edit': False,
                    'scale': None,
                    'form_data': request.POST,
                    'errors': {'education_level': [error_msg]}
                })
                
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Educational level not found.',
                    'errors': {'education_level': ['The selected educational level does not exist.']}
                }, status=404)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': 'Create Division Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': {'education_level': ['The selected educational level does not exist.']}
            })
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_division_data(
            education_level, division, min_points, max_points
        )
        
        if not is_valid:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in validation_errors:
                    message = validation_errors['__all__'][0]
                elif 'division' in validation_errors:
                    message = validation_errors['division'][0]
                elif 'min_points' in validation_errors:
                    message = validation_errors['min_points'][0]
                elif 'max_points' in validation_errors:
                    message = validation_errors['max_points'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': 'Create Division Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                scale = DivisionScale(
                    education_level=education_level,
                    division=division,
                    min_points=int(min_points),
                    max_points=int(max_points),
                    description=description
                )
                scale.full_clean()
                scale.save()
                
                message = f'Division scale for {education_level.name} - {scale.get_division_display()} created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:division_scale_detail', args=[scale.pk]),
                        'scale': {
                            'id': scale.pk,
                            'division': scale.division,
                            'division_display': scale.get_division_display(),
                            'min_points': scale.min_points,
                            'max_points': scale.max_points,
                            'education_level': education_level.name,
                            'education_level_id': education_level.pk,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:division_scale_detail', pk=scale.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': 'Create Division Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error creating division scale: {e}", exc_info=True)
            error_msg = f'Error creating division scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': 'Create Division Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class DivisionScaleDetailView(ManagementRequiredMixin, View):
    """View to display division scale details."""
    template_name = 'portal_management/academic/division_scales/detail.html'

    def get(self, request, pk):
        """Display division scale details."""
        scale = get_object_or_404(DivisionScale, pk=pk)
        
        # Get all scales for the same educational level
        sibling_scales = DivisionScale.objects.filter(
            education_level=scale.education_level
        ).exclude(pk=pk).order_by('min_points')
        
        # Calculate range width
        range_width = scale.max_points - scale.min_points
        
        context = {
            'scale': scale,
            'sibling_scales': sibling_scales,
            'education_level': scale.education_level,
            'range_width': range_width,
        }
        return render(request, self.template_name, context)


class DivisionScaleUpdateView(ManagementRequiredMixin, View):
    """View to update an existing division scale."""
    template_name = 'portal_management/academic/division_scales/form.html'

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

    def _validate_division_data(self, education_level, division, min_points, max_points, scale_id=None):
        """
        Comprehensive validation for division scale.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert values if needed
        if isinstance(min_points, str):
            try:
                min_points = int(min_points)
            except:
                errors['min_points'] = ['Invalid minimum points value.']
        
        if isinstance(max_points, str):
            try:
                max_points = int(max_points)
            except:
                errors['max_points'] = ['Invalid maximum points value.']
        
        # Validate min_points < max_points
        if min_points >= max_points:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Minimum points ({min_points}) must be less than maximum points ({max_points}).'
            ]
        
        # Validate points are within reasonable range (0-30 for typical O-Level/A-Level)
        if min_points < 0:
            errors['min_points'] = ['Minimum points cannot be negative.']
        
        if max_points < 0:
            errors['max_points'] = ['Maximum points cannot be negative.']
        
        if max_points > 30:
            errors['max_points'] = ['Maximum points cannot exceed 30.']
        
        # Check for overlapping point ranges for the same education level (excluding current)
        overlapping = DivisionScale.objects.filter(
            education_level=education_level,
            min_points__lt=max_points,
            max_points__gt=min_points,
        ).exclude(pk=scale_id)
        
        if overlapping.exists():
            overlapping_scale = overlapping.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Points range {min_points}–{max_points} overlaps with existing division '
                f'"{overlapping_scale.get_division_display()}" ({overlapping_scale.min_points}–{overlapping_scale.max_points}).'
            ]
        
        # Check if division already exists for this educational level (excluding current)
        if DivisionScale.objects.filter(
            education_level=education_level,
            division=division
        ).exclude(pk=scale_id).exists():
            errors['division'] = [f'Division "{division}" already exists for {education_level.name}.']
        
        # Validate division value
        valid_divisions = [d[0] for d in DivisionScale.DIVISION_CHOICES]
        if division not in valid_divisions:
            errors['division'] = [f'Invalid division. Must be one of: {", ".join(valid_divisions)}.']
        
        return len(errors) == 0, errors

    def get(self, request, pk):
        """Display the edit division scale form."""
        scale = get_object_or_404(DivisionScale, pk=pk)
        educational_levels = EducationalLevel.objects.filter(
            level_type__in=['O_LEVEL', 'A_LEVEL']
        ).order_by('code')
        
        context = {
            'scale': scale,
            'educational_levels': educational_levels,
            'division_choices': DivisionScale.DIVISION_CHOICES,
            'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit division scale form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        scale = get_object_or_404(DivisionScale, pk=pk)
        
        education_level_id = request.POST.get('education_level')
        division = request.POST.get('division')
        min_points = request.POST.get('min_points')
        max_points = request.POST.get('max_points')
        description = request.POST.get('description', '')
        
        # Validate required fields
        if not all([education_level_id, division, min_points, max_points]):
            errors = {}
            if not education_level_id:
                errors['education_level'] = ['Educational level is required.']
            if not division:
                errors['division'] = ['Division is required.']
            if not min_points:
                errors['min_points'] = ['Minimum points is required.']
            if not max_points:
                errors['max_points'] = ['Maximum points is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            education_level = get_object_or_404(EducationalLevel, pk=education_level_id)
            
            # Validate educational level type
            if education_level.level_type not in ['O_LEVEL', 'A_LEVEL']:
                error_msg = f'Division scales are only applicable to O-Level and A-Level. {education_level.name} is {education_level.get_level_type_display()}.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': {'education_level': [error_msg]}
                    }, status=400)
                
                educational_levels = EducationalLevel.objects.filter(
                    level_type__in=['O_LEVEL', 'A_LEVEL']
                ).order_by('code')
                return render(request, self.template_name, {
                    'scale': scale,
                    'educational_levels': educational_levels,
                    'division_choices': DivisionScale.DIVISION_CHOICES,
                    'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                    'is_edit': True,
                    'form_data': request.POST,
                    'errors': {'education_level': [error_msg]}
                })
                
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Educational level not found.',
                    'errors': {'education_level': ['The selected educational level does not exist.']}
                }, status=404)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': {'education_level': ['The selected educational level does not exist.']}
            })
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_division_data(
            education_level, division, min_points, max_points, scale.pk
        )
        
        if not is_valid:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in validation_errors:
                    message = validation_errors['__all__'][0]
                elif 'division' in validation_errors:
                    message = validation_errors['division'][0]
                elif 'min_points' in validation_errors:
                    message = validation_errors['min_points'][0]
                elif 'max_points' in validation_errors:
                    message = validation_errors['max_points'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                scale.education_level = education_level
                scale.division = division
                scale.min_points = int(min_points)
                scale.max_points = int(max_points)
                scale.description = description
                
                scale.full_clean()
                scale.save()
                
                message = f'Division scale for {education_level.name} - {scale.get_division_display()} updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:division_scale_detail', args=[scale.pk]),
                        'scale': {
                            'id': scale.pk,
                            'division': scale.division,
                            'division_display': scale.get_division_display(),
                            'min_points': scale.min_points,
                            'max_points': scale.max_points,
                            'education_level': education_level.name,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:division_scale_detail', pk=scale.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error updating division scale {pk}: {e}", exc_info=True)
            error_msg = f'Error updating division scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            educational_levels = EducationalLevel.objects.filter(
                level_type__in=['O_LEVEL', 'A_LEVEL']
            ).order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'division_choices': DivisionScale.DIVISION_CHOICES,
                'title': f'Edit Division Scale: {scale.education_level.name} - {scale.get_division_display()}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class DivisionScaleDeleteView(ManagementRequiredMixin, View):
    """View to delete a division scale."""
    
    def check_dependencies(self, scale):
        """Check if division scale has dependencies that prevent deletion."""
        dependencies = []
        
        # Check for student results that use this division scale
        # This would depend on your StudentExamMetrics model
        # if hasattr(scale, 'student_metrics'):
        #     metric_count = scale.student_metrics.count()
        #     if metric_count > 0:
        #         dependencies.append(f'{metric_count} student result(s)')
        
        return dependencies

    def post(self, request, pk):
        """Handle division scale deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        scale = get_object_or_404(DivisionScale, pk=pk)
        scale_name = f"{scale.education_level.name} - {scale.get_division_display()}"
        
        # Check for dependencies
        dependencies = self.check_dependencies(scale)
        
        if dependencies:
            error_msg = (
                f'Cannot delete "{scale_name}" because it has associated {", ".join(dependencies)}. '
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
            return redirect('management:division_scale_detail', pk=pk)
        
        try:
            with transaction.atomic():
                education_level_name = scale.education_level.name
                division = scale.get_division_display()
                scale.delete()
            
            message = f'Division scale "{division}" for {education_level_name} deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:division_scale_list')
            
        except Exception as e:
            logger.error(f"Error deleting division scale {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting division scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:division_scale_detail', pk=pk)


class DivisionScaleCheckDependenciesView(ManagementRequiredMixin, View):
    """AJAX view to check if a division scale has dependencies."""
    
    def get(self, request, pk):
        """Return dependency information for a division scale."""
        scale = get_object_or_404(DivisionScale, pk=pk)
        
        dependencies = []
        
        # Check for student metrics
        # if hasattr(scale, 'student_metrics'):
        #     metric_count = scale.student_metrics.count()
        #     if metric_count > 0:
        #         dependencies.append(f'{metric_count} student result(s)')
        
        return JsonResponse({
            'has_dependencies': len(dependencies) > 0,
            'dependencies': dependencies,
            'scale_id': scale.pk,
            'scale_name': f"{scale.education_level.name} - {scale.get_division_display()}",
        })


class DivisionScaleSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching division scales (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered division scales for autocomplete."""
        term = request.GET.get('term', '').strip()
        education_level_id = request.GET.get('education_level')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = DivisionScale.objects.all().select_related('education_level')
        
        if education_level_id:
            queryset = queryset.filter(education_level_id=education_level_id)
        
        if term:
            queryset = queryset.filter(
                Q(division__icontains=term) |
                Q(education_level__name__icontains=term) |
                Q(description__icontains=term)
            )
        
        queryset = queryset.order_by('education_level', 'min_points')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        scales = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': scale.pk,
                'text': f"{scale.education_level.name} - {scale.get_division_display()} ({scale.min_points}-{scale.max_points} pts)",
                'division': scale.division,
                'division_display': scale.get_division_display(),
                'min_points': scale.min_points,
                'max_points': scale.max_points,
                'education_level': scale.education_level.name,
            }
            for scale in scales
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })