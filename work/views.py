from itertools import groupby
from types import SimpleNamespace
from datetime import date, datetime, time, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.forms import inlineformset_factory
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from django.contrib import messages
from django.core.files.storage import default_storage
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponseForbidden
from django.db.models import Case, Count, DateTimeField, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_date
from django_filters.views import FilterView

from .filters import ReportFilter, SiteFilter
from .forms import (
    ReportForm, SiteForm, SitePhotoRequirementFormSet, WorkerForm,
    WorkPlanForm, WorkPhotoForm, RequiredSlotInlineFormSet,
)
from .models import (
    Report, Site, SiteDocument, SitePhotoRequirement, Worker, WorkPlan,
    WorkPhoto, WorkShift, WorkSubmission,
)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def plan_status_order():
    return Case(
        When(status=WorkPlan.Status.SUBMITTED, then=Value(0)),
        When(status=WorkPlan.Status.PLANNED, then=Value(1)),
        When(status=WorkPlan.Status.REVISION, then=Value(2)),
        When(status=WorkPlan.Status.APPROVED, then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )


def _day_bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), tz)
    return start, end


def _month_start(day):
    return timezone.make_aware(
        datetime.combine(day.replace(day=1), time.min),
        timezone.get_current_timezone(),
    )


def _shift_seconds(shifts, interval_start, interval_end):
    seconds = 0
    for shift in shifts:
        start = max(shift.started_at, interval_start)
        end = min(shift.ended_at or interval_end, interval_end)
        if end > start:
            seconds += int((end - start).total_seconds())
    return seconds


def _format_hours(seconds):
    hours, remainder = divmod(max(0, seconds), 3600)
    return f"{hours} ч {remainder // 60:02d} мин"


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "work/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.user.is_staff:
            ctx["today_plans"] = WorkPlan.objects.filter(work_date=timezone.localdate()).select_related("site", "worker")
            ctx["needs_review"] = WorkPlan.objects.filter(status=WorkPlan.Status.SUBMITTED).count()
            now = timezone.now()
            today = timezone.localdate()
            day_start, day_end = _day_bounds(today)
            month_start = _month_start(today)
            shift_map = {}
            for shift in WorkShift.objects.filter(
                started_at__lt=now,
            ).filter(
                Q(ended_at__gt=month_start) | Q(ended_at__isnull=True)
            ).select_related("worker").order_by("started_at"):
                shift_map.setdefault(shift.worker_id, []).append(shift)
            worker_rows = []
            for worker in Worker.objects.order_by("name"):
                shifts = shift_map.get(worker.pk, [])
                current_shift = next((shift for shift in reversed(shifts) if shift.ended_at is None), None)
                today_seconds = _shift_seconds(shifts, day_start, min(day_end, now))
                month_seconds = _shift_seconds(shifts, month_start, now)
                worker_rows.append({
                    "worker": worker,
                    "current_shift": current_shift,
                    "over_eight_hours": bool(current_shift and now - current_shift.started_at >= timedelta(hours=8)),
                    "today_hours": _format_hours(today_seconds),
                    "month_hours": _format_hours(month_seconds),
                })
            ctx["worker_time_rows"] = worker_rows
        elif hasattr(self.request.user, "worker"):
            worker = self.request.user.worker
            now = timezone.now()
            today = timezone.localdate()
            day_start, day_end = _day_bounds(today)
            month_start = _month_start(today)
            today_plans = WorkPlan.objects.filter(
                worker=worker,
                work_date=today,
            ).select_related("site")
            active_today = today_plans.exclude(status=WorkPlan.Status.APPROVED)
            future_plans = WorkPlan.objects.filter(
                worker=worker, work_date__gt=today,
            ).exclude(status=WorkPlan.Status.APPROVED).select_related("site").annotate(
                status_order=plan_status_order()
            ).order_by("work_date", "status_order", "site__name", "pk")
            ctx["active_today_count"] = active_today.count()
            ctx["active_future_count"] = future_plans.count()
            ctx["future_plan_groups"] = [
                (day, list(items)) for day, items in groupby(future_plans, key=lambda plan: plan.work_date)
            ]
            shifts = list(WorkShift.objects.filter(
                worker=worker, started_at__lt=now,
            ).filter(Q(ended_at__gt=month_start) | Q(ended_at__isnull=True)).order_by("started_at"))
            ctx["current_shift"] = next((shift for shift in reversed(shifts) if shift.ended_at is None), None)
            ctx["shift_over_eight_hours"] = bool(
                ctx["current_shift"] and now - ctx["current_shift"].started_at >= timedelta(hours=8)
            )
            ctx["today_work_hours"] = _format_hours(_shift_seconds(shifts, day_start, min(day_end, now)))
            ctx["month_work_hours"] = _format_hours(_shift_seconds(shifts, month_start, now))
        return ctx


