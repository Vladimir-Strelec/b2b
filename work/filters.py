import django_filters
from .models import Worker, Site, Report
from django_filters.widgets import RangeWidget


class SiteFilter(django_filters.FilterSet):
    workers = django_filters.ModelChoiceFilter(
        queryset=Worker.objects.all(), label="Работник"
    )

    class Meta:
        model = Site
        fields = ["workers"]


class WorkerFilter(django_filters.FilterSet):
    sites = django_filters.ModelChoiceFilter(
        queryset=Site.objects.all(), label="Объект"
    )

    class Meta:
        model = Worker
        fields = ["sites"]


class ReportFilter(django_filters.FilterSet):
    site = django_filters.ModelChoiceFilter(
        queryset=Site.objects.all(), label="Объект"
    )
    worker = django_filters.ModelChoiceFilter(
        queryset=Worker.objects.all(), label="Работник"
    )
    date = django_filters.DateFromToRangeFilter(
        field_name="created_at__date",
        label="Дата (от и до)",
        widget=RangeWidget(attrs={"type": "date"}),
    )

    class Meta:
        model = Report
        fields = ["site", "worker", "date"]