# portal_management/views/grading_scale_views.py

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
from core.models import GradingScale, EducationalLevel

logger = logging.getLogger(__name__)


class GradingScaleListView(ManagementRequiredMixin, View):
    """View to list all grading scales with filtering and search."""
    template_name = 'portal_management/academic/grading_scales/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = GradingScale.objects.all().select_related('education_level')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(grade__icontains=search) |
                Q(description__icontains=search) |
                Q(education_level__name__icontains=search)
            )
        
        # Educational level filter
        education_level_id = request.GET.get('education_level')
        if education_level_id:
            queryset = queryset.filter(education_level_id=education_level_id)
        
        # Grade filter
        grade = request.GET.get('grade')
        if grade:
            queryset = queryset.filter(grade=grade)
        
        return queryset.order_by('education_level', '-min_mark')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        
        # Get educational levels with grading scales
        educational_levels = EducationalLevel.objects.filter(
            grading_scales__isnull=False
        ).distinct().count()
        
        return {
            'total_scales': total,
            'educational_levels_with_scales': educational_levels,
        }

    def get(self, request):
        """Handle GET request - display grading scale list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        scales = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get all educational levels for filter dropdown
        educational_levels = EducationalLevel.objects.all().order_by('code')
        
        context = {
            'scales': scales,
            'educational_levels': educational_levels,
            'total_scales': total_count,
            'educational_levels_with_scales': EducationalLevel.objects.filter(
                grading_scales__isnull=False
            ).distinct().count(),
            'search_query': request.GET.get('search', ''),
            'selected_education_level': request.GET.get('education_level', ''),
            'selected_grade': request.GET.get('grade', ''),
            'grade_choices': GradingScale.GRADE_CHOICES,
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class GradingScaleCreateView(ManagementRequiredMixin, View):
    """View to create a new grading scale."""
    template_name = 'portal_management/academic/grading_scales/form.html'

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

    def _validate_scale_data(self, education_level, grade, min_mark, max_mark, points, scale_id=None):
        """
        Comprehensive validation for grading scale.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert values if needed
        if isinstance(min_mark, str):
            try:
                min_mark = Decimal(min_mark)
            except:
                errors['min_mark'] = ['Invalid minimum mark value.']
        
        if isinstance(max_mark, str):
            try:
                max_mark = Decimal(max_mark)
            except:
                errors['max_mark'] = ['Invalid maximum mark value.']
        
        if isinstance(points, str):
            try:
                points = Decimal(points) if points else Decimal('0')
            except:
                errors['points'] = ['Invalid points value.']
        
        # Validate min_mark < max_mark
        if min_mark >= max_mark:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Minimum mark ({min_mark}) must be less than maximum mark ({max_mark}).'
            ]
        
        # Validate marks are within 0-100
        if min_mark < 0 or min_mark > 100:
            errors['min_mark'] = ['Minimum mark must be between 0 and 100.']
        
        if max_mark < 0 or max_mark > 100:
            errors['max_mark'] = ['Maximum mark must be between 0 and 100.']
        
        # Validate points (0-12 range typical for grading scales)
        if points < 0 or points > 12:
            errors['points'] = ['Points must be between 0 and 12.']
        
        # Check for overlapping ranges for the same education level
        overlapping = GradingScale.objects.filter(
            education_level=education_level,
            min_mark__lt=max_mark,
            max_mark__gt=min_mark,
        ).exclude(pk=scale_id)
        
        if overlapping.exists():
            overlapping_scale = overlapping.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Mark range {min_mark}–{max_mark} overlaps with existing grade '
                f'"{overlapping_scale.grade}" ({overlapping_scale.min_mark}–{overlapping_scale.max_mark}).'
            ]
        
        # Check if grade already exists for this educational level
        if GradingScale.objects.filter(
            education_level=education_level,
            grade=grade
        ).exclude(pk=scale_id).exists():
            errors['grade'] = [f'Grade "{grade}" already exists for {education_level.name}.']
        
        return len(errors) == 0, errors

    def get(self, request):
        """Display the create grading scale form."""
        educational_levels = EducationalLevel.objects.all().order_by('code')
        context = {
            'educational_levels': educational_levels,
            'grade_choices': GradingScale.GRADE_CHOICES,
            'title': 'Create Grading Scale',
            'is_edit': False,
            'scale': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create grading scale form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        education_level_id = request.POST.get('education_level')
        grade = request.POST.get('grade')
        min_mark = request.POST.get('min_mark')
        max_mark = request.POST.get('max_mark')
        points = request.POST.get('points', '0')
        description = request.POST.get('description', '')
        
        # Validate required fields
        if not all([education_level_id, grade, min_mark, max_mark]):
            errors = {}
            if not education_level_id:
                errors['education_level'] = ['Educational level is required.']
            if not grade:
                errors['grade'] = ['Grade is required.']
            if not min_mark:
                errors['min_mark'] = ['Minimum mark is required.']
            if not max_mark:
                errors['max_mark'] = ['Maximum mark is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': 'Create Grading Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            education_level = get_object_or_404(EducationalLevel, pk=education_level_id)
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Educational level not found.',
                    'errors': {'education_level': ['The selected educational level does not exist.']}
                }, status=404)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': 'Create Grading Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': {'education_level': ['The selected educational level does not exist.']}
            })
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_scale_data(
            education_level, grade, min_mark, max_mark, points
        )
        
        if not is_valid:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in validation_errors:
                    message = validation_errors['__all__'][0]
                elif 'grade' in validation_errors:
                    message = validation_errors['grade'][0]
                elif 'min_mark' in validation_errors:
                    message = validation_errors['min_mark'][0]
                elif 'max_mark' in validation_errors:
                    message = validation_errors['max_mark'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': 'Create Grading Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                scale = GradingScale(
                    education_level=education_level,
                    grade=grade,
                    min_mark=Decimal(min_mark),
                    max_mark=Decimal(max_mark),
                    points=Decimal(points) if points else Decimal('0'),
                    description=description
                )
                scale.full_clean()
                scale.save()
                
                message = f'Grading scale for {education_level.name} - Grade {grade} created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:grading_scale_detail', args=[scale.pk]),
                        'scale': {
                            'id': scale.pk,
                            'grade': scale.grade,
                            'grade_display': scale.get_grade_display(),
                            'min_mark': float(scale.min_mark),
                            'max_mark': float(scale.max_mark),
                            'points': float(scale.points),
                            'education_level': education_level.name,
                            'education_level_id': education_level.pk,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:grading_scale_detail', pk=scale.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': 'Create Grading Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error creating grading scale: {e}", exc_info=True)
            error_msg = f'Error creating grading scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': 'Create Grading Scale',
                'is_edit': False,
                'scale': None,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class GradingScaleDetailView(ManagementRequiredMixin, View):
    """View to display grading scale details."""
    template_name = 'portal_management/academic/grading_scales/detail.html'

    def get(self, request, pk):
        """Display grading scale details."""
        scale = get_object_or_404(GradingScale, pk=pk)
        
        # Get all scales for the same educational level
        sibling_scales = GradingScale.objects.filter(
            education_level=scale.education_level
        ).exclude(pk=pk).order_by('-min_mark')
        
        context = {
            'scale': scale,
            'sibling_scales': sibling_scales,
            'education_level': scale.education_level,
        }
        return render(request, self.template_name, context)


class GradingScaleUpdateView(ManagementRequiredMixin, View):
    """View to update an existing grading scale."""
    template_name = 'portal_management/academic/grading_scales/form.html'

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

    def _validate_scale_data(self, education_level, grade, min_mark, max_mark, points, scale_id=None):
        """
        Comprehensive validation for grading scale.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert values if needed
        if isinstance(min_mark, str):
            try:
                min_mark = Decimal(min_mark)
            except:
                errors['min_mark'] = ['Invalid minimum mark value.']
        
        if isinstance(max_mark, str):
            try:
                max_mark = Decimal(max_mark)
            except:
                errors['max_mark'] = ['Invalid maximum mark value.']
        
        if isinstance(points, str):
            try:
                points = Decimal(points) if points else Decimal('0')
            except:
                errors['points'] = ['Invalid points value.']
        
        # Validate min_mark < max_mark
        if min_mark >= max_mark:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Minimum mark ({min_mark}) must be less than maximum mark ({max_mark}).'
            ]
        
        # Validate marks are within 0-100
        if min_mark < 0 or min_mark > 100:
            errors['min_mark'] = ['Minimum mark must be between 0 and 100.']
        
        if max_mark < 0 or max_mark > 100:
            errors['max_mark'] = ['Maximum mark must be between 0 and 100.']
        
        # Validate points (0-12 range typical for grading scales)
        if points < 0 or points > 12:
            errors['points'] = ['Points must be between 0 and 12.']
        
        # Check for overlapping ranges for the same education level (excluding current)
        overlapping = GradingScale.objects.filter(
            education_level=education_level,
            min_mark__lt=max_mark,
            max_mark__gt=min_mark,
        ).exclude(pk=scale_id)
        
        if overlapping.exists():
            overlapping_scale = overlapping.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Mark range {min_mark}–{max_mark} overlaps with existing grade '
                f'"{overlapping_scale.grade}" ({overlapping_scale.min_mark}–{overlapping_scale.max_mark}).'
            ]
        
        # Check if grade already exists for this educational level (excluding current)
        if GradingScale.objects.filter(
            education_level=education_level,
            grade=grade
        ).exclude(pk=scale_id).exists():
            errors['grade'] = [f'Grade "{grade}" already exists for {education_level.name}.']
        
        return len(errors) == 0, errors

    def get(self, request, pk):
        """Display the edit grading scale form."""
        scale = get_object_or_404(GradingScale, pk=pk)
        educational_levels = EducationalLevel.objects.all().order_by('code')
        
        context = {
            'scale': scale,
            'educational_levels': educational_levels,
            'grade_choices': GradingScale.GRADE_CHOICES,
            'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit grading scale form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        scale = get_object_or_404(GradingScale, pk=pk)
        
        education_level_id = request.POST.get('education_level')
        grade = request.POST.get('grade')
        min_mark = request.POST.get('min_mark')
        max_mark = request.POST.get('max_mark')
        points = request.POST.get('points', '0')
        description = request.POST.get('description', '')
        
        # Validate required fields
        if not all([education_level_id, grade, min_mark, max_mark]):
            errors = {}
            if not education_level_id:
                errors['education_level'] = ['Educational level is required.']
            if not grade:
                errors['grade'] = ['Grade is required.']
            if not min_mark:
                errors['min_mark'] = ['Minimum mark is required.']
            if not max_mark:
                errors['max_mark'] = ['Maximum mark is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            education_level = get_object_or_404(EducationalLevel, pk=education_level_id)
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Educational level not found.',
                    'errors': {'education_level': ['The selected educational level does not exist.']}
                }, status=404)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': {'education_level': ['The selected educational level does not exist.']}
            })
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_scale_data(
            education_level, grade, min_mark, max_mark, points, scale.pk
        )
        
        if not is_valid:
            if is_ajax:
                # Get the first error message for the main message
                if '__all__' in validation_errors:
                    message = validation_errors['__all__'][0]
                elif 'grade' in validation_errors:
                    message = validation_errors['grade'][0]
                elif 'min_mark' in validation_errors:
                    message = validation_errors['min_mark'][0]
                elif 'max_mark' in validation_errors:
                    message = validation_errors['max_mark'][0]
                else:
                    message = 'Please correct the errors below.'
                
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                scale.education_level = education_level
                scale.grade = grade
                scale.min_mark = Decimal(min_mark)
                scale.max_mark = Decimal(max_mark)
                scale.points = Decimal(points) if points else Decimal('0')
                scale.description = description
                
                scale.full_clean()
                scale.save()
                
                message = f'Grading scale for {education_level.name} - Grade {grade} updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:grading_scale_detail', args=[scale.pk]),
                        'scale': {
                            'id': scale.pk,
                            'grade': scale.grade,
                            'grade_display': scale.get_grade_display(),
                            'min_mark': float(scale.min_mark),
                            'max_mark': float(scale.max_mark),
                            'points': float(scale.points),
                            'education_level': education_level.name,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:grading_scale_detail', pk=scale.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error updating grading scale {pk}: {e}", exc_info=True)
            error_msg = f'Error updating grading scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            educational_levels = EducationalLevel.objects.all().order_by('code')
            return render(request, self.template_name, {
                'scale': scale,
                'educational_levels': educational_levels,
                'grade_choices': GradingScale.GRADE_CHOICES,
                'title': f'Edit Grading Scale: {scale.education_level.name} - Grade {scale.grade}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class GradingScaleDeleteView(ManagementRequiredMixin, View):
    """View to delete a grading scale."""
    
    def check_dependencies(self, scale):
        """Check if grading scale has dependencies that prevent deletion."""
        dependencies = []
        
        # Check for student results that use this grading scale
        # This would depend on your StudentSubjectResult model
        # if hasattr(scale, 'student_results'):
        #     result_count = scale.student_results.count()
        #     if result_count > 0:
        #         dependencies.append(f'{result_count} student result(s)')
        
        return dependencies

    def post(self, request, pk):
        """Handle grading scale deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        scale = get_object_or_404(GradingScale, pk=pk)
        scale_name = f"{scale.education_level.name} - Grade {scale.grade}"
        
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
            return redirect('management:grading_scale_detail', pk=pk)
        
        try:
            with transaction.atomic():
                education_level_name = scale.education_level.name
                grade = scale.grade
                scale.delete()
            
            message = f'Grading scale "{grade}" for {education_level_name} deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:grading_scale_list')
            
        except Exception as e:
            logger.error(f"Error deleting grading scale {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting grading scale: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:grading_scale_detail', pk=pk)


class GradingScaleCheckDependenciesView(ManagementRequiredMixin, View):
    """AJAX view to check if a grading scale has dependencies."""
    
    def get(self, request, pk):
        """Return dependency information for a grading scale."""
        scale = get_object_or_404(GradingScale, pk=pk)
        
        dependencies = []
        
        # Check for student results
        # if hasattr(scale, 'student_results'):
        #     result_count = scale.student_results.count()
        #     if result_count > 0:
        #         dependencies.append(f'{result_count} student result(s)')
        
        return JsonResponse({
            'has_dependencies': len(dependencies) > 0,
            'dependencies': dependencies,
            'scale_id': scale.pk,
            'scale_name': f"{scale.education_level.name} - Grade {scale.grade}",
        })


class GradingScaleSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching grading scales (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered grading scales for autocomplete."""
        term = request.GET.get('term', '').strip()
        education_level_id = request.GET.get('education_level')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = GradingScale.objects.all().select_related('education_level')
        
        if education_level_id:
            queryset = queryset.filter(education_level_id=education_level_id)
        
        if term:
            queryset = queryset.filter(
                Q(grade__icontains=term) |
                Q(education_level__name__icontains=term) |
                Q(description__icontains=term)
            )
        
        queryset = queryset.order_by('education_level', '-min_mark')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        scales = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': scale.pk,
                'text': f"{scale.education_level.name} - {scale.grade} ({scale.min_mark}-{scale.max_mark})",
                'grade': scale.grade,
                'min_mark': float(scale.min_mark),
                'max_mark': float(scale.max_mark),
                'points': float(scale.points),
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