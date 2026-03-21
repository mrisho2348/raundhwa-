# portal_management/views/exam_views.py

import json
import logging
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Prefetch
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View
from django.core.exceptions import ValidationError

from core.mixins import ManagementRequiredMixin
from core.models import (
    ExamType, ExamSession, AcademicYear, Term, ClassLevel, 
    StreamClass, Subject, Student, StudentPaperScore, 
    SubjectExamPaper, StudentSubjectResult, StudentExamMetrics,
    StudentExamPosition, GradingScale, DivisionScale
)
from portal_management.services import (
    calculate_session_results, calculate_subject_results,
    calculate_metrics, calculate_positions
)
from portal_management.utils import export_session_report

logger = logging.getLogger(__name__)


# ============================================================================
# EXAM TYPE CRUD
# ============================================================================

class ExamTypeListView(ManagementRequiredMixin, View):
    """List all exam types."""
    template_name = 'portal_management/exams/exam_type_list.html'
    paginate_by = 20
    
    def get_queryset(self, request):
        queryset = ExamType.objects.all().order_by('name')
        
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search)
            )
        
        return queryset
    
    def get(self, request):
        queryset = self.get_queryset(request)
        
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        exam_types = queryset[start:end]
        
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Generate page range
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
        
        context = {
            'exam_types': exam_types,
            'search_query': request.GET.get('search', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
            'page_range': page_range,
        }
        
        return render(request, self.template_name, context)


class ExamTypeCreateView(ManagementRequiredMixin, View):
    """Create a new exam type."""
    template_name = 'portal_management/exams/exam_type_form.html'
    
    def _format_errors(self, errors):
        formatted_errors = {}
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        return formatted_errors
    
    def get(self, request):
        context = {
            'title': 'Create Exam Type',
            'is_edit': False,
            'exam_type': None,
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        weight = request.POST.get('weight', '0')
        max_score = request.POST.get('max_score', '100')
        description = request.POST.get('description', '').strip()
        
        errors = {}
        
        if not name:
            errors['name'] = ['Name is required.']
        if not code:
            errors['code'] = ['Code is required.']
        if ExamType.objects.filter(code=code).exists():
            errors['code'] = [f'Exam type with code "{code}" already exists.']
        
        try:
            weight_decimal = Decimal(weight)
            if weight_decimal < 0 or weight_decimal > 100:
                errors['weight'] = ['Weight must be between 0 and 100.']
        except:
            errors['weight'] = ['Invalid weight value.']
        
        try:
            max_score_decimal = Decimal(max_score)
            if max_score_decimal < 1:
                errors['max_score'] = ['Max score must be at least 1.']
        except:
            errors['max_score'] = ['Invalid max score value.']
        
        if errors:
            if is_ajax:
                message = list(errors.values())[0][0] if errors else 'Please correct the errors below.'
                return JsonResponse({'success': False, 'message': message, 'errors': errors}, status=400)
            
            context = {
                'title': 'Create Exam Type',
                'is_edit': False,
                'exam_type': None,
                'form_data': request.POST,
                'errors': errors,
            }
            return render(request, self.template_name, context)
        
        try:
            with transaction.atomic():
                exam_type = ExamType.objects.create(
                    name=name,
                    code=code,
                    weight=weight_decimal,
                    max_score=max_score_decimal,
                    description=description
                )
                
                message = f'Exam type "{name}" created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:exam_type_list'),
                        'exam_type': {
                            'id': exam_type.pk,
                            'name': exam_type.name,
                            'code': exam_type.code,
                            'weight': float(exam_type.weight),
                            'max_score': float(exam_type.max_score),
                        }
                    })
                
                messages.success(request, message)
                return redirect('management:exam_type_list')
                
        except Exception as e:
            logger.error(f"Error creating exam type: {e}", exc_info=True)
            error_msg = f'Error creating exam type: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            context = {
                'title': 'Create Exam Type',
                'is_edit': False,
                'exam_type': None,
                'form_data': request.POST,
                'errors': {'__all__': [error_msg]},
            }
            return render(request, self.template_name, context)


