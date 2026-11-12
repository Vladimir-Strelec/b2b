from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.contrib.auth import get_user_model
from .models import (
    Report, Site, SitePhotoRequirement, Worker, WorkPlan, WorkSubmission,
    WorkPhoto, PhotoCategory,
)


User = get_user_model()


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["site", "photo", "description"]

    def __init__(self, *args, worker=None, **kwargs):
        super().__init__(*args, **kwargs)
        if worker:
            # Доступны объекты, назначенные работнику хотя бы в одном плане.
            self.fields["site"].queryset = Site.objects.filter(
                work_plans__worker=worker
            ).distinct()


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["object_number", "name", "address", "site_type"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["object_number"].required = True
        self.fields["object_number"].widget.attrs.update({
            "required": "required",
            "placeholder": "Введите номер объекта",
        })
        self.fields["name"].error_messages["required"] = "Укажите название объекта."
        self.fields["object_number"].error_messages["required"] = "Укажите номер объекта."
        self.fields["address"].error_messages["required"] = "Укажите адрес объекта."
        self.fields["site_type"].choices = [("", "Выберите тип объекта")] + list(Site.SiteType.choices)
        self.fields["site_type"].required = True
        self.fields["site_type"].error_messages["required"] = "Выберите тип объекта A, B, C или D."
        if not self.instance.pk and not self.is_bound:
            self.fields["site_type"].initial = ""

    def clean_object_number(self):
        object_number = self.cleaned_data["object_number"].strip()
        if not object_number:
            raise forms.ValidationError("Введите номер объекта, чтобы сохранить объект.")
        return object_number


class SitePhotoRequirementForm(forms.ModelForm):
    class Meta:
        model = SitePhotoRequirement
        fields = ["category"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = PhotoCategory.objects.filter(is_active=True)
        self.fields["category"].empty_label = "Выберите категорию фото"
        self.fields["category"].error_messages["required"] = "Выберите категорию этого фото."


SitePhotoRequirementFormSet = inlineformset_factory(
    Site, SitePhotoRequirement, form=SitePhotoRequirementForm,
    extra=0, min_num=1, validate_min=True, max_num=20, validate_max=True,
    can_delete=True,
)


class WorkerForm(forms.ModelForm):
    username = forms.CharField(label="Логин для входа", required=False)
    password = forms.CharField(label="Пароль", required=False, widget=forms.PasswordInput)
    class Meta:
        model = Worker
        fields = ["name", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        return worker


class SiteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} · № {obj.object_number} · {obj.address}"


class WorkPlanForm(forms.ModelForm):
    site = SiteChoiceField(queryset=Site.objects.order_by("name"), label="Объект")

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


class WorkPhotoForm(forms.ModelForm):
    class Meta:
        model = WorkPhoto
        fields = ["image", "photo_slot", "description"]
        widgets = {
            "image": forms.FileInput(attrs={"class": "photo-file-input", "accept": "image/*"}),
            "photo_slot": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"rows": 2, "class": "photo-description-input", "placeholder": "Кратко опишите, что сделано"}),
        }

    def __init__(self, *args, slot=None, site_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.slot = slot
        self.fields["photo_slot"].queryset = SitePhotoRequirement.objects.filter(
            site_id=site_id,
        ).select_related("category")
        self.fields["photo_slot"].required = True
        self.fields["description"].required = True
        self.fields["description"].error_messages["required"] = "Опишите выполненную работу на этом фото."
        if slot:
            self.initial["photo_slot"] = slot.pk
        self.fields["image"].error_messages["required"] = "Добавьте фотографию."


class RequiredSlotInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, slots=None, **kwargs):
        self.required_slots = list(slots or [])
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if index is not None and index < len(self.required_slots):
            kwargs["slot"] = self.required_slots[index]
            kwargs["site_id"] = self.instance.plan.site_id
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if len(self.forms) != len(self.required_slots):
            raise forms.ValidationError(
                "Добавьте по одной фотографии в каждое обязательное поле объекта."
            )
        for form, expected_slot in zip(self.forms, self.required_slots):
            cleaned = form.cleaned_data
            selected_slot = cleaned.get("photo_slot")
            image = cleaned.get("image") or form.instance.image
            if not image or not selected_slot or selected_slot.pk != expected_slot.pk:
                raise forms.ValidationError(
                    "Добавьте или сохраните фотографию в каждом обязательном поле объекта."
                )


WorkPhotoFormSet = inlineformset_factory(
    WorkSubmission, WorkPhoto, form=WorkPhotoForm,
    formset=RequiredSlotInlineFormSet, extra=0, can_delete=False,
)
