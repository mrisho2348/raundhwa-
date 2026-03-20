# portal_management/views/parent.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import Parent, StudentParent, Student
from portal_management.forms.parent_form import ParentForm, StudentParentForm

logger = logging.getLogger(__name__)


class ParentListView(ManagementRequiredMixin, TemplateView):
    """List all parents/guardians with filtering."""
    template_name = 'portal_management/parents/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        search_query = self.request.GET.get('search', '')
        relationship_filter = self.request.GET.get('relationship', '')
        
        # Base queryset
        parents = Parent.objects.annotate(
            student_count=models.Count('studentparent')
        ).order_by('full_name')
        
        # Apply filters
        if search_query:
            parents = parents.filter(
                Q(full_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(phone_number__icontains=search_query)
            )
        
        if relationship_filter:
            parents = parents.filter(relationship=relationship_filter)
        
        ctx['parents'] = parents
        ctx['total_parents'] = parents.count()
        
        # Get relationship choices for filter
        ctx['relationship_choices'] = Parent.RELATIONSHIP_CHOICES
        ctx['selected_relationship'] = relationship_filter
        ctx['search_query'] = search_query
        
        return ctx


class ParentCreateView(ManagementRequiredMixin, View):
    """Create a new parent/guardian."""
    template_name = 'portal_management/parents/form.html'
    
    def get(self, request):
        form = ParentForm()
        
        return render(request, self.template_name, {
            'form': form,
            'title': 'Add New Parent/Guardian',
            'is_update': False
        })
    
    def post(self, request):
        form = ParentForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    parent = form.save()
                    
                    message = f'Parent {parent.full_name} added successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:parent_detail', kwargs={'pk': parent.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:parent_detail', pk=parent.pk)
                    
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
                logger.error(f"Parent creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating parent: {e}')
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
            'title': 'Add New Parent/Guardian',
            'is_update': False
        })


class ParentDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a parent/guardian."""
    template_name = 'portal_management/parents/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        parent = get_object_or_404(
            Parent.objects.prefetch_related('studentparent_set__student'),
            pk=self.kwargs['pk']
        )
        
        ctx['parent'] = parent
        
        # Get students linked to this parent
        student_parents = parent.studentparent_set.select_related('student').all()
        ctx['student_parents'] = student_parents
        ctx['student_count'] = student_parents.count()
        
        # Get total number of students (for statistics)
        ctx['total_students'] = student_parents.count()
        
        # Get primary contacts count
        ctx['primary_contacts'] = student_parents.filter(is_primary_contact=True).count()
        
        # Get fee responsible count
        ctx['fee_responsible'] = student_parents.filter(is_fee_responsible=True).count()
        
        return ctx


class ParentUpdateView(ManagementRequiredMixin, View):
    """Update an existing parent/guardian."""
    template_name = 'portal_management/parents/form.html'
    
    def get(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        form = ParentForm(instance=parent)
        
        return render(request, self.template_name, {
            'form': form,
            'parent': parent,
            'title': f'Edit Parent - {parent.full_name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        form = ParentForm(request.POST, instance=parent)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    parent = form.save()
                    
                    message = f'Parent {parent.full_name} updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:parent_detail', kwargs={'pk': parent.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:parent_detail', pk=parent.pk)
                    
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
                logger.error(f"Parent update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating parent: {e}')
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
            'parent': parent,
            'title': f'Edit Parent - {parent.full_name}',
            'is_update': True
        })


class ParentDeleteView(ManagementRequiredMixin, View):
    """Delete a parent/guardian."""
    
    def post(self, request, pk):
        parent = get_object_or_404(Parent, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            parent_name = parent.full_name
            
            # Check if parent has linked students
            student_count = parent.studentparent_set.count()
            
            if student_count > 0:
                error_msg = f'Cannot delete parent "{parent_name}" because they are linked to {student_count} student(s).'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('management:parent_detail', pk=parent.pk)
            
            with transaction.atomic():
                parent.delete()
            
            message = f'Parent "{parent_name}" deleted successfully.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:parent_list')
                })
            
            messages.success(request, message)
            return redirect('management:parent_list')
            
        except Exception as e:
            logger.error(f"Parent deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting parent: {e}')
            return redirect('management:parent_detail', pk=pk)


class StudentParentLinkView(ManagementRequiredMixin, View):
    """Link a parent to a student."""
    template_name = 'portal_management/parents/link_student.html'
    
    def get(self, request, parent_pk=None, student_pk=None):
        initial = {}
        
        if parent_pk:
            parent = get_object_or_404(Parent, pk=parent_pk)
            initial['parent'] = parent
        elif student_pk:
            student = get_object_or_404(Student, pk=student_pk)
            initial['student'] = student
        
        form = StudentParentForm(initial=initial)
        
        # Get existing relationships for display
        existing_relationships = []
        if parent_pk:
            existing_relationships = StudentParent.objects.filter(parent_id=parent_pk).select_related('student')
        
        return render(request, self.template_name, {
            'form': form,
            'parent': parent if parent_pk else None,
            'student': student if student_pk else None,
            'existing_relationships': existing_relationships,
            'title': 'Link Parent to Student',
        })
    
    def post(self, request, parent_pk=None, student_pk=None):
        form = StudentParentForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    student_parent = form.save()
                    
                    message = f'{student_parent.parent.full_name} linked to {student_parent.student.full_name} successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:parent_detail', kwargs={'pk': student_parent.parent.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:parent_detail', pk=student_parent.parent.pk)
                    
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
                logger.error(f"Parent linking error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error linking parent: {e}')
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
        
        # Get data for re-render
        parent = None
        student = None
        existing_relationships = []
        
        if parent_pk:
            parent = get_object_or_404(Parent, pk=parent_pk)
            existing_relationships = StudentParent.objects.filter(parent_id=parent_pk).select_related('student')
        elif student_pk:
            student = get_object_or_404(Student, pk=student_pk)
        
        return render(request, self.template_name, {
            'form': form,
            'parent': parent,
            'student': student,
            'existing_relationships': existing_relationships,
            'title': 'Link Parent to Student',
        })


class StudentParentUnlinkView(ManagementRequiredMixin, View):
    """Unlink a parent from a student."""
    
    def post(self, request, pk):
        relationship = get_object_or_404(StudentParent, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            parent_name = relationship.parent.full_name
            student_name = relationship.student.full_name
            
            with transaction.atomic():
                relationship.delete()
            
            message = f'{parent_name} has been unlinked from {student_name}.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message
                })
            
            messages.success(request, message)
            
        except Exception as e:
            logger.error(f"Parent unlinking error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=500)
            messages.error(request, f'Error unlinking parent: {e}')
        
        return redirect('management:parent_detail', pk=relationship.parent.pk)


class GetParentDetailsView(ManagementRequiredMixin, View):
    """AJAX endpoint to get parent details for editing in modal."""
    
    def get(self, request, pk):
        try:
            parent = get_object_or_404(Parent, pk=pk)
            
            return JsonResponse({
                'id': parent.pk,
                'full_name': parent.full_name,
                'relationship': parent.relationship,
                'relationship_display': parent.get_relationship_display(),
                'address': parent.address,
                'email': parent.email,
                'phone_number': parent.phone_number,
                'alternate_phone': parent.alternate_phone,
                'student_count': parent.studentparent_set.count(),
            })
            
        except Exception as e:
            logger.error(f"Error in GetParentDetailsView: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)