class WorkerShiftView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return not self.request.user.is_staff and hasattr(self.request.user, "worker")

    def post(self, request, *args, **kwargs):
        raise NotImplementedError


class WorkerShiftStartView(WorkerShiftView):
    def post(self, request, *args, **kwargs):
        worker = request.user.worker
        if WorkShift.objects.filter(worker=worker, ended_at__isnull=True).exists():
            messages.info(request, "Смена уже начата.")
        else:
            try:
                with transaction.atomic():
                    WorkShift.objects.create(worker=worker)
                messages.success(request, "Смена начата. Время пошло.")
            except IntegrityError:
                messages.info(request, "Смена уже начата.")
        return redirect("dashboard")


class WorkerShiftEndView(WorkerShiftView):
    def post(self, request, *args, **kwargs):
        shift = WorkShift.objects.filter(
            worker=request.user.worker, ended_at__isnull=True,
        ).order_by("-started_at").first()
        if not shift:
            messages.error(request, "Нет открытой смены для завершения.")
        else:
            shift.ended_at = timezone.now()
            shift.save(update_fields=["ended_at"])
            messages.success(request, "Смена завершена.")
        return redirect("dashboard")


class WorkPlanListView(StaffRequiredMixin, ListView):
    model = WorkPlan
    template_name = "work/plan_list.html"
    paginate_by = 50

    def get_queryset(self):
        qs = WorkPlan.objects.select_related("site", "worker")
        for key, field in (("date", "work_date"), ("site", "site_id"), ("site_type", "site__site_type"), ("status", "status")):
            value = self.request.GET.get(key)
            if value:
                qs = qs.filter(**{field: value})
        site_number = self.request.GET.get("site_number", "").strip()
        if site_number:
            qs = qs.filter(site__object_number__icontains=site_number)
        site_name = self.request.GET.get("site_name", "").strip()
        if site_name:
            qs = qs.filter(site__name__icontains=site_name)
        address = self.request.GET.get("address", "").strip()
        if address:
            qs = qs.filter(site__address__icontains=address)
        return qs.annotate(status_order=plan_status_order()).order_by(
            "-work_date", "status_order", "site__name", "pk"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = Site.objects.order_by("name")
        ctx["statuses"] = WorkPlan.Status.choices
        ctx["site_types"] = Site.SiteType.choices
        today = timezone.localdate()
        filter_keys = ("date", "site", "site_number", "site_name", "address", "site_type", "status")
        has_filters = any(self.request.GET.get(key, "").strip() for key in filter_keys)
        ctx["history_mode"] = self.request.GET.get("history") == "1" or has_filters
        if ctx["history_mode"]:
            plans = ctx["object_list"]
            ctx["date_groups"] = [
                (day, list(items)) for day, items in groupby(plans, key=lambda plan: plan.work_date)
            ]
        else:
            plans = self.get_queryset()
            ctx["today_plans"] = plans.filter(work_date=today)
            upcoming = plans.filter(
                work_date__gt=today,
                status=WorkPlan.Status.PLANNED,
            ).order_by("work_date", "status_order", "site__name", "pk")
            ctx["upcoming_count"] = upcoming.count()
            completed = plans.filter(
                work_date__lt=today,
                status=WorkPlan.Status.APPROVED,
            ).order_by("-work_date", "site__name", "pk")
            ctx["upcoming_groups"] = [
                (day, list(items)) for day, items in groupby(upcoming, key=lambda plan: plan.work_date)
            ]
            ctx["completed_groups"] = [
                (day, list(items)) for day, items in groupby(completed, key=lambda plan: plan.work_date)
            ]
        query = self.request.GET.copy()
        query.pop("page", None)
        ctx["query_string"] = query.urlencode()
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
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        Site.objects.filter(pk=self.object.site_id).update(is_completed=False)
        messages.success(self.request, "План работы создан и назначен работнику.")
        return redirect("plan_detail", pk=self.object.pk)


class WorkPlanUpdateView(StaffRequiredMixin, UpdateView):
    model = WorkPlan
    form_class = WorkPlanForm
    template_name = "work/plan_form.html"

    def get_queryset(self):
        return WorkPlan.objects.filter(status=WorkPlan.Status.PLANNED).select_related(
            "site", "worker"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["editing"] = True
        return ctx

    def form_valid(self, form):
        self.object = form.save()
        self.object.status = WorkPlan.Status.PLANNED
        self.object.review_comment = ""
        self.object.reviewed_at = None
        self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
        Site.objects.filter(pk=self.object.site_id).update(is_completed=False)
        messages.success(self.request, "План работы обновлён.")
        return redirect("plan_detail", pk=self.object.pk)


class WorkPlanDeleteView(StaffRequiredMixin, DeleteView):
    model = WorkPlan
    template_name = "work/confirm_delete.html"
    success_url = reverse_lazy("plan_list")
    extra_context = {
        "back": "plan_list",
        "warning": "План и связанные с ним материалы будут удалены.",
    }

    def get_queryset(self):
        return WorkPlan.objects.filter(status=WorkPlan.Status.PLANNED).select_related(
            "site", "worker"
        )

    def form_valid(self, form):
        messages.success(self.request, "Запланированный план работы удалён.")
        return super().form_valid(form)


def validate_pdf_documents(files, remaining, owner_label):
    if len(files) > remaining:
        return f"К одному {owner_label} можно прикрепить не более 20 PDF-файлов; свободно мест: {remaining}."
    for uploaded in files:
        if not uploaded.name.lower().endswith(".pdf"):
            return f"Файл «{uploaded.name}» не является PDF."
        if uploaded.read(5) != b"%PDF-":
            return f"Файл «{uploaded.name}» не распознан как PDF."
        uploaded.seek(0)
    return ""


def work_photo_formset_for(plan, submission, data=None, files=None):
    slots = list(plan.site.photo_requirements.select_related("category"))
    if not slots:
        return None
    formset_class = inlineformset_factory(
        WorkSubmission,
        WorkPhoto,
        form=WorkPhotoForm,
        formset=RequiredSlotInlineFormSet,
        extra=len(slots),
        min_num=len(slots),
        validate_min=True,
        max_num=len(slots),
        validate_max=True,
        can_delete=False,
    )
    return formset_class(
        data=data,
        files=files,
        instance=submission,
        prefix="photos",
        slots=slots,
    )


class SiteFormProcessMixin:
    """Handle an object's fixed photo checklist and its attached PDF files."""

    def get_photo_requirement_formset(self, instance=None, data=None):
        return SitePhotoRequirementFormSet(
            data=data,
            instance=instance or self.object or Site(),
            prefix="requirements",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["site_form"] = True
        ctx["photo_requirement_formset"] = getattr(
            self, "photo_requirement_formset", None
        ) or self.get_photo_requirement_formset()
        ctx["site_documents"] = (
            self.object.documents.all() if getattr(self, "object", None) and self.object.pk else []
        )
        ctx["editing"] = bool(getattr(self, "object", None) and self.object.pk)
        return ctx

    def form_valid(self, form):
        current_count = self.object.documents.count() if self.object and self.object.pk else 0
        uploaded_files = [f for f in self.request.FILES.getlist("documents") if f.name]
        self.photo_requirement_formset = self.get_photo_requirement_formset(
            instance=form.instance, data=self.request.POST,
        )
        error = validate_pdf_documents(uploaded_files, 20 - current_count, "объекту")
        if error:
            form.add_error(None, error)
            return self.form_invalid(form)

        if not self.photo_requirement_formset.is_valid():
            return self.form_invalid(form)

        self.object = form.save()
        self.photo_requirement_formset.instance = self.object
        self.photo_requirement_formset.save()
        for order, requirement in enumerate(self.object.photo_requirements.order_by("pk")):
            if requirement.order != order:
                requirement.order = order
                requirement.save(update_fields=["order"])
        for uploaded_file in uploaded_files:
            SiteDocument.objects.create(site=self.object, file=uploaded_file)
        messages.success(self.request, "Объект сохранён.")
        return redirect(self.get_success_url())


class WorkPlanDetailView(LoginRequiredMixin, DetailView):
    model = WorkPlan
    template_name = "work/plan_detail.html"

    def get_queryset(self):
        return WorkPlan.objects.select_related("site", "worker").prefetch_related(
            "site__documents", "site__photo_requirements__category",
            "submissions__photos__category",
        )

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
        ctx["photo_slots"] = list(
            self.object.site.photo_requirements.select_related("category")
        )
        if self.request.user.is_staff:
            ctx["current_submission"] = WorkSubmission.objects.filter(
                plan__site_id=self.object.site_id
            ).select_related("plan__site", "plan__worker").order_by(
                "-created_at", "-pk"
            ).first()
        else:
            ctx["current_submission"] = self.object.submissions.order_by(
                "-created_at", "-pk"
            ).first()
        ctx["display_plan"] = (
            ctx["current_submission"].plan
            if self.request.user.is_staff and ctx["current_submission"]
            else self.object
        )
        history = WorkSubmission.objects.filter(plan__site_id=self.object.site_id)
        if not self.request.user.is_staff:
            history = history.filter(plan__worker__user_id=self.request.user.id)
        ctx["site_submission_history"] = history.select_related(
            "plan__site", "plan__worker"
        ).prefetch_related(
            "photos__category"
        ).order_by("-created_at", "-pk")
        if not self.request.user.is_staff and self.object.status != WorkPlan.Status.APPROVED:
            submission = ctx["current_submission"] or WorkSubmission(plan=self.object)
            ctx["photo_formset"] = kwargs.get("photo_formset") or work_photo_formset_for(
                self.object, submission,
            )
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_staff:
            action = request.POST.get("action")
            latest_submission = WorkSubmission.objects.filter(
                plan__site_id=self.object.site_id
            ).select_related("plan").order_by("-created_at", "-pk").first()
            review_plan = latest_submission.plan if latest_submission else self.object
            if action == "reopen" and review_plan.status == WorkPlan.Status.APPROVED:
                review_plan.status = WorkPlan.Status.SUBMITTED
                review_plan.review_comment = ""
                review_plan.reviewed_at = None
                review_plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                self._set_submission_status(latest_submission, WorkPlan.Status.SUBMITTED)
                messages.success(request, "Работа снова отправлена на проверку.")
            elif review_plan.status != WorkPlan.Status.SUBMITTED:
                messages.error(request, "Проверить можно только отправленный на проверку план.")
            elif action == "approve":
                review_plan.status = WorkPlan.Status.APPROVED
                review_plan.review_comment = ""
                review_plan.reviewed_at = timezone.now()
                review_plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                self._set_submission_status(latest_submission, WorkPlan.Status.APPROVED)
                messages.success(request, "Работа принята.")
            elif action == "revision":
                comment = request.POST.get("review_comment", "").strip()
                if not comment:
                    messages.error(request, "Напишите, что нужно исправить.")
                else:
                    review_plan.status = WorkPlan.Status.REVISION
                    review_plan.review_comment = comment
                    review_plan.reviewed_at = timezone.now()
                    review_plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                    self._set_submission_status(latest_submission, WorkPlan.Status.REVISION, comment)
                    messages.success(request, "Работа возвращена на доработку.")
            return redirect("plan_detail", pk=self.object.pk)

        if self.object.worker.user_id != request.user.id:
            return HttpResponseForbidden()
        if self.object.status not in (
            WorkPlan.Status.PLANNED,
            WorkPlan.Status.SUBMITTED,
            WorkPlan.Status.REVISION,
        ):
            messages.error(request, "Это задание уже принято и его нельзя изменить.")
            return redirect("plan_detail", pk=self.object.pk)
        submission = self.object.submissions.order_by("-created_at", "-pk").first()
        is_editing_submission = submission is not None
        if submission is None:
            submission = WorkSubmission(plan=self.object)
        formset = work_photo_formset_for(
            self.object, submission, data=request.POST, files=request.FILES,
        )
        if formset and formset.is_valid():
            previous_files = {
                photo.pk: photo.image.name
                for photo in submission.photos.all()
                if photo.pk and photo.image
            }
            with transaction.atomic():
                if not submission.pk:
                    submission.status = WorkPlan.Status.SUBMITTED
                    submission.save()
                formset.instance = submission
                formset.save()
                WorkSubmission.objects.filter(pk=submission.pk).update(
                    status=WorkPlan.Status.SUBMITTED,
                    created_at=timezone.now(),
                )
                self.object.status = WorkPlan.Status.SUBMITTED
                self.object.review_comment = ""
                self.object.reviewed_at = None
                self.object.save(update_fields=["status", "review_comment", "reviewed_at"])
            for photo in submission.photos.all():
                old_name = previous_files.get(photo.pk)
                if old_name and old_name != photo.image.name:
                    default_storage.delete(old_name)
            if is_editing_submission:
                messages.success(request, "Отчёт обновлён и отправлен хозяину на проверку.")
            else:
                messages.success(request, "Отчёт отправлен. Ожидайте одобрения хозяина.")
            return redirect("plan_detail", pk=self.object.pk)
        if formset is None:
            messages.error(request, "Для объекта пока не настроены обязательные фото. Обратитесь к хозяину.")
            return redirect("plan_detail", pk=self.object.pk)
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(
                photo_formset=formset, photo_formset_invalid=True,
            ))
        return self.render_to_response(self.get_context_data(photo_formset=formset))

    def _set_submission_status(self, submission, status, review_comment=None):
        if submission:
            submission.status = status
            update_fields = ["status"]
            if review_comment is not None:
                submission.review_comment = review_comment
                update_fields.append("review_comment")
            submission.save(update_fields=update_fields)


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
        qs = WorkPlan.objects.select_related("site").filter(
            worker=self.request.user.worker
        ).annotate(status_order=plan_status_order()).order_by(
            "-work_date", "status_order", "site__name", "pk"
        )
        today = timezone.localdate()
        date_value = self.request.GET.get("date")
        if date_value and parse_date(date_value):
            qs = qs.filter(work_date=parse_date(date_value))
        status = self.request.GET.get("status")
        if status in WorkPlan.Status.values:
            qs = qs.filter(status=status)
        history_mode = self.request.GET.get("history") == "1" or bool(date_value or status)
        ctx["history_mode"] = history_mode
        if history_mode:
            ctx["plans"] = qs
            ctx["date_groups"] = [
                (day, list(items)) for day, items in groupby(qs, key=lambda plan: plan.work_date)
            ]
        else:
            ctx["today_plans"] = qs.filter(work_date=today).exclude(
                status=WorkPlan.Status.APPROVED
            )
            future_plans = qs.filter(work_date__gt=today).exclude(
                status=WorkPlan.Status.APPROVED
            ).order_by("work_date", "status_order", "site__name", "pk")
            ctx["active_future_count"] = future_plans.count()
            completed_plans = qs.filter(
                status=WorkPlan.Status.APPROVED, work_date__lte=today,
            ).order_by("-work_date", "site__name", "pk")
            ctx["upcoming_groups"] = [
                (day, list(items)) for day, items in groupby(future_plans, key=lambda plan: plan.work_date)
            ]
            ctx["completed_groups"] = [
                (day, list(items)) for day, items in groupby(completed_plans, key=lambda plan: plan.work_date)
            ]
        ctx["selected_date"] = date_value or ""
        ctx["selected_status"] = status or ""
        ctx["statuses"] = WorkPlan.Status.choices
        ctx["today"] = today
        return ctx


# ---------- Объекты ----------

class SiteListView(StaffRequiredMixin, FilterView):
    model = Site
    filterset_class = SiteFilter
    template_name = "work/site_list.html"
    completed_only = False

    def get_queryset(self):
        latest_submission = WorkSubmission.objects.filter(
            plan_id=OuterRef("pk")
        ).order_by("-created_at", "-pk")
        latest_plan = WorkPlan.objects.filter(site_id=OuterRef("pk")).annotate(
            latest_activity=Coalesce(
                "reviewed_at",
                Subquery(latest_submission.values("created_at")[:1]),
                "created_at",
                output_field=DateTimeField(),
            )
        ).order_by("-latest_activity", "-work_date", "-created_at", "-pk")
        queryset = super().get_queryset().annotate(
            legacy_report_count=Count("reports", distinct=True),
            submission_count=Count("work_plans__submissions", distinct=True),
            latest_plan_status=Subquery(latest_plan.values("status")[:1]),
            latest_plan_date=Subquery(latest_plan.values("work_date")[:1]),
        ).annotate(
            state_order=Case(
                When(latest_plan_status__isnull=True, then=Value(0)),
                When(latest_plan_status=WorkPlan.Status.REVISION, then=Value(1)),
                When(latest_plan_status=WorkPlan.Status.PLANNED, then=Value(2)),
                When(latest_plan_status=WorkPlan.Status.SUBMITTED, then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            ),
        ).order_by("state_order", "name", "pk")
        if not self.completed_only:
            queryset = queryset.filter(is_completed=False)
        return queryset


class CompletedSiteListView(SiteListView):
    completed_only = True

    def get_queryset(self):
        return super().get_queryset().filter(is_completed=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["completed_only"] = True
        return ctx


class SiteRevertCompletionView(StaffRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        site = get_object_or_404(Site, pk=kwargs["pk"])
        if not site.is_completed:
            messages.error(request, "Объект уже находится в активном списке.")
        else:
            site.is_completed = False
            site.save(update_fields=["is_completed"])
            messages.success(request, "Объект возвращён в активный список. История отчётов сохранена.")
        return redirect("site_list")


class SiteCompleteView(StaffRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        site = get_object_or_404(Site, pk=kwargs["pk"])
        plans = site.work_plans.all()
        if site.is_completed:
            messages.info(request, "Объект уже завершён.")
        elif not plans.exists():
            messages.error(request, "Нельзя завершить объект без планов работ.")
        elif plans.exclude(status=WorkPlan.Status.APPROVED).exists():
            messages.error(request, "Сначала примите или обработайте все отчёты по планам этого объекта.")
        else:
            site.is_completed = True
            site.save(update_fields=["is_completed"])
            messages.success(request, "Объект завершён и перемещён в «Завершённые объекты».")
        return redirect("site_detail", pk=site.pk)


class SiteDetailView(StaffRequiredMixin, DetailView):
    model = Site
    template_name = "work/site_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plans = self.object.work_plans.all()
        ctx["can_complete"] = (
            plans.exists() and not plans.exclude(status=WorkPlan.Status.APPROVED).exists()
        )
        old_reports = self.object.reports.select_related("worker")
        submissions = WorkSubmission.objects.filter(plan__site=self.object).select_related(
            "plan__site", "plan__worker"
        ).prefetch_related("photos__category")
        entries = [_legacy_report_entry(report) for report in old_reports]
        entries.extend(_submission_report_entries(submissions))
        ctx["reports"] = sorted(entries, key=lambda report: report.created_at, reverse=True)
        ctx["report_total"] = sum(report.submission_count for report in entries)
        return ctx


class SiteCreateView(SiteFormProcessMixin, StaffRequiredMixin, CreateView):
    model = Site
    form_class = SiteForm
    template_name = "work/form.html"
    success_url = reverse_lazy("site_list")
    extra_context = {"title": "Новый объект", "back": "site_list"}


class SiteUpdateView(SiteFormProcessMixin, StaffRequiredMixin, UpdateView):
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

class WorkerListView(StaffRequiredMixin, ListView):
    model = Worker
    template_name = "work/worker_list.html"

    def get_queryset(self):
        return Worker.objects.order_by("name", "pk")


class WorkerDetailView(StaffRequiredMixin, DetailView):
    model = Worker
    template_name = "work/worker_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        worker = self.object
        today = timezone.localdate()
        now = timezone.now()
        try:
            year = int(self.request.GET.get("year", today.year))
            if year < 2000 or year > today.year + 1:
                year = today.year
        except (TypeError, ValueError):
            year = today.year
        try:
            month = int(self.request.GET.get("month", today.month))
            if month not in range(1, 13):
                month = today.month
        except (TypeError, ValueError):
            month = today.month

        month_start = timezone.make_aware(datetime(year, month, 1))
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        month_end = timezone.make_aware(datetime.combine(next_month, time.min))
        year_start = timezone.make_aware(datetime(year, 1, 1))
        next_year = timezone.make_aware(datetime(year + 1, 1, 1))
        day_start, day_end = _day_bounds(today)

        all_shifts = WorkShift.objects.filter(worker=worker, started_at__lt=now).order_by("started_at")
        month_shifts = all_shifts.filter(
            started_at__lt=month_end,
        ).filter(Q(ended_at__gt=month_start) | Q(ended_at__isnull=True))
        year_shifts = all_shifts.filter(
            started_at__lt=next_year,
        ).filter(Q(ended_at__gt=year_start) | Q(ended_at__isnull=True))
        current_shift = WorkShift.objects.filter(worker=worker, ended_at__isnull=True).order_by("-started_at").first()
        today_seconds = _shift_seconds(all_shifts, day_start, min(day_end, now))
        month_seconds = _shift_seconds(month_shifts, month_start, min(month_end, now))
        year_seconds = _shift_seconds(year_shifts, year_start, min(next_year, now))

        shift_rows = []
        for shift in month_shifts.order_by("-started_at"):
            end = min(shift.ended_at or now, month_end)
            start = max(shift.started_at, month_start)
            shift_rows.append({
                "shift": shift,
                "duration": _format_hours(int(max(0, (end - start).total_seconds()))),
            })

        month_options = [
            (1, "Январь"), (2, "Февраль"), (3, "Март"), (4, "Апрель"),
            (5, "Май"), (6, "Июнь"), (7, "Июль"), (8, "Август"),
            (9, "Сентябрь"), (10, "Октябрь"), (11, "Ноябрь"), (12, "Декабрь"),
        ]
        ctx.update({
            "selected_year": year,
            "selected_month": month,
            "selected_month_label": dict(month_options)[month],
            "year_options": range(min(year, today.year) - 4, max(year, today.year) + 1),
            "month_options": month_options,
            "today_hours": _format_hours(today_seconds),
            "month_hours": _format_hours(month_seconds),
            "year_hours": _format_hours(year_seconds),
            "current_shift": current_shift,
            "shift_over_eight_hours": bool(current_shift and now - current_shift.started_at >= timedelta(hours=8)),
            "shift_rows": shift_rows,
            "period_plans": WorkPlan.objects.filter(
                worker=worker, work_date__year=year, work_date__month=month,
            ).select_related("site").order_by("-work_date", "site__name", "pk"),
        })
        return ctx


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
        return qs.order_by("site__name", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        entries = [_legacy_report_entry(report) for report in ctx["object_list"]]
        filter_form = ctx["filter"].form
        filters = filter_form.cleaned_data if filter_form.is_valid() else {}
        submissions = WorkSubmission.objects.select_related("plan__site", "plan__worker").prefetch_related("photos__category")
        if filters.get("site_name"):
            submissions = submissions.filter(plan__site__name__icontains=filters["site_name"])
        if filters.get("site_number"):
            submissions = submissions.filter(plan__site__object_number__icontains=filters["site_number"])
        if filters.get("status"):
            submissions = submissions.filter(
                Q(status=filters["status"])
                | Q(status__isnull=True, plan__status=filters["status"])
            )
            entries = []
        date_range = filters.get("date")
        if date_range:
            if date_range.start:
                submissions = submissions.filter(created_at__date__gte=date_range.start)
            if date_range.stop:
                submissions = submissions.filter(created_at__date__lte=date_range.stop)
        entries.extend(_submission_report_entries(submissions))
        status_order = {
            WorkPlan.Status.SUBMITTED: 0,
            WorkPlan.Status.PLANNED: 1,
            WorkPlan.Status.REVISION: 2,
            WorkPlan.Status.APPROVED: 3,
        }
        entries.sort(key=lambda report: report.created_at, reverse=True)
        entries.sort(key=lambda report: status_order.get(report.status, 4))
        entries.sort(key=lambda report: report.site.name.casefold())
        entries.sort(
            key=lambda report: timezone.localtime(report.created_at).date(),
            reverse=True,
        )
        ctx["object_list"] = entries
        report_days = []
        for day, day_items in groupby(
            entries, key=lambda report: timezone.localtime(report.created_at).date()
        ):
            object_groups = [
                (site, list(site_reports))
                for site, site_reports in groupby(day_items, key=lambda report: report.site)
            ]
            report_days.append((day, object_groups, sum(len(items) for _, items in object_groups)))
        ctx["report_days"] = report_days
        return ctx


class ReportDetailView(StaffRequiredMixin, DetailView):
    queryset = Report.objects.select_related("site", "worker")
    template_name = "work/report_detail.html"


class WorkSubmissionDetailView(StaffRequiredMixin, DetailView):
    model = WorkSubmission
    template_name = "work/submission_detail.html"

    def get_queryset(self):
        return WorkSubmission.objects.select_related("plan__site", "plan__worker").prefetch_related("photos__category")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["submission_status"] = self.object.status
        ctx["submission_status_label"] = dict(WorkPlan.Status.choices).get(
            self.object.status, "Статус не сохранён"
        )
        return ctx


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
        submission_status = latest.status or plan.status
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
            status=submission_status,
            status_label={
                WorkPlan.Status.PLANNED: "В обработке",
                WorkPlan.Status.SUBMITTED: "Ожидает рассмотрения",
                WorkPlan.Status.APPROVED: "Принят",
                WorkPlan.Status.REVISION: "Не принят",
            }.get(submission_status, ""),
            detail_url=reverse_lazy("submission_detail", kwargs={"pk": latest.pk}),
        ))
    return entries
