from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import Report, Site, Worker, WorkPlan, PlanDocument, PhotoCategory, WorkSubmission, WorkPhoto

User = get_user_model()


class WorkerAdminForm(forms.ModelForm):
    username = forms.CharField(
        label="Логин для входа", required=False,
        help_text="Заполняется только при создании работника.",
    )
    password = forms.CharField(
        label="Пароль", required=False, widget=forms.PasswordInput,
    )

    class Meta:
        model = Worker
        fields = ["name", "phone"]

    def clean(self):
        cleaned = super().clean()
        if self.instance.user_id:
            return cleaned  # у работника уже есть учётная запись
        username = cleaned.get("username")
        password = cleaned.get("password")
        if username or password:
            if not (username and password):
                raise forms.ValidationError("Укажите и логин, и пароль.")
            if User.objects.filter(username=username).exists():
                raise forms.ValidationError("Такой логин уже занят.")
        return cleaned


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    form = WorkerAdminForm
    fields = ("name", "phone", "username", "password")
    list_display = ("name", "phone", "user")
    list_filter = ("sites",)
    search_fields = ("name", "phone")

    def save_model(self, request, obj, form, change):
        username = form.cleaned_data.get("username")
        password = form.cleaned_data.get("password")
        if username and password and not obj.user_id:
            obj.user = User.objects.create_user(username=username, password=password)
        super().save_model(request, obj, form, change)


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "site_type")
    list_filter = ("workers",)
    search_fields = ("name", "address")
    filter_horizontal = ("workers",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("site", "worker", "created_at")
    list_filter = ("site", "worker", "created_at")


class PlanDocumentInline(admin.TabularInline):
    model = PlanDocument
    extra = 0


@admin.register(WorkPlan)
class WorkPlanAdmin(admin.ModelAdmin):
    list_display = ("work_date", "site", "worker", "status")
    list_filter = ("work_date", "status", "site", "worker")
    search_fields = ("site__name", "worker__name", "description")
    inlines = (PlanDocumentInline,)


@admin.register(PhotoCategory)
class PhotoCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")


class WorkPhotoInline(admin.TabularInline):
    model = WorkPhoto
    extra = 0


@admin.register(WorkSubmission)
class WorkSubmissionAdmin(admin.ModelAdmin):
    list_display = ("plan", "created_at")
    inlines = (WorkPhotoInline,)