class ExamTypeUpdateView(ManagementRequiredMixin, View):
    """Update an existing exam type."""
    template_name = 'portal_management/exams/exam_type_form.html'
    
    def _format_errors(self, errors):
        formatted_errors = {}
        if hasattr(errors, 'message_dict'):
            for field, error_list in errors.message_dict.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, dict):
            for field, error_list in errors.items():
                formatted_errors[field] = [str(error) for error in error_list]
        elif isinstance(errors, (list, tuple)):
            formatted_errors['__all__'] = [str(error) for error in errors]
        else:
            formatted_errors['__all__'] = [str(errors)]
        return formatted_errors
    
    def get(self, request, pk):
        exam_type = get_object_or_404(ExamType, pk=pk)
        context = {
            'title': f'Edit Exam Type: {exam_type.name}',
            'is_edit': True,
            'exam_type': exam_type,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        exam_type = get_object_or_404(ExamType, pk=pk)
        
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        weight = request.POST.get('weight', '0')
        max_score = request.POST.get('max_score', '100')
        description = request.POST.get('description', '').strip()
        
        errors = {}
        
        if not name:
            errors['name'] = ['Name is required.']
        if not code:
            errors['code'] = ['Code is required.']
        
        if code != exam_type.code and ExamType.objects.filter(code=code).exists():
            errors['code'] = [f'Exam type with code "{code}" already exists.']
        
        try:
            weight_decimal = Decimal(weight)
            if weight_decimal < 0 or weight_decimal > 100:
                errors['weight'] = ['Weight must be between 0 and 100.']
        except:
            errors['weight'] = ['Invalid weight value.']
        
        try:
            max_score_decimal = Decimal(max_score)
            if max_score_decimal < 1:
                errors['max_score'] = ['Max score must be at least 1.']
        except:
            errors['max_score'] = ['Invalid max score value.']
        
        if errors:
            if is_ajax:
                message = list(errors.values())[0][0] if errors else 'Please correct the errors below.'
                return JsonResponse({'success': False, 'message': message, 'errors': errors}, status=400)
            
            context = {
                'title': f'Edit Exam Type: {exam_type.name}',
                'is_edit': True,
                'exam_type': exam_type,
                'form_data': request.POST,
                'errors': errors,
            }
            return render(request, self.template_name, context)
        
        try:
            with transaction.atomic():
                exam_type.name = name
                exam_type.code = code
                exam_type.weight = weight_decimal
                exam_type.max_score = max_score_decimal
                exam_type.description = description
                exam_type.save()
                
                message = f'Exam type "{name}" updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:exam_type_list'),
                    })
                
                messages.success(request, message)
                return redirect('management:exam_type_list')
                
        except Exception as e:
            logger.error(f"Error updating exam type {pk}: {e}", exc_info=True)
            error_msg = f'Error updating exam type: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            context = {
                'title': f'Edit Exam Type: {exam_type.name}',
                'is_edit': True,
                'exam_type': exam_type,
                'form_data': request.POST,
                'errors': {'__all__': [error_msg]},
            }
            return render(request, self.template_name, context)


class ExamTypeDeleteView(ManagementRequiredMixin, View):
    """Delete an exam type."""
    
    def check_dependencies(self, exam_type):
        """Check if exam type has dependent sessions."""
        sessions = ExamSession.objects.filter(exam_type=exam_type)
        if sessions.exists():
            return [f'Has {sessions.count()} exam session(s) associated.']
        return []
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        exam_type = get_object_or_404(ExamType, pk=pk)
        
        dependencies = self.check_dependencies(exam_type)
        
        if dependencies:
            error_msg = f'Cannot delete exam type: {", ".join(dependencies)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'has_dependencies': True,
                    'dependencies': dependencies
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_type_list')
        
        try:
            name = exam_type.name
            exam_type.delete()
            message = f'Exam type "{name}" deleted successfully!'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message})
            
            messages.success(request, message)
            return redirect('management:exam_type_list')
            
        except Exception as e:
            logger.error(f"Error deleting exam type {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting exam type: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_type_list')


class ExamTypeSearchView(ManagementRequiredMixin, View):
    """AJAX search for exam types."""
    
    def get(self, request):
        term = request.GET.get('term', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        
        queryset = ExamType.objects.all().order_by('name')
        
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term) | Q(code__icontains=term)
            )
        
        start = (page - 1) * page_size
        end = start + page_size
        exam_types = queryset[start:end]
        total_count = queryset.count()
        
        results = [
            {
                'id': et.pk,
                'text': f"{et.name} ({et.code}) - {et.weight}%",
                'name': et.name,
                'code': et.code,
                'weight': float(et.weight),
                'max_score': float(et.max_score),
            }
            for et in exam_types
        ]
        
        return JsonResponse({
            'results': results,
            'pagination': {'more': end < total_count, 'total': total_count}
        })


