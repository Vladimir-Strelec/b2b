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


class WorkShift(models.Model):
    worker = models.ForeignKey(
        Worker, on_delete=models.CASCADE, related_name="shifts", verbose_name="Работник"
    )
    started_at = models.DateTimeField("Начало смены", auto_now_add=True)
    ended_at = models.DateTimeField("Конец смены", null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Рабочая смена"
        verbose_name_plural = "Рабочие смены"
        constraints = [
            models.UniqueConstraint(
                fields=["worker"], condition=models.Q(ended_at__isnull=True),
                name="one_open_shift_per_worker",
            ),
        ]

    def __str__(self):
        return f"{self.worker} · {self.started_at:%d.%m.%Y %H:%M}"


class Site(models.Model):
    class SiteType(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    name = models.CharField("Название объекта", max_length=150)
    object_number = models.CharField("Номер объекта", max_length=50, default="")
    address = models.CharField("Адрес", max_length=255)
    site_type = models.CharField("Тип объекта", max_length=1, choices=SiteType.choices, default=SiteType.A)
    completion_reverted = models.BooleanField(
        "Статус завершения сброшен", default=False,
        help_text="Объект исключён из завершённых без удаления планов и отчётов.",
    )
    workers = models.ManyToManyField(
        Worker, related_name="sites", blank=True, verbose_name="Работники"
    )

    def __str__(self):
        return self.name


class SiteDocument(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("PDF", upload_to="sites/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "PDF объекта"
        verbose_name_plural = "PDF объекта"

    def __str__(self):
        return self.file.name.rsplit("/", 1)[-1]


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


class SitePhotoRequirement(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="photo_requirements")
    category = models.ForeignKey(PhotoCategory, on_delete=models.PROTECT, related_name="site_requirements", verbose_name="Категория фото")
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Обязательное фото объекта"
        verbose_name_plural = "Обязательные фото объекта"

    def __str__(self):
        return f"{self.site} · {self.category}"


class WorkSubmission(models.Model):
    plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name="submissions")
    review_comment = models.TextField("Причина возврата на доработку", blank=True)
    status = models.CharField(
        "Состояние отправки", max_length=12, choices=WorkPlan.Status.choices,
        null=True, blank=True, default=None,
    )
    created_at = models.DateTimeField("Отправлено", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сдача работы"
        verbose_name_plural = "Сдачи работ"

    def __str__(self):
        return f"{self.plan} · {self.created_at:%d.%m.%Y %H:%M}"


class WorkPhoto(models.Model):
    submission = models.ForeignKey(WorkSubmission, on_delete=models.CASCADE, related_name="photos")
    photo_slot = models.ForeignKey(
        SitePhotoRequirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="photos", verbose_name="Требуемое фото",
    )
    category = models.ForeignKey(PhotoCategory, on_delete=models.PROTECT, null=True, related_name="photos", verbose_name="Категория")
    image = models.ImageField("Фото", upload_to="work/%Y/%m/")
    description = models.TextField("Что сделано", blank=True, default="")

    class Meta:
        verbose_name = "Фото выполненной работы"
        verbose_name_plural = "Фото выполненной работы"
        constraints = [
            models.UniqueConstraint(fields=["submission", "photo_slot"], name="unique_photo_slot_per_submission"),
        ]

    def save(self, *args, **kwargs):
        if self.photo_slot_id:
            self.category = self.photo_slot.category
        super().save(*args, **kwargs)
