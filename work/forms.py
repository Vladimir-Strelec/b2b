from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth import get_user_model
from .models import Report, Site, Worker, WorkPlan, WorkSubmission, WorkPhoto, PhotoCategory


User = get_user_model()


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["site", "photo", "description"]

    def __init__(self, *args, worker=None, **kwargs):
        super().__init__(*args, **kwargs)
        if worker:
            # Работник видит только свои объекты
            self.fields["site"].queryset = worker.sites.all()


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["name", "address", "site_type", "workers"]
        widgets = {"workers": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].error_messages["required"] = "Укажите название объекта."
        self.fields["address"].error_messages["required"] = "Укажите адрес объекта."
        self.fields["site_type"].choices = [("", "Выберите тип объекта")] + list(Site.SiteType.choices)
        self.fields["site_type"].required = True
        self.fields["site_type"].error_messages["required"] = "Выберите тип объекта A, B, C или D."
        self.fields["workers"].required = True
        self.fields["workers"].error_messages["required"] = "Выберите хотя бы одного работника."
        if not self.instance.pk and not self.is_bound:
            self.fields["site_type"].initial = ""


class WorkerForm(forms.ModelForm):
    username = forms.CharField(label="Логин для входа", required=False)
    password = forms.CharField(label="Пароль", required=False, widget=forms.PasswordInput)
    sites = forms.ModelMultipleChoiceField(
        queryset=Site.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple, label="Объекты",
    )

    class Meta:
        model = Worker
        fields = ["name", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["sites"].initial = self.instance.sites.all()
        if self.instance.user_id:  # у работника уже есть вход
            del self.fields["username"]
            del self.fields["password"]

    def clean(self):
        cleaned = super().clean()
        if not self.instance.user_id:
            username = cleaned.get("username")
            if not (username and cleaned.get("password")):
                raise forms.ValidationError("Укажите логин и пароль для работника.")
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError("Такой логин уже занят.")
        return cleaned

    def save(self, commit=True):
        worker = super().save(commit=False)
        if not worker.user_id:
            worker.user = User.objects.create_user(
                username=self.cleaned_data["username"],
                password=self.cleaned_data["password"],
            )
        worker.save()
        worker.sites.set(self.cleaned_data["sites"])
        return worker


class WorkPlanForm(forms.ModelForm):
    site_type = forms.ChoiceField(
        label="Категория объекта",
        choices=[("", "Выберите тип объекта")] + list(Site.SiteType.choices),
        error_messages={"required": "Выберите тип объекта A, B, C или D."},
    )

    class Meta:
        model = WorkPlan
        fields = ["work_date", "site", "worker", "description"]
        widgets = {"work_date": forms.DateInput(attrs={"type": "date"}), "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Краткое описание к документации"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].label = "Краткое описание к документации"
        self.fields["worker"].queryset = Worker.objects.select_related("user").filter(user__isnull=False).order_by("name")
        self.fields["work_date"].error_messages["required"] = "Укажите дату плана."
        self.fields["site"].error_messages["required"] = "Выберите объект."
        self.fields["worker"].error_messages["required"] = "Выберите работника."
        self.fields["description"].error_messages["required"] = "Добавьте краткое описание к документации."
        if self.instance.pk:
            self.fields["site_type"].initial = self.instance.site.site_type
        elif not self.is_bound:
            self.fields["site_type"].initial = ""

    def save(self, commit=True):
        plan = super().save(commit=False)
        site = self.cleaned_data["site"]
        site.site_type = self.cleaned_data["site_type"]
        site.save(update_fields=["site_type"])
        if commit:
            plan.save()
            self.save_m2m()
        return plan


class WorkPhotoForm(forms.ModelForm):
    class Meta:
        model = WorkPhoto
        fields = ["image", "category", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = PhotoCategory.objects.filter(is_active=True)
        self.fields["image"].error_messages["required"] = "Добавьте фотографию."
        self.fields["category"].error_messages["required"] = "Выберите категорию фотографии."
        self.fields["description"].error_messages["required"] = "Добавьте описание выполненной работы."


WorkPhotoFormSet = inlineformset_factory(
    WorkSubmission, WorkPhoto, form=WorkPhotoForm, extra=1, can_delete=False,
)
