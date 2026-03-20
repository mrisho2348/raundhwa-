# portal_management/views/departments.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import View

from core.mixins import ManagementRequiredMixin
from core.models import Department
from portal_management.forms.departments import DepartmentForm

logger = logging.getLogger(__name__)


class DepartmentListView(ManagementRequiredMixin, View):
    """View to list all departments with filtering and search."""
    template_name = 'portal_management/academic/departments/list.html'
    paginate_by = 20

    def get_queryset(self, request):
        """Get filtered queryset based on request parameters."""
        queryset = Department.objects.all()
        
        # Search filter
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset.order_by('name')

    def get_statistics(self, queryset):
        """Calculate statistics for the dashboard."""
        total = queryset.count()
        
        return {
            'total_departments': total,
        }

    def get(self, request):
        """Handle GET request - display department list."""
        queryset = self.get_queryset(request)
        
        # Simple pagination
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        departments = queryset[start:end]
        
        # Calculate total pages
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        context = {
            'departments': departments,
            'total_departments': total_count,
            'search_query': request.GET.get('search', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
        }
        
        return render(request, self.template_name, context)


class DepartmentCreateView(ManagementRequiredMixin, View):
    """View to create a new department."""
    template_name = 'portal_management/academic/departments/form.html'

    def get(self, request):
        """Display the create department form."""
        form = DepartmentForm()
        context = {
            'form': form,
            'title': 'Create Department',
            'is_edit': False,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        """Process the create department form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        form = DepartmentForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    department = form.save()
                
                message = f'Department "{department.name}" created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:department_detail', args=[department.pk]),
                        'department': {
                            'id': department.pk,
                            'name': department.name,
                            'code': department.code,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:department_detail', pk=department.pk)
                
            except Exception as e:
                logger.error(f"Error creating department: {e}", exc_info=True)
                error_msg = f'Error creating department: {str(e)}'
                
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': {'__all__': [str(e)]}
                    }, status=400)
                
                messages.error(request, error_msg)
                return render(request, self.template_name, {
                    'form': form,
                    'title': 'Create Department',
                    'is_edit': False,
                })
        else:
            # Form is invalid
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            return render(request, self.template_name, {
                'form': form,
                'title': 'Create Department',
                'is_edit': False,
            })


class DepartmentDetailView(ManagementRequiredMixin, View):
    """View to display department details."""
    template_name = 'portal_management/academic/departments/detail.html'

    def get(self, request, pk):
        """Display department details."""
        department = get_object_or_404(Department, pk=pk)
        
        context = {
            'department': department,
        }
        return render(request, self.template_name, context)


class DepartmentUpdateView(ManagementRequiredMixin, View):
    """View to update an existing department."""
    template_name = 'portal_management/academic/departments/form.html'

    def get(self, request, pk):
        """Display the edit department form."""
        department = get_object_or_404(Department, pk=pk)
        form = DepartmentForm(instance=department)
        
        context = {
            'form': form,
            'department': department,
            'title': f'Edit Department: {department.name}',
            'is_edit': True,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """Process the edit department form submission."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        department = get_object_or_404(Department, pk=pk)
        form = DepartmentForm(request.POST, instance=department)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_department = form.save()
                
                message = f'Department "{updated_department.name}" updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:department_detail', args=[updated_department.pk]),
                        'department': {
                            'id': updated_department.pk,
                            'name': updated_department.name,
                            'code': updated_department.code,
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:department_detail', pk=updated_department.pk)
                
            except Exception as e:
                logger.error(f"Error updating department {pk}: {e}", exc_info=True)
                error_msg = f'Error updating department: {str(e)}'
                
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': {'__all__': [str(e)]}
                    }, status=400)
                
                messages.error(request, error_msg)
                return render(request, self.template_name, {
                    'form': form,
                    'department': department,
                    'title': f'Edit Department: {department.name}',
                    'is_edit': True,
                })
        else:
            # Form is invalid
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                }, status=400)
            
            return render(request, self.template_name, {
                'form': form,
                'department': department,
                'title': f'Edit Department: {department.name}',
                'is_edit': True,
            })


class DepartmentDeleteView(ManagementRequiredMixin, View):
    """View to delete a department."""
    
    def post(self, request, pk):
        """Handle department deletion."""
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        department = get_object_or_404(Department, pk=pk)
        department_name = department.name
        
        try:
            # Check for associated staff assignments
            staff_count = department.staff_assignments.filter(is_active=True).count()
            
            if staff_count > 0:
                error_msg = (
                    f'Cannot delete "{department_name}" because it has '
                    f'{staff_count} active staff assignment(s). '
                    f'Please reassign these staff members first.'
                )
                
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'has_staff': True,
                        'staff_count': staff_count
                    }, status=400)
                
                messages.error(request, error_msg)
                return redirect('management:department_detail', pk=pk)
            
            with transaction.atomic():
                department.delete()
            
            message = f'Department "{department_name}" deleted successfully!'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            return redirect('management:department_list')
            
        except Exception as e:
            logger.error(f"Error deleting department {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting department: {str(e)}'
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                }, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:department_detail', pk=pk)


class DepartmentSearchView(ManagementRequiredMixin, View):
    """AJAX view for searching departments (for select2/autocomplete)."""
    
    def get(self, request):
        """Return filtered departments for autocomplete."""
        term = request.GET.get('term', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = Department.objects.all().order_by('name')
        
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) |
                Q(code__icontains=term)
            )
        
        # Simple pagination for select2
        start = (page - 1) * page_size
        end = start + page_size
        departments = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': dept.pk,
                'text': f"{dept.name} ({dept.code})",
                'name': dept.name,
                'code': dept.code,
            }
            for dept in departments
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {
                'more': end < total_count,
                'total': total_count,
            }
        })