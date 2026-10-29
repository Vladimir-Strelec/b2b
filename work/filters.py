import django_filters
from .models import Worker, Site


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