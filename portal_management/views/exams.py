"""
portal_management/views/exams.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Examination and grading views for the Management portal.

Covers:
  - Exam types CRUD
  - Exam sessions CRUD
  - Subject exam papers CRUD
  - Grading scales CRUD
  - Division scales CRUD
  - Trigger result calculation
  - Export results to Excel
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, TemplateView, View

from core.mixins import ManagementRequiredMixin
from core.models import (
    DivisionScale, ExamSession, ExamType,
    GradingScale, SubjectExamPaper,
)
from portal_management.forms.staff_form import DivisionScaleForm, ExamSessionForm, ExamTypeForm, GradingScaleForm


# ── Exam Type ─────────────────────────────────────────────────────────────────

class ExamTypeListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/exams/exam_types.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['exam_types'] = ExamType.objects.order_by('name')
        ctx['form'] = ExamTypeForm()
        return ctx


class ExamTypeCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = ExamTypeForm(request.POST)
        if form.is_valid():
            et = form.save()
            messages.success(request, f'Exam type "{et.name}" created.')
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:exam_type_list')


class ExamTypeUpdateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/exams/exam_type_form.html'

    def get(self, request, pk):
        et = get_object_or_404(ExamType, pk=pk)
        return render(request, self.template_name, {
            'form': ExamTypeForm(instance=et), 'exam_type': et,
        })

    def post(self, request, pk):
        et = get_object_or_404(ExamType, pk=pk)
        form = ExamTypeForm(request.POST, instance=et)
        if form.is_valid():
            form.save()
            messages.success(request, 'Exam type updated.')
            return redirect('management:exam_type_list')
        return render(request, self.template_name, {
            'form': form, 'exam_type': et,
        })


# ── Exam Session ──────────────────────────────────────────────────────────────

class ExamSessionListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/exams/sessions.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sessions'] = ExamSession.objects.select_related(
            'exam_type', 'academic_year', 'term', 'class_level'
        ).order_by('-exam_date')
        ctx['form'] = ExamSessionForm()
        return ctx


class ExamSessionCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = ExamSessionForm(request.POST)
        if form.is_valid():
            session = form.save()
            messages.success(
                request,
                f'Exam session "{session.name}" created.'
            )
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:exam_session_list')


class ExamSessionDetailView(ManagementRequiredMixin, DetailView):
    model = ExamSession
    template_name = 'portal_management/exams/session_detail.html'
    context_object_name = 'session'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = self.object
        ctx['papers'] = session.exam_papers.select_related('subject')
        ctx['results_count'] = session.subject_results.count()
        ctx['metrics_count'] = session.student_metrics.count()
        ctx['positions'] = session.student_positions.select_related(
            'student'
        ).order_by('class_position')[:20]
        from portal_management.forms import SubjectExamPaperForm
        ctx['paper_form'] = SubjectExamPaperForm(
            initial={'exam_session': session}
        )
        return ctx


class ExamSessionUpdateView(ManagementRequiredMixin, View):
    template_name = 'portal_management/exams/session_form.html'

    def get(self, request, pk):
        session = get_object_or_404(ExamSession, pk=pk)
        return render(request, self.template_name, {
            'form': ExamSessionForm(instance=session),
            'session': session,
        })

    def post(self, request, pk):
        session = get_object_or_404(ExamSession, pk=pk)
        form = ExamSessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, 'Exam session updated.')
            return redirect('management:exam_session_detail', pk=pk)
        return render(request, self.template_name, {
            'form': form, 'session': session,
        })


class ExamSessionPublishView(ManagementRequiredMixin, View):
    """Change exam session status to published."""
    def post(self, request, pk):
        session = get_object_or_404(ExamSession, pk=pk)
        if session.status != 'verified':
            messages.error(
                request,
                'Only verified sessions can be published. '
                'Please verify the results first.'
            )
            return redirect('management:exam_session_detail', pk=pk)
        session.status = 'published'
        session.save(update_fields=['status'])
        messages.success(
            request,
            f'"{session.name}" has been published. Students can now view results.'
        )
        return redirect('management:exam_session_detail', pk=pk)


# ── Subject Exam Paper ────────────────────────────────────────────────────────

class SubjectExamPaperCreateView(ManagementRequiredMixin, View):
    def post(self, request, session_pk):
        session = get_object_or_404(ExamSession, pk=session_pk)
        from portal_management.forms import SubjectExamPaperForm
        form = SubjectExamPaperForm(request.POST)
        if form.is_valid():
            paper = form.save()
            messages.success(
                request,
                f'Paper "{paper}" added to session.'
            )
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:exam_session_detail', pk=session_pk)


class SubjectExamPaperDeleteView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        paper = get_object_or_404(SubjectExamPaper, pk=pk)
        session_pk = paper.exam_session_id
        paper.delete()
        messages.success(request, 'Exam paper removed.')
        return redirect('management:exam_session_detail', pk=session_pk)


# ── Grading Scale ─────────────────────────────────────────────────────────────

class GradingScaleListView(ManagementRequiredMixin, TemplateView):
    template_name = 'portal_management/exams/grading_scales.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['grading_scales'] = GradingScale.objects.select_related(
            'education_level'
        ).order_by('education_level', '-min_mark')
        ctx['division_scales'] = DivisionScale.objects.select_related(
            'education_level'
        ).order_by('education_level', 'min_points')
        ctx['grading_form'] = GradingScaleForm()
        ctx['division_form'] = DivisionScaleForm()
        return ctx


class GradingScaleCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = GradingScaleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Grade band created.')
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:grading_scale_list')


class GradingScaleDeleteView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        gs = get_object_or_404(GradingScale, pk=pk)
        gs.delete()
        messages.success(request, 'Grade band deleted.')
        return redirect('management:grading_scale_list')


# ── Division Scale ────────────────────────────────────────────────────────────

class DivisionScaleCreateView(ManagementRequiredMixin, View):
    def post(self, request):
        form = DivisionScaleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Division band created.')
        else:
            messages.error(request, f'Error: {form.errors}')
        return redirect('management:grading_scale_list')


class DivisionScaleDeleteView(ManagementRequiredMixin, View):
    def post(self, request, pk):
        ds = get_object_or_404(DivisionScale, pk=pk)
        ds.delete()
        messages.success(request, 'Division band deleted.')
        return redirect('management:grading_scale_list')