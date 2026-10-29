from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

from .filters import SiteFilter, WorkerFilter
from .forms import ReportForm
from .models import Site, Worker


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "work/dashboard.html"


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class SiteListView(StaffRequiredMixin, FilterView):
    model = Site
    filterset_class = SiteFilter
    template_name = "work/site_list.html"


class WorkerListView(StaffRequiredMixin, FilterView):
    model = Worker
    filterset_class = WorkerFilter
    template_name = "work/worker_list.html"


class ReportCreateView(LoginRequiredMixin, CreateView):
    form_class = ReportForm
    template_name = "work/report_form.html"
    success_url = reverse_lazy("dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["worker"] = self.request.user.worker
        return kwargs

    def form_valid(self, form):
        form.instance.worker = self.request.user.worker
        return super().form_valid(form)


