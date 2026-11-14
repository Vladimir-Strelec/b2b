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
    WorkPhoto, WorkShift, WorkSubmission, WorkSubmissionOfficeNote,
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
            selected_from = parse_date(self.request.GET.get("date_from", ""))
            selected_to = parse_date(self.request.GET.get("date_to", ""))
            if selected_from is None and selected_to is None:
                selected_from = selected_to = today
            elif selected_from is None:
                selected_from = selected_to
            elif selected_to is None:
                selected_to = selected_from
            if selected_from > selected_to:
                selected_from, selected_to = selected_to, selected_from
            selected_day_start, _ = _day_bounds(selected_from)
            _, selected_day_end = _day_bounds(selected_to)
            shift_map = {}
            for shift in WorkShift.objects.filter(
                started_at__lt=now,
            ).filter(
                Q(ended_at__gt=min(month_start, selected_day_start)) | Q(ended_at__isnull=True)
            ).select_related("worker").order_by("started_at"):
                shift_map.setdefault(shift.worker_id, []).append(shift)
            worker_rows = []
            for worker in Worker.objects.order_by("name"):
                shifts = shift_map.get(worker.pk, [])
                current_shift = next((shift for shift in reversed(shifts) if shift.ended_at is None), None)
                today_seconds = _shift_seconds(shifts, day_start, min(day_end, now))
                month_seconds = _shift_seconds(shifts, month_start, now)
                selected_period_shifts = [
                    shift for shift in shifts
                    if shift.started_at < selected_day_end
                    and (shift.ended_at is None or shift.ended_at > selected_day_start)
                ]
                worker_rows.append({
                    "worker": worker,
                    "current_shift": current_shift,
                    "over_eight_hours": bool(current_shift and now - current_shift.started_at >= timedelta(hours=8)),
                    "today_hours": _format_hours(today_seconds),
                    "month_hours": _format_hours(month_seconds),
                    "selected_period_shifts": selected_period_shifts,
                })
            ctx["worker_time_rows"] = worker_rows
            ctx["date_from"] = selected_from.isoformat()
            ctx["date_to"] = selected_to.isoformat() if selected_to != selected_from else ""
            ctx["show_shift_dates"] = selected_from != selected_to
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
        site_search = self.request.GET.get("site_search", "").strip()
        if site_search:
            qs = qs.filter(
                Q(site__object_number__icontains=site_search)
                | Q(site__name__icontains=site_search)
                | Q(site__address__icontains=site_search)
            )
        return qs.annotate(status_order=plan_status_order()).order_by(
            "-work_date", "status_order", "site__name", "pk"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["site_options"] = list(
            Site.objects.order_by("name").values("id", "object_number", "name", "address")
        )
        ctx["statuses"] = WorkPlan.Status.choices
        ctx["site_types"] = Site.SiteType.choices
        today = timezone.localdate()
        filter_keys = ("date", "site", "site_search", "site_type", "status")
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
            ).exclude(status=WorkPlan.Status.APPROVED).order_by(
                "work_date", "status_order", "site__name", "pk"
            )
            ctx["upcoming_count"] = upcoming.count()
            completed = plans.filter(
                work_date__lt=today,
            ).order_by("-work_date", "site__name", "pk")
            ctx["upcoming_groups"] = [
                (day, list(items)) for day, items in groupby(upcoming, key=lambda plan: plan.work_date)
            ]
            ctx["completed_groups"] = []
            for day, items in groupby(completed, key=lambda plan: plan.work_date):
                day_plans = list(items)
                unfinished_count = sum(
                    plan.status != WorkPlan.Status.APPROVED for plan in day_plans
                )
                ctx["completed_groups"].append((day, day_plans, unfinished_count))
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


def validate_site_documents(files, remaining, required=False):
    if required and not files:
        return "При создании объекта прикрепите хотя бы один файл PDF или Excel."
    if len(files) > remaining:
        return f"К объекту можно прикрепить не более 20 файлов; свободно мест: {remaining}."
    signatures = {
        ".pdf": (b"%PDF-", "PDF"),
        ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "Excel"),
        ".xlsx": (b"PK\x03\x04", "Excel"),
    }
    for uploaded in files:
        extension = "." + uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
        signature = signatures.get(extension)
        if not signature:
            return f"Файл «{uploaded.name}» должен быть формата PDF, XLS или XLSX."
        expected, file_type = signature
        if uploaded.read(len(expected)) != expected:
            return f"Файл «{uploaded.name}» не распознан как {file_type}."
        uploaded.seek(0)
    return ""


