from itertools import groupby
from types import SimpleNamespace

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.db.models import Count
from django.utils.dateparse import parse_date
from django_filters.views import FilterView

from .filters import ReportFilter, SiteFilter, WorkerFilter
from .forms import ReportForm, SiteForm, WorkerForm, WorkPlanForm, WorkPhotoFormSet
from .models import Report, Site, Worker, WorkPlan, PlanDocument, WorkSubmission


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "work/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.is_staff:
            ctx["today_plans"] = WorkPlan.objects.filter(work_date=timezone.localdate()).select_related("site", "worker")
            ctx["needs_review"] = WorkPlan.objects.filter(status=WorkPlan.Status.SUBMITTED).count()
        elif hasattr(self.request.user, "worker"):
            ctx["today_plans"] = WorkPlan.objects.filter(worker=self.request.user.worker, work_date=timezone.localdate()).select_related("site")
        return ctx


class WorkPlanListView(StaffRequiredMixin, ListView):
    model = WorkPlan
    template_name = "work/plan_list.html"
    paginate_by = 50

    def get_queryset(self):
        qs = WorkPlan.objects.select_related("site", "worker")
        for key, field in (("date", "work_date"), ("worker", "worker_id"), ("site", "site_id"), ("site_type", "site__site_type"), ("status", "status")):
            value = self.request.GET.get(key)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["workers"] = Worker.objects.order_by("name")
        ctx["sites"] = Site.objects.order_by("name")
        ctx["statuses"] = WorkPlan.Status.choices
        ctx["site_types"] = Site.SiteType.choices
        return ctx


class WorkPlanCreateView(StaffRequiredMixin, CreateView):
    model = WorkPlan
    form_class = WorkPlanForm
    template_name = "work/plan_form.html"
    success_url = reverse_lazy("plan_list")

    def get_initial(self):
        initial = super().get_initial()
        initial["work_date"] = timezone.localdate()
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx

    def form_valid(self, form):
        files = [item for item in self.request.FILES.getlist("documents") if item.name]
        if not files:
            form.add_error(None, "Добавьте хотя бы один PDF-файл к плану.")
            return self.form_invalid(form)
        error = validate_plan_documents(files, 20)
        if error:
            form.add_error(None, error)
            return self.form_invalid(form)
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        for uploaded in files:
            PlanDocument.objects.create(plan=self.object, file=uploaded)
        messages.success(self.request, "План работы создан и назначен работнику.")
        return redirect("plan_detail", pk=self.object.pk)


class WorkPlanUpdateView(StaffRequiredMixin, UpdateView):
    model = WorkPlan
    form_class = WorkPlanForm
    template_name = "work/plan_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["editing"] = True
        return ctx

    def form_valid(self, form):
        files = [item for item in self.request.FILES.getlist("documents") if item.name]
        current_count = self.object.documents.count()
        if current_count + len(files) == 0:
            form.add_error(None, "Добавьте хотя бы один PDF-файл к плану.")
            return self.form_invalid(form)
        error = validate_plan_documents(files, 20 - current_count)
        if error:
            form.add_error(None, error)
            return self.form_invalid(form)
        self.object = form.save()
        for uploaded in files:
            PlanDocument.objects.create(plan=self.object, file=uploaded)
        self.object.status = WorkPlan.Status.PLANNED
        self.object.review_comment = ""
        self.object.reviewed_at = None
        self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
        messages.success(self.request, "План работы обновлён.")
        return redirect("plan_detail", pk=self.object.pk)


def validate_plan_documents(files, remaining):
    if len(files) > remaining:
        return f"К одному плану можно прикрепить не более 20 PDF-файлов; свободно мест: {remaining}."
    for uploaded in files:
        if not uploaded.name.lower().endswith(".pdf"):
            return f"Файл «{uploaded.name}» не является PDF."
        if uploaded.read(5) != b"%PDF-":
            return f"Файл «{uploaded.name}» не распознан как PDF."
        uploaded.seek(0)
    return ""


