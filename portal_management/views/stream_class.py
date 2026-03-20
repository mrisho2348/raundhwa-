# portal_management/views/stream_class.py

import logging
from django.db import transaction
from django.contrib import messages
from django.db import models
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import StreamClass, ClassLevel, EducationalLevel
from portal_management.forms.stream_class_form import StreamClassForm

logger = logging.getLogger(__name__)


class StreamClassListView(ManagementRequiredMixin, TemplateView):
    """List all stream classes with filtering."""
    template_name = 'portal_management/academic/streams/list.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # Get filter parameters
        class_level_id = self.request.GET.get('class_level')
        educational_level_id = self.request.GET.get('educational_level')
        search_query = self.request.GET.get('search', '')
        
        # Base queryset with annotations
        streams = StreamClass.objects.select_related(
            'class_level',
            'class_level__educational_level'
        ).annotate(
            current_student_count=Count(
                'stream_assignments',
                filter=Q(
                    stream_assignments__enrollment__status='active',
                    stream_assignments__enrollment__academic_year__is_active=True
                )
            )
        ).order_by('class_level__educational_level', 'class_level', 'stream_letter')
        
        # Apply filters
        if class_level_id:
            streams = streams.filter(class_level_id=class_level_id)
        
        if educational_level_id:
            streams = streams.filter(class_level__educational_level_id=educational_level_id)
        
        if search_query:
            streams = streams.filter(
                Q(name__icontains=search_query) |
                Q(stream_letter__icontains=search_query) |
                Q(class_level__name__icontains=search_query)
            )
        
        ctx['streams'] = streams
        ctx['total_streams'] = streams.count()
        
        # Statistics
        ctx['total_capacity'] = streams.aggregate(total=models.Sum('capacity'))['total'] or 0
        ctx['total_students'] = streams.aggregate(total=models.Sum('current_student_count'))['total'] or 0
        ctx['available_capacity'] = ctx['total_capacity'] - ctx['total_students']
        
        # Get filter options
        ctx['class_levels'] = ClassLevel.objects.select_related('educational_level').all().order_by('educational_level', 'order')
        ctx['educational_levels'] = EducationalLevel.objects.all().order_by('level_type')
        
        # Store selected filters
        ctx['selected_class_level'] = int(class_level_id) if class_level_id else None
        ctx['selected_educational_level'] = int(educational_level_id) if educational_level_id else None
        ctx['search_query'] = search_query
        
        return ctx


class StreamClassCreateView(ManagementRequiredMixin, View):
    """Create a new stream class."""
    template_name = 'portal_management/academic/streams/form.html'
    
    def get_class_levels(self):
        """Get all class levels for the dropdown."""
        return ClassLevel.objects.select_related('educational_level').all().order_by('educational_level', 'order')
    
    def get(self, request):
        form = StreamClassForm()
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'class_levels': class_levels,
            'title': 'Add Stream Class',
            'is_update': False
        })
    
    def post(self, request):
        form = StreamClassForm(request.POST)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Stream class creation POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    stream = form.save()
                    
                    message = f'Stream class {stream.name} created successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:stream_class_detail', kwargs={'pk': stream.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:stream_class_detail', pk=stream.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Stream class creation validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Stream class creation error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error creating stream class: {e}')
        else:
            logger.debug(f"Form errors: {form.errors}")
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
        
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'class_levels': class_levels,
            'title': 'Add Stream Class',
            'is_update': False
        })


class StreamClassDetailView(ManagementRequiredMixin, TemplateView):
    """View detailed information about a stream class."""
    template_name = 'portal_management/academic/streams/detail.html'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        stream = get_object_or_404(
            StreamClass.objects.select_related(
                'class_level',
                'class_level__educational_level'
            ).prefetch_related(
                'stream_assignments__enrollment__student',
                'stream_assignments__enrollment__academic_year'
            ),
            pk=self.kwargs['pk']
        )
        
        ctx['stream'] = stream
        
        # Get current active students in this stream
        current_year = timezone.now().year
        ctx['current_students'] = stream.stream_assignments.filter(
            enrollment__status='active',
            enrollment__academic_year__is_active=True
        ).select_related(
            'enrollment__student',
            'enrollment__academic_year'
        ).order_by('enrollment__student__first_name', 'enrollment__student__last_name')[:20]
        
        # Get student count
        ctx['student_count'] = stream.stream_assignments.filter(
            enrollment__status='active',
            enrollment__academic_year__is_active=True
        ).count()
        
        # Get capacity utilization percentage
        if stream.capacity > 0:
            ctx['capacity_utilization'] = (ctx['student_count'] / stream.capacity) * 100
        else:
            ctx['capacity_utilization'] = 0
        
        return ctx


class StreamClassUpdateView(ManagementRequiredMixin, View):
    """Update an existing stream class."""
    template_name = 'portal_management/academic/streams/form.html'
    
    def get_class_levels(self):
        """Get all class levels for the dropdown."""
        return ClassLevel.objects.select_related('educational_level').all().order_by('educational_level', 'order')
    
    def get(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        form = StreamClassForm(instance=stream)
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'stream': stream,
            'class_levels': class_levels,
            'title': f'Edit Stream - {stream.name}',
            'is_update': True
        })
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        form = StreamClassForm(request.POST, instance=stream)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        logger.debug(f"Stream class update POST data: {request.POST}")
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    stream = form.save()
                    
                    message = f'Stream class {stream.name} updated successfully.'
                    
                    if is_ajax:
                        return JsonResponse({
                            'success': True,
                            'message': message,
                            'redirect_url': reverse('management:stream_class_detail', kwargs={'pk': stream.pk})
                        })
                    
                    messages.success(request, message)
                    return redirect('management:stream_class_detail', pk=stream.pk)
                    
            except ValidationError as e:
                error_msg = ', '.join(e.messages) if hasattr(e, 'messages') else str(e)
                logger.error(f"Stream class update validation error: {error_msg}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'errors': getattr(e, 'message_dict', {'__all__': [error_msg]})
                    }, status=400)
                messages.error(request, f'Validation error: {error_msg}')
                
            except Exception as e:
                logger.error(f"Stream class update error: {e}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': str(e),
                        'errors': {'__all__': [str(e)]}
                    }, status=500)
                messages.error(request, f'Error updating stream class: {e}')
        else:
            logger.debug(f"Form errors: {form.errors}")
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
        
        class_levels = self.get_class_levels()
        
        return render(request, self.template_name, {
            'form': form,
            'stream': stream,
            'class_levels': class_levels,
            'title': f'Edit Stream - {stream.name}',
            'is_update': True
        })


class StreamClassDeleteView(ManagementRequiredMixin, View):
    """Delete a stream class."""
    
    def post(self, request, pk):
        stream = get_object_or_404(StreamClass, pk=pk)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            stream_name = stream.name
            
            # Check if there are students assigned to this stream
            if stream.student_count > 0:
                error_msg = f'Cannot delete stream "{stream_name}" because it has {stream.student_count} student(s) assigned.'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('management:stream_class_detail', pk=stream.pk)
            
            with transaction.atomic():
                stream.delete()
            
            message = f'Stream class "{stream_name}" deleted successfully.'
            
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('management:stream_class_list')
                })
            
            messages.success(request, message)
            return redirect('management:stream_class_list')
            
        except Exception as e:
            logger.error(f"Stream class deletion error: {e}", exc_info=True)
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=500)
            messages.error(request, f'Error deleting stream class: {e}')
            return redirect('management:stream_class_detail', pk=pk)


