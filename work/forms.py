from django import forms
from .models import Report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["site", "photo", "description"]

    def __init__(self, *args, worker=None, **kwargs):
        super().__init__(*args, **kwargs)
        if worker:
            # Работник видит только свои объекты
            self.fields["site"].queryset = worker.sites.all()