from django.conf import settings
from django.db import models


class Worker(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="worker", verbose_name="Учётная запись",
    )
    name = models.CharField("Имя", max_length=100)
    phone = models.CharField("Телефон", max_length=30)

    def __str__(self):
        return self.name


class Site(models.Model):
    class SiteType(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    name = models.CharField("Название объекта", max_length=150)
    address = models.CharField("Адрес", max_length=255)
    site_type = models.CharField("Тип объекта", max_length=1, choices=SiteType.choices, default=SiteType.A)
    workers = models.ManyToManyField(
        Worker, related_name="sites", blank=True, verbose_name="Работники"
    )

    def __str__(self):
        return self.name


class Report(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="reports")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="reports")
    photo = models.ImageField("Фото", upload_to="reports/%Y/%m/")
    description = models.TextField("Описание выполненной работы")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.site} / {self.worker} / {self.created_at:%d.%m.%Y}"


class WorkPlan(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        SUBMITTED = "submitted", "На проверке"
        REVISION = "revision", "Отклонено — нужна доработка"
        APPROVED = "approved", "Принято"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="work_plans", verbose_name="Объект")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="work_plans", verbose_name="Работник")
    work_date = models.DateField("Дата выполнения", db_index=True)
    description = models.TextField("Краткое описание к документации")
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.PLANNED, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_work_plans")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    review_comment = models.TextField("Комментарий к проверке", blank=True)
    reviewed_at = models.DateTimeField("Проверено", null=True, blank=True)

    class Meta:
        ordering = ["-work_date", "site__name"]
        verbose_name = "План работы"
        verbose_name_plural = "Планы работы"

    def __str__(self):
        return f"{self.work_date:%d.%m.%Y} · {self.site} · {self.worker}"


class PlanDocument(models.Model):
    plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("PDF", upload_to="plans/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "PDF к плану"
        verbose_name_plural = "PDF к плану"

    def __str__(self):
        return self.file.name.rsplit("/", 1)[-1]


class PhotoCategory(models.Model):
    name = models.CharField("Категория фото", max_length=80, unique=True)
    is_active = models.BooleanField("Активна", default=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Категория фото"
        verbose_name_plural = "Категории фото"

    def __str__(self):
        return self.name


class WorkSubmission(models.Model):
    plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name="submissions")
    created_at = models.DateTimeField("Отправлено", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сдача работы"
        verbose_name_plural = "Сдачи работ"

    def __str__(self):
        return f"{self.plan} · {self.created_at:%d.%m.%Y %H:%M}"


class WorkPhoto(models.Model):
    submission = models.ForeignKey(WorkSubmission, on_delete=models.CASCADE, related_name="photos")
    category = models.ForeignKey(PhotoCategory, on_delete=models.PROTECT, null=True, related_name="photos", verbose_name="Категория")
    image = models.ImageField("Фото", upload_to="work/%Y/%m/")
    description = models.TextField("Что сделано")

    class Meta:
        verbose_name = "Фото выполненной работы"
        verbose_name_plural = "Фото выполненной работы"
