# portal_management/views/term_views.py

import logging
from datetime import datetime
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
from core.models import Term, AcademicYear

logger = logging.getLogger(__name__)


class TermListView(ManagementRequiredMixin, View):
    """View to list all terms with filtering and search."""
    template_name = 'portal_management/academic/terms/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = Term.objects.all().select_related('academic_year')
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(term_number__icontains=search) |
                Q(academic_year__name__icontains=search)
            )
        
        # Academic year filter
        academic_year_id = request.GET.get('academic_year')
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        # Active filter
        is_active = request.GET.get('is_active')
        if is_active == 'yes':
            queryset = queryset.filter(is_active=True)
        elif is_active == 'no':
            queryset = queryset.filter(is_active=False)
        
        return queryset.order_by('-academic_year__start_date', 'term_number')

    def get(self, request):
        """Handle GET request - display term list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        terms = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get all academic years for filter dropdown
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        context = {
            'terms': terms,
            'academic_years': academic_years,
            'total_terms': total_count,
            'active_terms': queryset.filter(is_active=True).count(),
            'inactive_terms': queryset.filter(is_active=False).count(),
            'terms_in_active_year': queryset.filter(
                academic_year__is_active=True
            ).count(),
            'search_query': request.GET.get('search', ''),
            'selected_academic_year': request.GET.get('academic_year', ''),
            'selected_active_filter': request.GET.get('is_active', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class TermCreateView(ManagementRequiredMixin, View):
    """View to create a new term."""
    template_name = 'portal_management/academic/terms/form.html'

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

    def _convert_to_date(self, date_value):
        """Convert string date to date object."""
        if isinstance(date_value, str):
            return datetime.strptime(date_value, '%Y-%m-%d').date()
        return date_value

    def _validate_term_dates(self, academic_year, term_number, start_date, end_date, term_id=None):
        """
        Comprehensive validation for term dates.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert dates if needed
        start_date = self._convert_to_date(start_date)
        end_date = self._convert_to_date(end_date)
        
        # Ensure start_date is before end_date
        if start_date >= end_date:
            errors['__all__'] = ['Start date must be before end date.']
        
        # Validate that term dates are within the academic year
        if start_date < academic_year.start_date:
            errors['start_date'] = [
                f'Term start date ({start_date.strftime("%b %d, %Y")}) cannot be before '
                f'academic year start ({academic_year.start_date.strftime("%b %d, %Y")}).'
            ]
        
        if end_date > academic_year.end_date:
            errors['end_date'] = [
                f'Term end date ({end_date.strftime("%b %d, %Y")}) cannot be after '
                f'academic year end ({academic_year.end_date.strftime("%b %d, %Y")}).'
            ]
        
        # Validate term duration (reasonable length for a term)
        term_duration_days = (end_date - start_date).days + 1  # inclusive
        if term_duration_days < 60:  # Less than ~2 months
            errors['__all__'] = errors.get('__all__', []) + [
                f'Term duration ({term_duration_days} days) is too short. '
                f'Terms must be at least 60 days.'
            ]
        if term_duration_days > 150:  # More than ~5 months
            errors['__all__'] = errors.get('__all__', []) + [
                f'Term duration ({term_duration_days} days) is too long. '
                f'Terms cannot exceed 150 days.'
            ]
        
        # Check for overlapping with other terms in the same academic year
        overlapping_terms = Term.objects.filter(
            academic_year=academic_year
        ).exclude(pk=term_id).filter(
            models.Q(start_date__lt=end_date, end_date__gt=start_date)
        )
        
        if overlapping_terms.exists():
            overlapping = overlapping_terms.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Date range overlaps with existing term "{overlapping.name}" '
                f'({overlapping.start_date.strftime("%b %d, %Y")} to '
                f'{overlapping.end_date.strftime("%b %d, %Y")}).'
            ]
        
        # Validate term number is appropriate (1,2,3)
        if term_number not in ['1', '2', '3']:
            errors['term_number'] = ['Term number must be 1, 2, or 3.']
        
        # Check if this term number already exists in this academic year
        if Term.objects.filter(academic_year=academic_year, term_number=term_number).exclude(pk=term_id).exists():
            errors['term_number'] = [f'Term {term_number} already exists in {academic_year.name}.']
        
        return len(errors) == 0, errors

    def get(self, request):
        """Display the create term form."""
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        context = {
            'academic_years': academic_years,
            'title': 'Create Term',
            'is_edit': False,
            'term': None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create term form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        academic_year_id = request.POST.get('academic_year')
        term_number = request.POST.get('term_number')
        name = request.POST.get('name', '').strip()
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([academic_year_id, term_number, start_date, end_date]):
            errors = {}
            if not academic_year_id:
                errors['academic_year'] = ['Academic year is required.']
            if not term_number:
                errors['term_number'] = ['Term number is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'academic_years': academic_years,
                'title': 'Create Term',
                'is_edit': False,
                'term': None,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Academic year not found.',
                    'errors': {'academic_year': ['The selected academic year does not exist.']}
                }, status=404)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'academic_years': academic_years,
                'title': 'Create Term',
                'is_edit': False,
                'term': None,
                'form_data': request.POST,
                'errors': {'academic_year': ['The selected academic year does not exist.']}
            })
        
        # Perform comprehensive validation
        is_valid, validation_errors = self._validate_term_dates(
            academic_year, term_number, start_date, end_date
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'term_number' in validation_errors:
                message = validation_errors['term_number'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'academic_years': academic_years,
                'title': 'Create Term',
                'is_edit': False,
                'term': None,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                term = Term(
                    academic_year=academic_year,
                    term_number=term_number,
                    name=name if name else f"Term {term_number}",
                    start_date=start_date,
                    end_date=end_date,
                    is_active=is_active
                )
                term.full_clean()
                term.save()
                
                message = f'Term "{term.name}" created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:term_detail', args=[term.pk]),
                        'term': {
                            'id': term.pk,
                            'term_number': term.term_number,
                            'name': term.name,
                            'start_date': term.start_date.strftime('%Y-%m-%d'),
                            'end_date': term.end_date.strftime('%Y-%m-%d'),
                            'is_active': term.is_active,
                            'academic_year': academic_year.name,
                            'academic_year_id': academic_year.pk,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:term_detail', pk=term.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'academic_years': academic_years,
                'title': 'Create Term',
                'is_edit': False,
                'term': None,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error creating term: {e}", exc_info=True)
            error_msg = f'Error creating term: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'academic_years': academic_years,
                'title': 'Create Term',
                'is_edit': False,
                'term': None,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class TermDetailView(ManagementRequiredMixin, View):
    """View to display term details."""
    template_name = 'portal_management/academic/terms/detail.html'

    def get(self, request, pk):
        """Display term details."""
        term = get_object_or_404(Term, pk=pk)
        
        # Calculate duration in days
        duration_days = (term.end_date - term.start_date).days + 1
        
        # Get all terms in the same academic year
        sibling_terms = Term.objects.filter(
            academic_year=term.academic_year
        ).exclude(pk=pk).order_by('term_number')
        
        # Get exam sessions (if any)
        exam_sessions = None
        if hasattr(term, 'exam_sessions'):
            exam_sessions = term.exam_sessions.all().order_by('exam_date')[:10]
        
        context = {
            'term': term,
            'duration_days': duration_days,
            'sibling_terms': sibling_terms,
            'academic_year': term.academic_year,
            'exam_sessions': exam_sessions,
            'exam_count': exam_sessions.count() if exam_sessions else 0,
        }
        return render(request, self.template_name, context)


class TermUpdateView(ManagementRequiredMixin, View):
    """View to update an existing term."""
    template_name = 'portal_management/academic/terms/form.html'

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

    def _convert_to_date(self, date_value):
        """Convert string date to date object."""
        if isinstance(date_value, str):
            return datetime.strptime(date_value, '%Y-%m-%d').date()
        return date_value

    def _validate_term_dates(self, academic_year, term_number, start_date, end_date, term_id=None):
        """
        Comprehensive validation for term dates.
        Returns (is_valid, errors_dict)
        """
        errors = {}
        
        # Convert dates if needed
        start_date = self._convert_to_date(start_date)
        end_date = self._convert_to_date(end_date)
        
        # Ensure start_date is before end_date
        if start_date >= end_date:
            errors['__all__'] = ['Start date must be before end date.']
        
        # Validate that term dates are within the academic year
        if start_date < academic_year.start_date:
            errors['start_date'] = [
                f'Term start date ({start_date.strftime("%b %d, %Y")}) cannot be before '
                f'academic year start ({academic_year.start_date.strftime("%b %d, %Y")}).'
            ]
        
        if end_date > academic_year.end_date:
            errors['end_date'] = [
                f'Term end date ({end_date.strftime("%b %d, %Y")}) cannot be after '
                f'academic year end ({academic_year.end_date.strftime("%b %d, %Y")}).'
            ]
        
        # Validate term duration (reasonable length for a term)
        term_duration_days = (end_date - start_date).days + 1  # inclusive
        if term_duration_days < 60:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Term duration ({term_duration_days} days) is too short. '
                f'Terms must be at least 60 days.'
            ]
        if term_duration_days > 150:
            errors['__all__'] = errors.get('__all__', []) + [
                f'Term duration ({term_duration_days} days) is too long. '
                f'Terms cannot exceed 150 days.'
            ]
        
        # Check for overlapping with other terms in the same academic year
        overlapping_terms = Term.objects.filter(
            academic_year=academic_year
        ).exclude(pk=term_id).filter(
            models.Q(start_date__lt=end_date, end_date__gt=start_date)
        )
        
        if overlapping_terms.exists():
            overlapping = overlapping_terms.first()
            errors['__all__'] = errors.get('__all__', []) + [
                f'Date range overlaps with existing term "{overlapping.name}" '
                f'({overlapping.start_date.strftime("%b %d, %Y")} to '
                f'{overlapping.end_date.strftime("%b %d, %Y")}).'
            ]
        
        # Validate term number is appropriate (1,2,3)
        if term_number not in ['1', '2', '3']:
            errors['term_number'] = ['Term number must be 1, 2, or 3.']
        
        # Check if this term number already exists in this academic year
        if Term.objects.filter(academic_year=academic_year, term_number=term_number).exclude(pk=term_id).exists():
            errors['term_number'] = [f'Term {term_number} already exists in {academic_year.name}.']
        
        return len(errors) == 0, errors

    def get(self, request, pk):
        """Display the edit term form."""
        term = get_object_or_404(Term, pk=pk)
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        
        context = {
            'term': term,
            'academic_years': academic_years,
            'title': f'Edit Term: {term.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit term form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        term = get_object_or_404(Term, pk=pk)
        
        academic_year_id = request.POST.get('academic_year')
        term_number = request.POST.get('term_number')
        name = request.POST.get('name', '').strip()
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'true'
        
        # Validate required fields
        if not all([academic_year_id, term_number, start_date, end_date]):
            errors = {}
            if not academic_year_id:
                errors['academic_year'] = ['Academic year is required.']
            if not term_number:
                errors['term_number'] = ['Term number is required.']
            if not start_date:
                errors['start_date'] = ['Start date is required.']
            if not end_date:
                errors['end_date'] = ['End date is required.']
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please fill in all required fields.',
                    'errors': errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'term': term,
                'academic_years': academic_years,
                'title': f'Edit Term: {term.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': errors
            })
        
        try:
            academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
        except Exception:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Academic year not found.',
                    'errors': {'academic_year': ['The selected academic year does not exist.']}
                }, status=404)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'term': term,
                'academic_years': academic_years,
                'title': f'Edit Term: {term.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': {'academic_year': ['The selected academic year does not exist.']}
            })
        
        # Perform comprehensive validation (pass term_id to exclude current term)
        is_valid, validation_errors = self._validate_term_dates(
            academic_year, term_number, start_date, end_date, term.pk
        )
        
        if not is_valid:
            # Get the first error message for the main message
            if '__all__' in validation_errors:
                message = validation_errors['__all__'][0]
            elif 'term_number' in validation_errors:
                message = validation_errors['term_number'][0]
            elif 'start_date' in validation_errors:
                message = validation_errors['start_date'][0]
            elif 'end_date' in validation_errors:
                message = validation_errors['end_date'][0]
            else:
                message = 'Please correct the errors below.'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': validation_errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'term': term,
                'academic_years': academic_years,
                'title': f'Edit Term: {term.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': validation_errors
            })
        
        try:
            with transaction.atomic():
                term.academic_year = academic_year
                term.term_number = term_number
                term.name = name if name else f"Term {term_number}"
                term.start_date = start_date
                term.end_date = end_date
                term.is_active = is_active
                
                term.full_clean()
                term.save()
                
                message = f'Term "{term.name}" updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:term_detail', args=[term.pk]),
                        'term': {
                            'id': term.pk,
                            'term_number': term.term_number,
                            'name': term.name,
                            'start_date': term.start_date.strftime('%Y-%m-%d'),
                            'end_date': term.end_date.strftime('%Y-%m-%d'),
                            'is_active': term.is_active,
                            'academic_year': academic_year.name,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:term_detail', pk=term.pk)
                
        except ValidationError as e:
            formatted_errors = self._format_errors(e)
            message = formatted_errors.get('__all__', ['Please correct the errors below.'])[0]
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': formatted_errors
                }, status=400)
            
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'term': term,
                'academic_years': academic_years,
                'title': f'Edit Term: {term.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': formatted_errors
            })
            
        except Exception as e:
            logger.error(f"Error updating term {pk}: {e}", exc_info=True)
            error_msg = f'Error updating term: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            academic_years = AcademicYear.objects.all().order_by('-start_date')
            return render(request, self.template_name, {
                'term': term,
                'academic_years': academic_years,
                'title': f'Edit Term: {term.name}',
                'is_edit': True,
                'form_data': request.POST,
                'errors': [error_msg]
            })