# ============================================================================
# EXAM SESSION CRUD
# ============================================================================

class ExamSessionListView(ManagementRequiredMixin, View):
    """List all exam sessions."""
    template_name = 'portal_management/exams/exam_session_list.html'
    paginate_by = 20
    
    def get_queryset(self, request):
        queryset = ExamSession.objects.all().select_related(
            'exam_type', 'academic_year', 'term', 'class_level', 'stream_class'
        ).order_by('-exam_date')
        
        search = request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(exam_type__name__icontains=search) |
                Q(class_level__name__icontains=search)
            )
        
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        academic_year = request.GET.get('academic_year')
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        
        class_level = request.GET.get('class_level')
        if class_level:
            queryset = queryset.filter(class_level_id=class_level)
        
        return queryset
    
    def get(self, request):
        queryset = self.get_queryset(request)
        
        page = int(request.GET.get('page', 1))
        start = (page - 1) * self.paginate_by
        end = start + self.paginate_by
        sessions = queryset[start:end]
        
        total_count = queryset.count()
        total_pages = (total_count + self.paginate_by - 1) // self.paginate_by
        
        # Get filter data
        academic_years = AcademicYear.objects.all().order_by('-start_date')
        class_levels = ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order')
        
        # Calculate statistics
        draft_count = ExamSession.objects.filter(status='draft').count()
        submitted_count = ExamSession.objects.filter(status='submitted').count()
        verified_count = ExamSession.objects.filter(status='verified').count()
        published_count = ExamSession.objects.filter(status='published').count()
        
        context = {
            'sessions': sessions,
            'academic_years': academic_years,
            'class_levels': class_levels,
            'status_choices': ExamSession.STATUS_CHOICES,
            'search_query': request.GET.get('search', ''),
            'selected_status': request.GET.get('status', ''),
            'selected_academic_year': request.GET.get('academic_year', ''),
            'selected_class_level': request.GET.get('class_level', ''),
            'current_page': page,
            'total_pages': total_pages,
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'previous_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None,
            'total_count': total_count,
            'draft_count': draft_count,
            'submitted_count': submitted_count,
            'verified_count': verified_count,
            'published_count': published_count,
        }
        
        return render(request, self.template_name, context)