class WorkPlanDetailView(LoginRequiredMixin, DetailView):
    model = WorkPlan
    template_name = "work/plan_detail.html"

    def get_queryset(self):
        return WorkPlan.objects.select_related("site", "worker").prefetch_related("documents", "submissions__photos__category")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_staff:
            plan = get_object_or_404(WorkPlan, pk=kwargs.get(self.pk_url_kwarg, self.kwargs.get(self.pk_url_kwarg)))
            if plan.worker.user_id != request.user.id:
                return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["photo_formset_invalid"] = kwargs.get("photo_formset_invalid", False)
        if not self.request.user.is_staff and self.object.status != WorkPlan.Status.APPROVED:
            submission = WorkSubmission(plan=self.object)
            ctx["photo_formset"] = WorkPhotoFormSet(instance=submission, prefix="photos")
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_staff:
            action = request.POST.get("action")
            if action == "reopen" and self.object.status == WorkPlan.Status.APPROVED:
                self.object.status = WorkPlan.Status.SUBMITTED
                self.object.review_comment = ""
                self.object.reviewed_at = None
                self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
                messages.success(request, "Работа снова отправлена на проверку.")
            elif self.object.status != WorkPlan.Status.SUBMITTED:
                messages.error(request, "Проверить можно только отправленный на проверку план.")
            elif action == "approve":
                self.object.status = WorkPlan.Status.APPROVED
                self.object.review_comment = ""
                self.object.reviewed_at = timezone.now()
                self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
                messages.success(request, "Работа принята.")
            elif action == "revision":
                comment = request.POST.get("review_comment", "").strip()
                if not comment:
                    messages.error(request, "Напишите, что нужно исправить.")
                else:
                    self.object.status = WorkPlan.Status.REVISION
                    self.object.review_comment = comment
                    self.object.reviewed_at = timezone.now()
                    self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
                    messages.success(request, "Работа возвращена на доработку.")
            return redirect("plan_detail", pk=self.object.pk)

        if self.object.worker.user_id != request.user.id:
            return HttpResponseForbidden()
        if self.object.status not in (WorkPlan.Status.PLANNED, WorkPlan.Status.REVISION):
            messages.error(request, "Это задание уже отправлено хозяину или принято.")
            return redirect("plan_detail", pk=self.object.pk)
        submission = WorkSubmission(plan=self.object)
        formset = WorkPhotoFormSet(request.POST, request.FILES, instance=submission, prefix="photos")
        formset_valid = formset.is_valid()
        if formset_valid and any(item.cleaned_data and not item.cleaned_data.get("DELETE") and item.cleaned_data.get("image") for item in formset.forms):
            submission.save()
            formset.instance = submission
            formset.save()
            self.object.status = WorkPlan.Status.SUBMITTED
            self.object.review_comment = ""
            self.object.reviewed_at = None
            self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
            messages.success(request, "Отчёт отправлен. Ожидайте одобрения хозяина.")
            return redirect("plan_detail", pk=self.object.pk)
        if not formset_valid:
            return self.render_to_response(self.get_context_data(
                photo_formset=formset, photo_formset_invalid=True,
            ))
        if formset_valid:
            messages.error(request, "Добавьте хотя бы одно фото перед отправкой.")
        return self.render_to_response(self.get_context_data(photo_formset=formset))


