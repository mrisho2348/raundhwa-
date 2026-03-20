# portal_management/views/schools.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import School, EducationalLevel, StudentEducationHistory, StudentTransferOut
from portal_management.forms.school_form import SchoolForm


logger = logging.getLogger(__name__)


class SchoolListView(ManagementRequiredMixin, TemplateView):
    """List all schools with filtering and statistics."""
    template_name = 'portal_management/academic/schools/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        search_query = self.request.GET.get('search', '')
        level_id = self.request.GET.get('level')
        location_query = self.request.GET.get('location', '')
        
        # Base queryset with annotations
        schools = School.objects.select_related(
            'educational_level'
        ).annotate(
            student_history_count=Count('student_histories', distinct=True),
            transfer_in_count=Count('incoming_transfers', distinct=True)
        ).order_by('name', 'educational_level__level_type')
        
        # Apply filters
        if search_query:
            schools = schools.filter(
                Q(name__icontains=search_query) |
                Q(registration_number__icontains=search_query)
            )
        
        if location_query:
            schools = schools.filter(location__icontains=location_query)
        
        if level_id:
            schools = schools.filter(educational_level_id=level_id)
        
        # Group schools by name for display purposes
        school_groups = {}
        for school in schools:
            if school.name not in school_groups:
                school_groups[school.name] = []
            school_groups[school.name].append(school)
        
        ctx['schools'] = schools
        ctx['school_groups'] = school_groups
        ctx['total_schools'] = schools.count()
        ctx['unique_school_names'] = len(school_groups)
        
        # Statistics
        ctx['total_student_histories'] = StudentEducationHistory.objects.filter(
            school__in=schools
        ).count()
        ctx['total_transfers_in'] = StudentTransferOut.objects.filter(
            destination_school__in=schools
        ).count()
        
        # Get filter options
        ctx['educational_levels'] = EducationalLevel.objects.all().order_by('level_type', 'name')
        
        # Store selected filters
        ctx['search_query'] = search_query
        ctx['location_query'] = location_query
        ctx['selected_level'] = int(level_id) if level_id else None
        
        return ctx


# portal_management/views/schools.py - Update the create and update views

class SchoolCreateView(ManagementRequiredMixin, View):
    """Create a new school."""
    template_name = 'portal_management/academic/schools/form.html'
    
    def get(self, request):
        form = SchoolForm()
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add New School',
            'action': 'Create',
            'is_update': False
        })
    
    def post(self, request):
        form = SchoolForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    school = form.save()
                    
                    message = f'School "{school.name}" created successfully.'
                    
                    # Check if there are warnings
                    if hasattr(form, 'warnings') and form.warnings:
                        if is_ajax:
                            return JsonResponse({
                                'success': True,
                                'message': message,
                                'warnings': form.warnings,
                                'redirect_url': reverse('management:school_list')
                            })
                        for warning in form.warnings:
                            messages.warning(request, warning)
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:school_list')
                        })
                    
                    messages.success(request, message)
                    return redirect('management:school_list')
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"School creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating school: {e}')
        else:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} error{"s" if error_count > 1 else ""} below.'
            )
        
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add New School',
            'action': 'Create',
            'is_update': False
        })


