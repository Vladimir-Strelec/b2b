from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from .models import (
    Report, Site, SitePhotoRequirement, Worker, WorkPlan, WorkSubmission,
    WorkPhoto, PhotoCategory, PhotoCategoryPhoto,
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
        fields = ["object_number", "name", "address", "category", "requires_work_permit", "has_work_permit", "permit_valid_from", "permit_valid_until"]
        widgets = {
            "permit_valid_from": forms.DateInput(attrs={"type": "date"}),
            "permit_valid_until": forms.DateInput(attrs={"type": "date"}),
        }

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
        self.fields["name"].widget.attrs["required"] = "required"
        self.fields["address"].widget.attrs["required"] = "required"
        self.fields["category"].queryset = PhotoCategory.objects.filter(is_active=True)
        if self.instance.pk and self.instance.category_id:
            self.fields["category"].queryset = PhotoCategory.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.category_id)
            )
        self.fields["category"].empty_label = "Выберите тип объекта"
        self.fields["category"].label = "Тип объекта"
        self.fields["category"].required = True
        self.fields["category"].help_text = "Выберите тип из созданных категорий объекта."
        self.fields["requires_work_permit"].label = "Для работ по объекту требуется VAO"
        self.fields["requires_work_permit"].help_text = "План можно назначить после получения VAO и только в срок его действия."
        self.fields["has_work_permit"].help_text = "Отметьте, когда VAO получено; затем укажите даты его действия."
        self.fields["permit_valid_from"].required = False
        self.fields["permit_valid_until"].required = False

    def clean_object_number(self):
        object_number = self.cleaned_data["object_number"].strip()
        if not object_number:
            raise forms.ValidationError("Введите номер объекта, чтобы сохранить объект.")
        return object_number

    def clean_address(self):
        address = self.cleaned_data["address"].strip()
        if not address:
            raise forms.ValidationError("Укажите адрес объекта.")
        return address

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        address = cleaned.get("address")
        if category and address:
            duplicates = Site.objects.filter(
                category=category, address__iexact=address.strip(),
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error("category", "Объект с таким типом уже существует по этому адресу.")
        if category and not category.photo_slots.exists():
            self.add_error("category", "В этой категории ещё не настроены обязательные фото.")
        if not cleaned.get("requires_work_permit"):
            cleaned["has_work_permit"] = False
            cleaned["permit_valid_from"] = None
            cleaned["permit_valid_until"] = None
        elif cleaned.get("has_work_permit"):
            start = cleaned.get("permit_valid_from")
            end = cleaned.get("permit_valid_until")
            if not start:
                self.add_error("permit_valid_from", "Укажите дату начала действия VAO.")
            if not end:
                self.add_error("permit_valid_until", "Укажите дату окончания действия VAO.")
            if start and end and end < start:
                self.add_error("permit_valid_until", "Дата окончания не может быть раньше даты начала.")
        else:
            cleaned["permit_valid_from"] = None
            cleaned["permit_valid_until"] = None
        return cleaned


class PhotoCategoryForm(forms.ModelForm):
    class Meta:
        model = PhotoCategory
        fields = ["name"]


class PhotoCategoryPhotoForm(forms.ModelForm):
    class Meta:
        model = PhotoCategoryPhoto
        fields = ["name"]


PhotoCategoryPhotoFormSet = inlineformset_factory(
    PhotoCategory, PhotoCategoryPhoto,
    form=PhotoCategoryPhotoForm,
    extra=0,
    min_num=1,
    validate_min=True,
    max_num=10000,
    validate_max=False,
    absolute_max=10000,
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
        available_sites = Site.objects.filter(is_completed=False)
        if self.instance and self.instance.pk and self.instance.site_id:
            # Keep the current value available while editing an existing plan,
            # even if its site was completed after the plan was created.
            available_sites = Site.objects.filter(
                Q(is_completed=False) | Q(pk=self.instance.site_id)
            )
        available_sites = available_sites.filter(
            Q(requires_work_permit=False) |
            Q(
                requires_work_permit=True,
                has_work_permit=True,
                permit_valid_from__isnull=False,
                permit_valid_until__isnull=False,
            )
        )
        self.fields["site"].queryset = available_sites.order_by("name")
        self.fields["work_date"].widget.attrs["min"] = timezone.localdate().isoformat()
        self.fields["description"].label = "Краткое описание к документации"
        self.fields["worker"].queryset = Worker.objects.select_related("user").filter(user__isnull=False).order_by("name")
        self.fields["work_date"].error_messages["required"] = "Укажите дату плана."
        self.fields["site"].error_messages["required"] = "Выберите объект."
        self.fields["site"].error_messages["invalid_choice"] = "Выберите объект с полученным VAO."
        self.fields["worker"].error_messages["required"] = "Выберите работника."
        self.fields["description"].error_messages["required"] = "Добавьте краткое описание к документации."

    def clean_work_date(self):
        work_date = self.cleaned_data["work_date"]
        if work_date < timezone.localdate():
            raise forms.ValidationError(
                "Нельзя создать план на прошедшую дату. Выберите сегодня или будущий день."
            )
        return work_date

    def clean(self):
        cleaned = super().clean()
        site = cleaned.get("site")
        work_date = cleaned.get("work_date")
        if site and work_date:
            if site.requires_work_permit and not site.has_work_permit:
                self.add_error("site", "Для этого объекта требуется VAO; сначала укажите, что оно получено.")
            elif site.requires_work_permit and (
                not site.permit_valid_from or not site.permit_valid_until
            ):
                self.add_error("site", "Укажите период действия VAO для этого объекта.")
            elif site.requires_work_permit and not site.permit_valid_from <= work_date <= site.permit_valid_until:
                self.add_error("site", "План можно назначить только в период действия VAO.")
        return cleaned


class WorkPhotoForm(forms.ModelForm):
    location_accuracy = forms.DecimalField(
        max_digits=9, decimal_places=2, required=False, min_value=0,
        widget=forms.HiddenInput(attrs={"class": "photo-location-accuracy"}),
    )

    class Meta:
        model = WorkPhoto
        fields = ["image", "photo_slot", "description", "location_latitude", "location_longitude", "location_accuracy", "location_captured_at"]
        widgets = {
            "image": forms.FileInput(attrs={"class": "photo-file-input", "accept": "image/*"}),
            "photo_slot": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"rows": 2, "class": "photo-description-input", "placeholder": "Кратко опишите, что сделано"}),
            "location_latitude": forms.HiddenInput(attrs={"class": "photo-location-latitude"}),
            "location_longitude": forms.HiddenInput(attrs={"class": "photo-location-longitude"}),
            "location_captured_at": forms.HiddenInput(attrs={"class": "photo-location-captured-at"}),
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
        self.fields["location_latitude"].required = False
        self.fields["location_longitude"].required = False
        self.fields["location_captured_at"].required = False
        self.fields["location_accuracy"].required = False
        if self.instance.pk:
            self.initial.setdefault("location_latitude", self.instance.location_latitude)
            self.initial.setdefault("location_longitude", self.instance.location_longitude)
            self.initial.setdefault("location_accuracy", self.instance.location_accuracy)
            self.initial.setdefault("location_captured_at", self.instance.location_captured_at)

    def clean(self):
        cleaned = super().clean()
        latitude = cleaned.get("location_latitude")
        longitude = cleaned.get("location_longitude")
        if (latitude is None) != (longitude is None):
            cleaned["location_latitude"] = None
            cleaned["location_longitude"] = None
            cleaned["location_accuracy"] = None
            cleaned["location_captured_at"] = None
        elif latitude is not None and not -90 <= latitude <= 90:
            self.add_error("location_latitude", "Не удалось принять координаты места съёмки.")
        elif longitude is not None and not -180 <= longitude <= 180:
            self.add_error("location_longitude", "Не удалось принять координаты места съёмки.")
        return cleaned

    def has_changed(self):
        # A correction is a new submission, so inherited photo defaults must
        # be saved into its new rows even when the worker keeps them unchanged.
        if not self.instance.pk and self.initial.get("image"):
            return True
        return super().has_changed()


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