class WorkerPlanListView(LoginRequiredMixin, TemplateView):
    template_name = "work/worker_plans.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect("plan_list")
        if request.user.is_authenticated and not hasattr(request.user, "worker"):
            messages.error(request, "К аккаунту не привязан работник.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = WorkPlan.objects.select_related("site").filter(worker=self.request.user.worker)
        date_value = self.request.GET.get("date")
        if date_value and parse_date(date_value):
            qs = qs.filter(work_date=parse_date(date_value))
        status = self.request.GET.get("status")
        if status in WorkPlan.Status.values:
            qs = qs.filter(status=status)
        ctx["plans"] = qs
        ctx["selected_date"] = date_value or ""
        ctx["selected_status"] = status or ""
        ctx["statuses"] = WorkPlan.Status.choices
        ctx["today"] = timezone.localdate()
        return ctx


# ---------- Объекты ----------

class SiteListView(StaffRequiredMixin, FilterView):
    model = Site
    filterset_class = SiteFilter
    template_name = "work/site_list.html"

    def get_queryset(self):
        return super().get_queryset().annotate(
            legacy_report_count=Count("reports", distinct=True),
            submission_count=Count("work_plans__submissions", distinct=True),
        )


class SiteDetailView(StaffRequiredMixin, DetailView):
    model = Site
    template_name = "work/site_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["workers"] = self.object.workers.all()
        old_reports = self.object.reports.select_related("worker")
        submissions = WorkSubmission.objects.filter(plan__site=self.object).select_related(
            "plan__site", "plan__worker"
        ).prefetch_related("photos__category")
        entries = [_legacy_report_entry(report) for report in old_reports]
        entries.extend(_submission_report_entries(submissions))
        ctx["reports"] = sorted(entries, key=lambda report: report.created_at, reverse=True)
        ctx["report_total"] = sum(report.submission_count for report in entries)
        return ctx


class SiteCreateView(StaffRequiredMixin, CreateView):
    model = Site
    form_class = SiteForm
    template_name = "work/form.html"
    success_url = reverse_lazy("site_list")
    extra_context = {"title": "Новый объект", "back": "site_list"}


class SiteUpdateView(StaffRequiredMixin, UpdateView):
    model = Site
    form_class = SiteForm
    template_name = "work/form.html"
    success_url = reverse_lazy("site_list")
    extra_context = {"title": "Изменить объект", "back": "site_list"}


class SiteDeleteView(StaffRequiredMixin, DeleteView):
    model = Site
    template_name = "work/confirm_delete.html"
    success_url = reverse_lazy("site_list")
    extra_context = {
        "back": "site_list",
        "warning": "Вместе с объектом удалятся все его отчёты.",
    }


# ---------- Работники ----------

class WorkerListView(StaffRequiredMixin, FilterView):
    model = Worker
    filterset_class = WorkerFilter
    template_name = "work/worker_list.html"


class WorkerCreateView(StaffRequiredMixin, CreateView):
    model = Worker
    form_class = WorkerForm
    template_name = "work/form.html"
    success_url = reverse_lazy("worker_list")
    extra_context = {"title": "Новый работник", "back": "worker_list"}


class WorkerUpdateView(StaffRequiredMixin, UpdateView):
    model = Worker
    form_class = WorkerForm
    template_name = "work/form.html"
    success_url = reverse_lazy("worker_list")
    extra_context = {"title": "Изменить работника", "back": "worker_list"}


class WorkerDeleteView(StaffRequiredMixin, DeleteView):
    model = Worker
    template_name = "work/confirm_delete.html"
    success_url = reverse_lazy("worker_list")
    extra_context = {
        "back": "worker_list",
        "warning": "Вместе с работником удалятся его отчёты и учётная запись для входа.",
    }

    def form_valid(self, form):
        user = self.object.user
        response = super().form_valid(form)
        if user and not user.is_staff:
            user.delete()
        return response


# ---------- Отчёты ----------

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

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not hasattr(request.user, "worker"):
            messages.error(request, "К вашей учётной записи не привязан работник.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class ReportListView(StaffRequiredMixin, FilterView):
    model = Report
    filterset_class = ReportFilter
    template_name = "work/report_list.html"

    def get_queryset(self):
        qs = Report.objects.select_related("site", "worker")
        if self.request.GET.get("group") == "site":
            return qs.order_by("site__name", "-created_at")
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entries = [_legacy_report_entry(report) for report in ctx["object_list"]]
        filter_form = ctx["filter"].form
        filters = filter_form.cleaned_data if filter_form.is_valid() else {}
        submissions = WorkSubmission.objects.select_related("plan__site", "plan__worker").prefetch_related("photos__category")
        if filters.get("site"):
            submissions = submissions.filter(plan__site=filters["site"])
        if filters.get("worker"):
            submissions = submissions.filter(plan__worker=filters["worker"])
        date_range = filters.get("date")
        if date_range:
            if date_range.start:
                submissions = submissions.filter(created_at__date__gte=date_range.start)
            if date_range.stop:
                submissions = submissions.filter(created_at__date__lte=date_range.stop)
        entries.extend(_submission_report_entries(submissions))
        group = "site" if self.request.GET.get("group") == "site" else "date"
        if group == "site":
            entries.sort(key=lambda report: report.created_at, reverse=True)
            entries.sort(key=lambda report: report.site.name.casefold())
        else:
            entries.sort(key=lambda report: report.created_at, reverse=True)
        ctx["object_list"] = entries
        if group == "site":
            key = lambda r: r.site
        else:
            key = lambda r: timezone.localtime(r.created_at).date()
        ctx["group"] = group
        ctx["groups"] = [
            (k, list(items)) for k, items in groupby(ctx["object_list"], key=key)
        ]
        return ctx


class ReportDetailView(StaffRequiredMixin, DetailView):
    queryset = Report.objects.select_related("site", "worker")
    template_name = "work/report_detail.html"


class WorkSubmissionDetailView(StaffRequiredMixin, DetailView):
    model = WorkSubmission
    template_name = "work/submission_detail.html"

    def get_queryset(self):
        return WorkSubmission.objects.select_related("plan__site", "plan__worker").prefetch_related("photos__category")


def _legacy_report_entry(report):
    return SimpleNamespace(
        pk=report.pk,
        site=report.site,
        worker=report.worker,
        created_at=report.created_at,
        description=report.description,
        photo_url=report.photo.url,
        submission_count=1,
        photo_count=1,
        status=None,
        status_label="",
        detail_url=reverse_lazy("report_detail", kwargs={"pk": report.pk}),
    )


def _submission_report_entries(submissions):
    entries = []
    by_plan = {}
    for submission in submissions:
        by_plan.setdefault(submission.plan_id, []).append(submission)

    for attempts in by_plan.values():
        attempts.sort(key=lambda item: item.created_at, reverse=True)
        latest = attempts[0]
        plan = latest.plan
        latest_photos = list(latest.photos.all())
        photo_count = sum(len(list(item.photos.all())) for item in attempts)
        if not latest_photos:
            continue
        description = "\n".join(
            f"{photo.category.name}: {photo.description}" if photo.category else photo.description
            for photo in latest_photos
        )
        entries.append(SimpleNamespace(
            pk=plan.pk,
            site=plan.site,
            worker=plan.worker,
            created_at=latest.created_at,
            description=description,
            photo_url=latest_photos[0].image.url,
            submission_count=len(attempts),
            photo_count=photo_count,
            status=plan.status,
            status_label={
                WorkPlan.Status.PLANNED: "Запланирован",
                WorkPlan.Status.SUBMITTED: "В обработке",
                WorkPlan.Status.APPROVED: "Закрыт",
                WorkPlan.Status.REVISION: "Не принят",
            }.get(plan.status, ""),
            detail_url=reverse_lazy("plan_detail", kwargs={"pk": plan.pk}),
        ))
    return entries