class SchoolUpdateView(ManagementRequiredMixin, View):
    """Update an existing school."""
    template_name = 'portal_management/academic/schools/form.html'
    
    def get(self, request, pk):
        school = get_object_or_404(School, pk=pk)
        form = SchoolForm(instance=school)
        
        return render(request, self.template_name, {
            'form': form,
            'school': school,
            'title': f'Edit School - {school.name}',
            'action': 'Update',
            'is_update': True
        })
    
    def post(self, request, pk):
        school = get_object_or_404(School, pk=pk)
        form = SchoolForm(request.POST, instance=school)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    school = form.save()
                    
                    message = f'School "{school.name}" updated successfully.'
                    
                    # Check if there are warnings
                    if hasattr(form, 'warnings') and form.warnings:
                        if is_ajax:
                            return JsonResponse({
                                'success': True,
                                'message': message,
                                'warnings': form.warnings,
                                'redirect_url': reverse('management:school_list')
                            })
                        for warning in form.warnings:
                            messages.warning(request, warning)
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:school_list')
                        })
                    
                    messages.success(request, message)
                    return redirect('management:school_list')
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"School update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating school: {e}')
        else:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            error_count = len(form.errors)
            messages.error(
                request,
                f'Please correct the {error_count} error{"s" if error_count > 1 else ""} below.'
            )
        
        return render(request, self.template_name, {
            'form': form,
            'school': school,
            'title': f'Edit School - {school.name}',
            'action': 'Update',
            'is_update': True
        })


class SchoolDeleteView(ManagementRequiredMixin, View):
    """Delete a school only if no dependencies exist."""
    
    def post(self, request, pk):
        school = get_object_or_404(School, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Check dependencies
        dependency_errors = []
        
        if school.student_histories.exists():
            count = school.student_histories.count()
            dependency_errors.append(f'{count} student education histor{"y" if count == 1 else "ies"}')
        
        if school.incoming_transfers.exists():
            count = school.incoming_transfers.count()
            dependency_errors.append(f'{count} incoming transfer record{"s" if count != 1 else ""}')
        
        if dependency_errors:
            error_msg = f'Cannot delete school that has: {", ".join(dependency_errors)}.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'errors': {'__all__': [error_msg]}
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:school_list')
        
        try:
            school_name = school.name
            school.delete()
            
            message = f'School "{school_name}" deleted successfully.'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message})
            
            messages.success(request, message)
            return redirect('management:school_list')
            
        except Exception as e:
            logger.error(f"School deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': str(e),
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            messages.error(request, f'Error deleting school: {e}')
            return redirect('management:school_list')


class SchoolDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a school including its usage."""
    template_name = 'portal_management/academic/schools/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        school = get_object_or_404(
            School.objects.select_related('educational_level'),
            pk=self.kwargs['pk']
        )
        
        ctx['school'] = school
        
        # Get student education histories
        ctx['student_histories'] = school.student_histories.select_related(
            'student'
        ).order_by('-completion_year', '-created_at')[:20]
        
        # Get incoming transfers
        ctx['incoming_transfers'] = school.incoming_transfers.select_related(
            'student'
        ).order_by('-transfer_date', '-created_at')[:20]
        
        # Statistics
        ctx['total_histories'] = school.student_histories.count()
        ctx['total_transfers'] = school.incoming_transfers.count()
        
        return ctx


class GetSchoolDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get school details for editing in modal."""
    
    def get(self, request, pk):
        school = get_object_or_404(School, pk=pk)
        
        return JsonResponse({
            'id': school.pk,
            'name': school.name,
            'educational_level_id': school.educational_level_id,
            'educational_level': school.educational_level.name if school.educational_level else None,
            'location': school.location or '',
            'registration_number': school.registration_number or '',
            'student_histories_count': school.student_histories.count(),
            'incoming_transfers_count': school.incoming_transfers.count(),
        })


class SearchSchoolsForSelectView(ManagementRequiredMixin, View):
    """AJAX endpoint for Select2 to search schools."""
    
    def get(self, request):
        search = request.GET.get('term', '')
        page = int(request.GET.get('page', 1))
        page_size = 20
        
        schools = School.objects.all()
        
        if search:
            schools = schools.filter(
                Q(name__icontains=search) |
                Q(location__icontains=search) |
                Q(registration_number__icontains=search)
            )
        
        total = schools.count()
        schools = schools.order_by('name')[(page - 1) * page_size:page * page_size]
        
        results = [{
            'id': s.pk,
            'text': f"{s.name}" + (f" ({s.location})" if s.location else ""),
            'name': s.name,
            'location': s.location or '',
        } for s in schools]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': total > page * page_size
            }
        })