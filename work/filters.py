import django_filters
from django.forms import DateInput
from .models import Worker, Site, Report, WorkPlan
from django_filters.widgets import RangeWidget
from django_filters import ChoiceFilter


class SiteFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(
        field_name="latest_plan_date", label="Дата",
        widget=DateInput(attrs={"type": "date"}),
    )
    object_number = django_filters.CharFilter(
        field_name="object_number", lookup_expr="icontains", label="Номер объекта"
    )
    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label="Объект"
    )
    address = django_filters.CharFilter(
        field_name="address", lookup_expr="icontains", label="Адрес объекта"
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
            ("approved", "Завершён"),
        ),
        label="Состояние",
        method="filter_state",
    )

    def filter_state(self, queryset, name, value):
        if value == "none":
            return queryset.filter(latest_plan_status__isnull=True)
        if value in {"planned", "submitted", "revision", "approved"}:
            return queryset.filter(latest_plan_status=value)
        return queryset

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
    site_name = django_filters.CharFilter(
        field_name="site__name", lookup_expr="icontains", label="Название объекта"
    )
    site_number = django_filters.CharFilter(
        field_name="site__object_number", lookup_expr="icontains", label="Номер объекта"
    )
    status = django_filters.ChoiceFilter(
        choices=(
            (WorkPlan.Status.PLANNED, "В обработке"),
            (WorkPlan.Status.SUBMITTED, "Ожидает рассмотрения"),
            (WorkPlan.Status.REVISION, "Не принят"),
            (WorkPlan.Status.APPROVED, "Закрыт"),
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