class ExamSessionCreateView(ManagementRequiredMixin, View):
    """Create a new exam session."""
    template_name = 'portal_management/exams/exam_session_form.html'
    
    def _get_form_data(self):
        # Get all terms grouped by academic year for dynamic loading
        all_terms = Term.objects.all().select_related('academic_year').values(
            'id', 'name', 'term_number', 'academic_year_id', 'start_date', 'end_date'
        )
        
        terms_by_year = {}
        for term in all_terms:
            year_id = term['academic_year_id']
            if year_id not in terms_by_year:
                terms_by_year[year_id] = []
            terms_by_year[year_id].append({
                'id': term['id'],
                'name': f"Term {term['term_number']}",
                'term_number': term['term_number'],
                'start_date': term['start_date'].strftime('%Y-%m-%d'),
                'end_date': term['end_date'].strftime('%Y-%m-%d'),
            })
        
        return {
            'exam_types': ExamType.objects.all().order_by('name'),
            'academic_years': AcademicYear.objects.all().order_by('-start_date'),
            'class_levels': ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order'),
            'stream_classes': StreamClass.objects.all().select_related('class_level').order_by('class_level', 'stream_letter'),
            'status_choices': ExamSession.STATUS_CHOICES,
            'terms_data': json.dumps(terms_by_year),  # This is the key addition
        }
    
    def get(self, request):
        context = {
            'title': 'Create Exam Session',
            'is_edit': False,
            'session': None,
            **self._get_form_data(),
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        try:
            with transaction.atomic():
                session = ExamSession(
                    name=request.POST.get('name', '').strip(),
                    exam_type_id=request.POST.get('exam_type'),
                    academic_year_id=request.POST.get('academic_year'),
                    term_id=request.POST.get('term'),
                    class_level_id=request.POST.get('class_level'),
                    stream_class_id=request.POST.get('stream_class') or None,
                    exam_date=request.POST.get('exam_date'),
                    status=request.POST.get('status', 'draft'),
                )
                session.full_clean()
                session.save()
                
                message = f'Exam session "{session.name}" created successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:exam_session_detail', args=[session.pk]),
                    })
                
                messages.success(request, message)
                return redirect('management:exam_session_detail', pk=session.pk)
                
        except ValidationError as e:
            errors = {}
            if hasattr(e, 'message_dict'):
                errors = e.message_dict
            else:
                errors['__all__'] = [str(e)]
            
            if is_ajax:
                message = list(errors.values())[0][0] if errors else 'Please correct the errors below.'
                return JsonResponse({'success': False, 'message': message, 'errors': errors}, status=400)
            
            context = {
                'title': 'Create Exam Session',
                'is_edit': False,
                'session': None,
                'form_data': request.POST,
                'errors': errors,
                **self._get_form_data(),
            }
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Error creating exam session: {e}", exc_info=True)
            error_msg = f'Error creating exam session: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            context = {
                'title': 'Create Exam Session',
                'is_edit': False,
                'session': None,
                'form_data': request.POST,
                'errors': {'__all__': [error_msg]},
                **self._get_form_data(),
            }
            return render(request, self.template_name, context)


# In your views.py, add this class
class TermsByAcademicYearView(ManagementRequiredMixin, View):
    """AJAX endpoint to get terms for a specific academic year."""
    
    def get(self, request):
        academic_year_id = request.GET.get('academic_year_id')
        if not academic_year_id:
            return JsonResponse({'terms': []})
        
        terms = Term.objects.filter(
            academic_year_id=academic_year_id
        ).values('id', 'name', 'term_number', 'start_date', 'end_date').order_by('term_number')
        
        terms_list = []
        for term in terms:
            terms_list.append({
                'id': term['id'],
                'name': f"Term {term['term_number']}",
                'term_number': term['term_number'],
                'start_date': term['start_date'].strftime('%Y-%m-%d'),
                'end_date': term['end_date'].strftime('%Y-%m-%d'),
            })
        
        return JsonResponse({'terms': terms_list})
    

class ExamSessionDetailView(ManagementRequiredMixin, View):
    """Display exam session details with results."""
    template_name = 'portal_management/exams/exam_session_detail.html'
    
    def get(self, request, pk):
        session = get_object_or_404(
            ExamSession.objects.select_related(
                'exam_type', 'academic_year', 'term', 'class_level', 'stream_class'
            ),
            pk=pk
        )
        
        # Get statistics
        paper_count = SubjectExamPaper.objects.filter(exam_session=session).count()
        student_count = StudentSubjectResult.objects.filter(exam_session=session).values('student').distinct().count()
        metrics_count = StudentExamMetrics.objects.filter(exam_session=session).count()
        
        # Check if results have been calculated
        has_results = StudentSubjectResult.objects.filter(exam_session=session).exists()
        has_metrics = StudentExamMetrics.objects.filter(exam_session=session).exists()
        has_positions = StudentExamPosition.objects.filter(exam_session=session).exists()
        
        context = {
            'session': session,
            'paper_count': paper_count,
            'student_count': student_count,
            'metrics_count': metrics_count,
            'has_results': has_results,
            'has_metrics': has_metrics,
            'has_positions': has_positions,
            'status_choices': ExamSession.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)