class TermDeleteView(ManagementRequiredMixin, View):
    """View to delete a term."""
    
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

    def check_dependencies(self, term):
        """Check if term has dependencies that prevent deletion."""
        dependencies = []
        
        # Check for exam sessions
        if hasattr(term, 'exam_sessions'):
            exam_count = term.exam_sessions.count()
            if exam_count > 0:
                dependencies.append(f'{exam_count} exam session(s)')
        
        return dependencies

    def post(self, request, pk):
        """Handle term deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        term = get_object_or_404(Term, pk=pk)
        term_name = term.name
        
        # Check for dependencies
        dependencies = self.check_dependencies(term)
        
        if dependencies:
            error_msg = (
                f'Cannot delete "{term_name}" because it has associated {", ".join(dependencies)}. '
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
            return redirect('management:term_detail', pk=pk)
        
        try:
            with transaction.atomic():
                academic_year_name = term.academic_year.name
                term.delete()
            
            message = f'Term "{term_name}" ({academic_year_name}) deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:term_list')
            
        except Exception as e:
            logger.error(f"Error deleting term {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting term: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:term_detail', pk=pk)


class TermCheckDependenciesView(ManagementRequiredMixin, View):
    """AJAX view to check if a term has dependencies."""
    
    def get(self, request, pk):
        """Return dependency information for a term."""
        term = get_object_or_404(Term, pk=pk)
        
        dependencies = []
        
        # Check for exam sessions
        if hasattr(term, 'exam_sessions'):
            exam_count = term.exam_sessions.count()
            if exam_count > 0:
                dependencies.append(f'{exam_count} exam session(s)')
        
        return JsonResponse({
            'has_dependencies': len(dependencies) > 0,
            'dependencies': dependencies,
            'term_id': term.pk,
            'term_name': term.name,
        })


class TermSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching terms (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered terms for autocomplete."""
        term = request.GET.get('term', '').strip()
        academic_year_id = request.GET.get('academic_year')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = Term.objects.all().select_related('academic_year')
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) |
                Q(term_number__icontains=term)
            )
        
        queryset = queryset.order_by('-academic_year__start_date', 'term_number')
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        terms = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': term.pk,
                'text': f"{term.name} ({term.academic_year.name})",
                'name': term.name,
                'term_number': term.term_number,
                'academic_year': term.academic_year.name,
            }
            for term in terms
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })
    

class TermDeactivateView(ManagementRequiredMixin, View):
    """View to deactivate a term."""
    
    def post(self, request, pk):
        """Deactivate a term."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        term = get_object_or_404(Term, pk=pk)
        
        try:
            with transaction.atomic():
                term.is_active = False
                term.save()
                
                message = f'Term "{term.name}" has been deactivated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message
                    })
                
                messages.success(request, message)
                return redirect('management:term_detail', pk=term.pk)
                
        except Exception as e:
            logger.error(f"Error deactivating term {pk}: {e}", exc_info=True)
            error_msg = f'Error deactivating term: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:term_detail', pk=term.pk)