def work_photo_formset_for(plan, submission, data=None, files=None, initial=None):
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
        # RequiredSlotInlineFormSet validates every required slot itself. The
        # default min validator counts only changed extras and rejects a valid
        # correction that reuses unchanged photos from the previous attempt.
        validate_min=False,
        max_num=len(slots),
        validate_max=True,
        can_delete=False,
    )
    return formset_class(
        data=data,
        files=files,
        instance=submission,
        initial=initial,
        prefix="photos",
        slots=slots,
    )


def resubmission_photo_initial(plan, previous_submission):
    """Carry forward the last attempt's photos as editable defaults."""
    if previous_submission is None:
        return None
    slots = list(plan.site.photo_requirements.select_related("category"))
    photos = list(previous_submission.photos.select_related("category", "photo_slot__category"))
    used_photo_ids = set()
    initial = []
    for slot in slots:
        photo = next((item for item in photos if item.photo_slot_id == slot.pk), None)
        if photo is None:
            photo = next(
                (item for item in photos if item.pk not in used_photo_ids and item.category_id == slot.category_id),
                None,
            )
        row = {"photo_slot": slot.pk}
        if photo:
            used_photo_ids.add(photo.pk)
            row.update(image=photo.image, description=photo.description)
        initial.append(row)
    return initial


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
        error = validate_site_documents(
            uploaded_files,
            20 - current_count,
            required=not (self.object and self.object.pk) and current_count == 0,
        )
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
        ctx["future_locked"] = (
            not self.request.user.is_staff
            and self.object.work_date > timezone.localdate()
        )
        ctx["photo_slots"] = list(
            self.object.site.photo_requirements.select_related("category")
        )
        if self.request.user.is_staff:
            ctx["current_submission"] = WorkSubmission.objects.filter(
                plan_id=self.object.pk
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
        if (
            not self.request.user.is_staff
            and not ctx["future_locked"]
            and self.object.status != WorkPlan.Status.APPROVED
        ):
            ctx["resubmission_mode"] = (
                self.object.status in (WorkPlan.Status.REVISION, WorkPlan.Status.SUBMITTED)
                and ctx["current_submission"] is not None
            )
            if ctx["resubmission_mode"]:
                submission = WorkSubmission(plan=self.object)
                initial = resubmission_photo_initial(self.object, ctx["current_submission"])
            else:
                submission = ctx["current_submission"] or WorkSubmission(plan=self.object)
                initial = None
            ctx["photo_formset"] = kwargs.get("photo_formset") or work_photo_formset_for(
                self.object, submission, initial=initial,
            )
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user.is_staff:
            messages.info(request, "Рассмотрение отчётов находится в разделе «Отчёты».")
            return redirect("plan_detail", pk=self.object.pk)

        if self.object.worker.user_id != request.user.id:
            return HttpResponseForbidden()
        if self.object.work_date > timezone.localdate():
            messages.error(
                request,
                f"Это задание можно выполнить не раньше {self.object.work_date:%d.%m.%Y}.",
            )
            return redirect("plan_detail", pk=self.object.pk)
        if self.object.status not in (
            WorkPlan.Status.PLANNED,
            WorkPlan.Status.SUBMITTED,
            WorkPlan.Status.REVISION,
        ):
            messages.error(request, "Это задание уже принято и его нельзя изменить.")
            return redirect("plan_detail", pk=self.object.pk)
        previous_submission = self.object.submissions.order_by("-created_at", "-pk").first()
        is_resubmission = (
            previous_submission is not None
            and self.object.status in (WorkPlan.Status.REVISION, WorkPlan.Status.SUBMITTED)
        )
        if is_resubmission:
            submission = WorkSubmission(plan=self.object)
            initial = resubmission_photo_initial(self.object, previous_submission)
        else:
            submission = previous_submission
            initial = None
        is_editing_submission = submission is not None and submission.pk is not None
        if submission is None:
            submission = WorkSubmission(plan=self.object)
        formset = work_photo_formset_for(
            self.object, submission, data=request.POST, files=request.FILES, initial=initial,
        )
        if formset and formset.is_valid():
            # A first-time submission is unsaved, so its reverse manager cannot
            # be queried until it has a primary key. Existing submissions can
            # still be inspected to remove replaced images after the update.
            previous_files = {}
            if submission.pk:
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
            if is_resubmission:
                messages.success(request, "Новая версия отчёта отправлена. Предыдущая версия и ответы шефа сохранены в истории.")
            elif is_editing_submission:
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
            work_plan_count=Count("work_plans", distinct=True),
            legacy_report_count=Count("reports", distinct=True),
            submission_count=Count("work_plans__submissions", distinct=True),
            planned_plan_count=Count(
                "work_plans", filter=Q(work_plans__status=WorkPlan.Status.PLANNED), distinct=True,
            ),
            submitted_plan_count=Count(
                "work_plans", filter=Q(work_plans__status=WorkPlan.Status.SUBMITTED), distinct=True,
            ),
            revision_plan_count=Count(
                "work_plans", filter=Q(work_plans__status=WorkPlan.Status.REVISION), distinct=True,
            ),
            approved_plan_count=Count(
                "work_plans", filter=Q(work_plans__status=WorkPlan.Status.APPROVED), distinct=True,
            ),
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
        ).order_by("is_completed", "state_order", "name", "pk")
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
        plans = self.object.work_plans.select_related("worker", "created_by").prefetch_related(
            "documents", "submissions__photos__category"
        ).order_by("-work_date", "worker__name", "pk")
        ctx["plans"] = plans
        for plan in plans:
            plan.submission_history = list(plan.submissions.all())
            for submission in plan.submission_history:
                submission.effective_status = submission.status or plan.status
                submission.effective_status_label = dict(WorkPlan.Status.choices).get(
                    submission.effective_status, "Статус не сохранён"
                )
                submission.photo_list = list(submission.photos.all())
        ctx["site_workers"] = Worker.objects.filter(
            Q(sites=self.object) | Q(work_plans__site=self.object)
        ).annotate(
            site_plan_count=Count(
                "work_plans", filter=Q(work_plans__site=self.object), distinct=True,
            )
        ).distinct().select_related("user").order_by("name", "pk")
        ctx["can_complete"] = (
            plans.exists() and not plans.exclude(status=WorkPlan.Status.APPROVED).exists()
        )
        ctx["photo_requirements"] = self.object.photo_requirements.select_related("category").all()
        for requirement in ctx["photo_requirements"]:
            latest_photo = requirement.photos.filter(
                submission__plan__site=self.object
            ).select_related("submission__plan").order_by(
                "-submission__created_at", "-pk"
            ).first()
            if latest_photo is None:
                requirement.progress_status = "missing"
                requirement.progress_label = "Работник ещё не добавил фото"
                continue

            status = latest_photo.submission.status or latest_photo.submission.plan.status
            if status == WorkPlan.Status.APPROVED:
                requirement.progress_status = "approved"
                requirement.progress_label = "✓ Фото принято"
            elif status == WorkPlan.Status.SUBMITTED:
                requirement.progress_status = "submitted"
                requirement.progress_label = "Фото ожидает проверки хозяина"
            elif status == WorkPlan.Status.REVISION:
                requirement.progress_status = "revision"
                requirement.progress_label = "Отклонено — нужна доработка"
            else:
                requirement.progress_status = "missing"
                requirement.progress_label = "Работнику необходимо добавить фото"
        old_reports = self.object.reports.select_related("worker")
        submissions = WorkSubmission.objects.filter(plan__site=self.object).select_related(
            "plan__site", "plan__worker"
        ).prefetch_related("photos__category")
        entries = [_legacy_report_entry(report) for report in old_reports]
        entries.extend(_submission_report_entries(submissions))
        ctx["reports"] = sorted(entries, key=lambda report: report.created_at, reverse=True)
        ctx["legacy_reports"] = [report for report in ctx["reports"] if report.status is None]
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
        "warning": "Вместе с объектом удалятся его планы, отправленные отчёты и документы.",
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

        date_from_value = parse_date(self.request.GET.get("date_from", ""))
        date_to_value = parse_date(self.request.GET.get("date_to", ""))
        selected_shift_range = date_from_value is not None or date_to_value is not None
        if selected_shift_range:
            date_from = date_from_value or date_to_value
            date_to = date_to_value or date_from_value
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            range_start, _ = _day_bounds(date_from)
            _, range_end = _day_bounds(date_to)

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
        if selected_shift_range:
            shifts_for_table = all_shifts.filter(
                started_at__lt=range_end,
            ).filter(Q(ended_at__gt=range_start) | Q(ended_at__isnull=True))
            row_start, row_end = range_start, range_end
        else:
            shifts_for_table = month_shifts
            row_start, row_end = month_start, month_end
        for shift in shifts_for_table.order_by("-started_at"):
            end = min(shift.ended_at or now, row_end, now)
            start = max(shift.started_at, row_start)
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
            "date_from": date_from.isoformat() if selected_shift_range else "",
            "date_to": date_to.isoformat() if selected_shift_range else "",
            "selected_shift_range": selected_shift_range,
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
        "warning": "Вместе с работником удалятся его планы, смены, отчёты и учётная запись для входа.",
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
        if filters.get("site_search"):
            search = filters["site_search"]
            submissions = submissions.filter(
                Q(plan__site__name__icontains=search)
                | Q(plan__site__object_number__icontains=search)
                | Q(plan__site__address__icontains=search)
            )
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
        ctx["site_options"] = list(
            Site.objects.order_by("name").values("id", "object_number", "name", "address")
        )
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
        return WorkSubmission.objects.select_related("plan__site", "plan__worker").prefetch_related(
            "photos__category", "office_notes",
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["submission_status"] = self.object.status or self.object.plan.status
        ctx["latest_submission_id"] = WorkSubmission.objects.filter(
            plan_id=self.object.plan_id
        ).order_by("-created_at", "-pk").values_list("pk", flat=True).first()
        ctx["is_latest_submission"] = ctx["latest_submission_id"] == self.object.pk
        if not ctx["is_latest_submission"] and self.object.status == WorkPlan.Status.SUBMITTED:
            ctx["submission_status_label"] = "Заменён новой версией"
        else:
            ctx["submission_status_label"] = dict(WorkPlan.Status.choices).get(
                ctx["submission_status"], "Статус не сохранён"
            )
        ctx["office_notes"] = self.object.office_notes.all()
        ctx["submission_history"] = WorkSubmission.objects.filter(
            plan_id=self.object.plan_id
        ).select_related("plan__worker").prefetch_related(
            "photos__category", "office_notes",
        ).order_by("created_at", "pk")
        photos = list(self.object.photos.select_related("category", "photo_slot__category"))
        requirements = list(self.object.plan.site.photo_requirements.select_related("category"))
        grouped_photos = []
        used_photo_ids = set()
        for requirement in requirements:
            attached = next(
                (photo for photo in photos if photo.photo_slot_id == requirement.pk),
                None,
            )
            if attached is None:
                attached = next(
                    (
                        photo for photo in photos
                        if photo.pk not in used_photo_ids
                        and photo.category_id == requirement.category_id
                    ),
                    None,
                )
            if attached:
                used_photo_ids.add(attached.pk)
            grouped_photos.append({"requirement": requirement, "photo": attached})
        ctx["report_photo_groups"] = grouped_photos
        ctx["additional_report_photos"] = [
            photo for photo in photos if photo.pk not in used_photo_ids
        ]
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        action = request.POST.get("action")
        comment = request.POST.get("review_comment", "").strip()
        office_note = request.POST.get("office_note", "").strip()
        now = timezone.now()

        if action == "office_note":
            if self.object.status != WorkPlan.Status.REVISION:
                messages.error(request, "Дополнение Office можно добавить к отклонённому отчёту.")
            elif not office_note:
                messages.error(request, "Введите текст дополнения Office.")
            else:
                WorkSubmissionOfficeNote.objects.create(
                    submission=self.object, text=office_note,
                )
                messages.success(request, "Дополнение Office добавлено.")
            return redirect("submission_detail", pk=self.object.pk)

        with transaction.atomic():
            plan = WorkPlan.objects.select_for_update().get(pk=self.object.plan_id)
            latest_submission = WorkSubmission.objects.filter(
                plan_id=plan.pk
            ).order_by("-created_at", "-pk").first()

            if latest_submission is None or latest_submission.pk != self.object.pk:
                messages.error(request, "Рассматривать можно только последнюю отправку. Откройте актуальный отчёт.")
            elif action == "approve" and plan.status == WorkPlan.Status.SUBMITTED:
                plan.status = WorkPlan.Status.APPROVED
                plan.review_comment = ""
                plan.reviewed_at = now
                plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                latest_submission.status = WorkPlan.Status.APPROVED
                latest_submission.review_comment = ""
                latest_submission.save(update_fields=["status", "review_comment"])
                messages.success(request, "Отчёт одобрен.")
            elif action == "revision" and plan.status == WorkPlan.Status.SUBMITTED:
                if not comment:
                    messages.error(request, "Добавьте текст с причиной отклонения отчёта.")
                else:
                    plan.status = WorkPlan.Status.REVISION
                    plan.review_comment = comment
                    plan.reviewed_at = now
                    plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                    latest_submission.status = WorkPlan.Status.REVISION
                    latest_submission.review_comment = comment
                    latest_submission.save(update_fields=["status", "review_comment"])
                    messages.success(request, "Отчёт отклонён и отправлен на доработку.")
            elif action == "reopen" and plan.status == WorkPlan.Status.APPROVED:
                plan.status = WorkPlan.Status.SUBMITTED
                plan.review_comment = ""
                plan.reviewed_at = None
                plan.save(update_fields=["status", "review_comment", "reviewed_at"])
                latest_submission.status = WorkPlan.Status.SUBMITTED
                latest_submission.review_comment = ""
                latest_submission.save(update_fields=["status", "review_comment"])
                messages.success(request, "Отчёт снова ожидает рассмотрения.")
            else:
                messages.error(request, "Это действие недоступно для текущего статуса отчёта.")

        return redirect("submission_detail", pk=self.object.pk)


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