class ExamSessionUpdateView(ManagementRequiredMixin, View):
    """Update an existing exam session."""
    template_name = 'portal_management/exams/exam_session_form.html'
    
    def _get_form_data(self):
        # Get all terms grouped by academic year for dynamic loading
        all_terms = Term.objects.all().select_related('academic_year').values(
            'id', 'name', 'term_number', 'academic_year_id', 'start_date', 'end_date'
        )
        
        terms_by_year = {}
        for term in all_terms:
            year_id = term['academic_year_id']
            if year_id not in terms_by_year:
                terms_by_year[year_id] = []
            terms_by_year[year_id].append({
                'id': term['id'],
                'name': f"Term {term['term_number']}",
                'term_number': term['term_number'],
                'start_date': term['start_date'].strftime('%Y-%m-%d'),
                'end_date': term['end_date'].strftime('%Y-%m-%d'),
            })
        
        return {
            'exam_types': ExamType.objects.all().order_by('name'),
            'academic_years': AcademicYear.objects.all().order_by('-start_date'),
            'class_levels': ClassLevel.objects.all().select_related('educational_level').order_by('educational_level', 'order'),
            'stream_classes': StreamClass.objects.all().select_related('class_level').order_by('class_level', 'stream_letter'),
            'status_choices': ExamSession.STATUS_CHOICES,
            'terms_data': json.dumps(terms_by_year),  # This is the key addition
        }
    
    def get(self, request, pk):
        session = get_object_or_404(ExamSession, pk=pk)
        
        # Don't allow editing if results are published
        if session.status == 'published':
            messages.warning(request, 'Published exam sessions cannot be edited.')
            return redirect('management:exam_session_detail', pk=pk)
        
        context = {
            'title': f'Edit Exam Session: {session.name}',
            'is_edit': True,
            'session': session,
            **self._get_form_data(),
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        if session.status == 'published':
            error_msg = 'Published exam sessions cannot be edited.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            with transaction.atomic():
                session.name = request.POST.get('name', '').strip()
                session.exam_type_id = request.POST.get('exam_type')
                session.academic_year_id = request.POST.get('academic_year')
                session.term_id = request.POST.get('term')
                session.class_level_id = request.POST.get('class_level')
                session.stream_class_id = request.POST.get('stream_class') or None
                session.exam_date = request.POST.get('exam_date')
                session.status = request.POST.get('status', session.status)
                
                session.full_clean()
                session.save()
                
                message = f'Exam session "{session.name}" updated successfully!'
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': message,
                        'redirect_url': reverse('management:exam_session_detail', args=[session.pk]),
                    })
                
                messages.success(request, message)
                return redirect('management:exam_session_detail', pk=session.pk)
                
        except ValidationError as e:
            errors = {}
            if hasattr(e, 'message_dict'):
                errors = e.message_dict
            else:
                errors['__all__'] = [str(e)]
            
            if is_ajax:
                message = list(errors.values())[0][0] if errors else 'Please correct the errors below.'
                return JsonResponse({'success': False, 'message': message, 'errors': errors}, status=400)
            
            context = {
                'title': f'Edit Exam Session: {session.name}',
                'is_edit': True,
                'session': session,
                'form_data': request.POST,
                'errors': errors,
                **self._get_form_data(),
            }
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Error updating exam session {pk}: {e}", exc_info=True)
            error_msg = f'Error updating exam session: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            context = {
                'title': f'Edit Exam Session: {session.name}',
                'is_edit': True,
                'session': session,
                'form_data': request.POST,
                'errors': {'__all__': [error_msg]},
                **self._get_form_data(),
            }
            return render(request, self.template_name, context)
        

class ExamSessionDeleteView(ManagementRequiredMixin, View):
    """Delete an exam session."""
    
    def check_dependencies(self, session):
        """Check if session has any associated data."""
        dependencies = []
        
        paper_count = SubjectExamPaper.objects.filter(exam_session=session).count()
        if paper_count > 0:
            dependencies.append(f'Has {paper_count} exam paper(s) associated.')
        
        result_count = StudentSubjectResult.objects.filter(exam_session=session).count()
        if result_count > 0:
            dependencies.append(f'Has {result_count} student result(s) associated.')
        
        return dependencies
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        dependencies = self.check_dependencies(session)
        
        if dependencies:
            error_msg = f'Cannot delete exam session: {", ".join(dependencies)}'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                    'has_dependencies': True,
                    'dependencies': dependencies
                }, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            name = session.name
            session.delete()
            message = f'Exam session "{name}" deleted successfully!'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message})
            
            messages.success(request, message)
            return redirect('management:exam_session_list')
            
        except Exception as e:
            logger.error(f"Error deleting exam session {pk}: {e}", exc_info=True)
            error_msg = f'Error deleting exam session: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


