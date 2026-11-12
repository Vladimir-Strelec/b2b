import django_filters
from django.forms import DateInput, TextInput
from django.db.models import Q
from .models import Worker, Site, Report, WorkPlan
from django_filters.widgets import RangeWidget
from django_filters import ChoiceFilter


class SiteFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(
        field_name="latest_plan_date", label="Дата",
        widget=DateInput(attrs={"type": "date"}),
    )
    site_search = django_filters.CharFilter(
        label="Объект",
        method="filter_site_search",
        widget=TextInput(attrs={
            "type": "search",
            "placeholder": "Введите название, номер или адрес объекта",
            "autocomplete": "off",
        }),
    )
    site_type = django_filters.ChoiceFilter(
        choices=Site.SiteType.choices, label="Тип объекта"
    )
    state = ChoiceFilter(
        choices=(
            ("none", "Без плана"),
            ("revision", "Отказано"),
            ("submitted", "На проверке"),
            ("planned", "Запланирован"),
            ("approved", "Отчёты приняты"),
            ("completed", "Объект завершён"),
        ),
        label="Состояние",
        method="filter_state",
    )

    def filter_state(self, queryset, name, value):
        if value == "none":
            return queryset.filter(latest_plan_status__isnull=True, is_completed=False)
        if value == "completed":
            return queryset.filter(is_completed=True)
        if value == "approved":
            return queryset.filter(latest_plan_status=value, is_completed=False)
        if value in {"planned", "submitted", "revision"}:
            return queryset.filter(latest_plan_status=value, is_completed=False)
        return queryset

    def filter_site_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(object_number__icontains=value)
            | Q(address__icontains=value)
        )

    class Meta:
        model = Site
        fields = []


class WorkerFilter(django_filters.FilterSet):
    sites = django_filters.ModelChoiceFilter(
        queryset=Site.objects.all(), label="Объект"
    )

    class Meta:
        model = Worker
        fields = ["sites"]


class ReportFilter(django_filters.FilterSet):
    site_search = django_filters.CharFilter(
        label="Объект",
        method="filter_site_search",
        widget=TextInput(attrs={
            "type": "search",
            "placeholder": "Введите название, номер или адрес объекта",
            "autocomplete": "off",
        }),
    )
    status = django_filters.ChoiceFilter(
        choices=(
            (WorkPlan.Status.PLANNED, "В обработке"),
            (WorkPlan.Status.SUBMITTED, "Ожидает рассмотрения"),
            (WorkPlan.Status.REVISION, "Не принят"),
            (WorkPlan.Status.APPROVED, "Принят"),
        ),
        label="Статус",
        method="filter_status",
    )
    date = django_filters.DateFromToRangeFilter(
        field_name="created_at__date",
        label="Дата (от и до)",
        widget=RangeWidget(attrs={"type": "date"}),
    )

    class Meta:
        model = Report
        fields = ["date"]

    def filter_status(self, queryset, name, value):
        # Status is stored on work plans and submissions, not legacy Report rows.
        return queryset

    def filter_site_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(site__name__icontains=value)
            | Q(site__object_number__icontains=value)
            | Q(site__address__icontains=value)
        )
