from django.contrib import messages
from django.shortcuts import render
from django.views.generic import TemplateView
from core.mixins import FinanceRequiredMixin


class DashboardView(FinanceRequiredMixin, TemplateView):
    template_name = 'portal_finance/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # TODO: add portal-specific context here
        return ctx