# ============================================================================
# RESULT CALCULATION VIEWS
# ============================================================================

class CalculateSubjectResultsView(ManagementRequiredMixin, View):
    """Calculate subject results for an exam session."""
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        if session.status == 'published':
            error_msg = 'Published exam sessions cannot be recalculated.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            result = calculate_subject_results(pk)
            
            message = f'Subject results calculated: {result["created"]} created, {result["updated"]} updated.'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message, 'result': result})
            
            messages.success(request, message)
            return redirect('management:exam_session_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error calculating subject results for session {pk}: {e}", exc_info=True)
            error_msg = f'Error calculating subject results: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


class CalculateMetricsView(ManagementRequiredMixin, View):
    """Calculate metrics for an exam session."""
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        if session.status == 'published':
            error_msg = 'Published exam sessions cannot be recalculated.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            result = calculate_metrics(pk)
            
            message = f'Metrics calculated: {result["created"]} created, {result["updated"]} updated, {result["skipped"]} skipped.'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message, 'result': result})
            
            messages.success(request, message)
            return redirect('management:exam_session_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error calculating metrics for session {pk}: {e}", exc_info=True)
            error_msg = f'Error calculating metrics: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


class CalculatePositionsView(ManagementRequiredMixin, View):
    """Calculate positions for an exam session."""
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        if session.status == 'published':
            error_msg = 'Published exam sessions cannot be recalculated.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            result = calculate_positions(pk)
            
            message = f'Positions calculated: {result["class_positions"]} class positions, {result["stream_positions"]} stream positions.'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message, 'result': result})
            
            messages.success(request, message)
            return redirect('management:exam_session_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error calculating positions for session {pk}: {e}", exc_info=True)
            error_msg = f'Error calculating positions: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


class CalculateFullResultsView(ManagementRequiredMixin, View):
    """Calculate full results for an exam session."""
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        if session.status == 'published':
            error_msg = 'Published exam sessions cannot be recalculated.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            result = calculate_session_results(pk)
            
            subject_res = result['subject_results']
            metrics_res = result['metrics']
            positions_res = result['positions']
            
            message = (
                f'Full results calculated:\n'
                f'Subject Results: {subject_res["created"]} created, {subject_res["updated"]} updated\n'
                f'Metrics: {metrics_res["created"]} created, {metrics_res["updated"]} updated, {metrics_res["skipped"]} skipped\n'
                f'Positions: {positions_res["class_positions"]} class, {positions_res["stream_positions"]} stream'
            )
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message, 'result': result})
            
            messages.success(request, message)
            return redirect('management:exam_session_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error calculating full results for session {pk}: {e}", exc_info=True)
            error_msg = f'Error calculating results: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


class PublishExamSessionView(ManagementRequiredMixin, View):
    """Publish an exam session (mark as published)."""
    
    def post(self, request, pk):
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        session = get_object_or_404(ExamSession, pk=pk)
        
        # Check if results exist before publishing
        has_metrics = StudentExamMetrics.objects.filter(exam_session=session).exists()
        
        if not has_metrics:
            error_msg = 'Cannot publish session without calculated metrics.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)
        
        try:
            session.status = 'published'
            session.save()
            
            message = f'Exam session "{session.name}" has been published.'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': message})
            
            messages.success(request, message)
            return redirect('management:exam_session_detail', pk=pk)
            
        except Exception as e:
            logger.error(f"Error publishing exam session {pk}: {e}", exc_info=True)
            error_msg = f'Error publishing session: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=500)
            
            messages.error(request, error_msg)
            return redirect('management:exam_session_detail', pk=pk)


class ExportSessionReportView(ManagementRequiredMixin, View):
    """Export exam session results to Excel."""
    
    def get(self, request, pk):
        session = get_object_or_404(ExamSession, pk=pk)
        
        try:
            workbook = export_session_report(session)
            
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="exam_results_{session.name}_{date.today()}.xlsx"'
            
            workbook.save(response)
            return response
            
        except Exception as e:
            logger.error(f"Error exporting session report {pk}: {e}", exc_info=True)
            messages.error(request, f'Error exporting report: {str(e)}')
            return redirect('management:exam_session_detail', pk=pk)