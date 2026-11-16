from django.conf import settings
from django.db import models
from django.db.models.functions import Lower, Trim


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
    name = models.CharField("Название объекта", max_length=150)
    object_number = models.CharField("Номер объекта", max_length=50, default="")
    address = models.CharField("Адрес", max_length=255)
    category = models.ForeignKey(
        "PhotoCategory", on_delete=models.PROTECT, null=True, blank=True,
        related_name="sites", verbose_name="Категория объекта",
    )
    requires_work_permit = models.BooleanField("Для работ требуется VAO", default=False)
    has_work_permit = models.BooleanField("VAO получено", default=False)
    permit_valid_from = models.DateField("VAO действует с", null=True, blank=True)
    permit_valid_until = models.DateField("VAO действует по", null=True, blank=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True, null=True, blank=True)
    is_completed = models.BooleanField("Объект завершён", default=False, db_index=True)
    workers = models.ManyToManyField(
        Worker, related_name="sites", blank=True, verbose_name="Работники"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("address")), "category",
                name="unique_site_address_category_ci",
            ),
        ]

    def __str__(self):
        return self.name


class SiteDocument(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("Документ", upload_to="sites/%Y/%m/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Документ объекта"
        verbose_name_plural = "Документы объекта"

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
    name = models.CharField("Название категории объекта", max_length=80, unique=True)
    is_active = models.BooleanField("Активна", default=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Категория объекта"
        verbose_name_plural = "Категории объектов"

    def __str__(self):
        return self.name


class PhotoCategoryPhoto(models.Model):
    category = models.ForeignKey(
        PhotoCategory, on_delete=models.CASCADE, related_name="photo_slots",
        verbose_name="Категория объекта",
    )
    name = models.CharField("Название обязательного фото", max_length=120)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Обязательное фото категории"
        verbose_name_plural = "Обязательные фото категории"

    def __str__(self):
        return f"{self.category} · {self.name}"


class SitePhotoRequirement(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="photo_requirements")
    category = models.ForeignKey(PhotoCategory, on_delete=models.PROTECT, related_name="site_requirements", verbose_name="Категория фото")
    name = models.CharField("Название фото", max_length=120, blank=True, default="")
    order = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Обязательное фото объекта"
        verbose_name_plural = "Обязательные фото объекта"

    def __str__(self):
        return f"{self.site} · {self.name}"


class WorkSubmission(models.Model):
    plan = models.ForeignKey(WorkPlan, on_delete=models.CASCADE, related_name="submissions")
    review_comment = models.TextField("Причина возврата на доработку", blank=True)
    status = models.CharField(
        "Состояние отправки", max_length=12, choices=WorkPlan.Status.choices,
        null=True, blank=True, default=None,
    )
    location_latitude = models.DecimalField("Широта при отправке", max_digits=9, decimal_places=6, null=True, blank=True)
    location_longitude = models.DecimalField("Долгота при отправке", max_digits=9, decimal_places=6, null=True, blank=True)
    location_accuracy = models.DecimalField("Точность геолокации, м", max_digits=9, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField("Отправлено", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сдача работы"
        verbose_name_plural = "Сдачи работ"

    def __str__(self):
        return f"{self.plan} · {self.created_at:%d.%m.%Y %H:%M}"


class WorkSubmissionOfficeNote(models.Model):
    submission = models.ForeignKey(
        WorkSubmission, on_delete=models.CASCADE, related_name="office_notes",
    )
    text = models.TextField("Дополнение от Office")
    created_at = models.DateTimeField("Добавлено", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Дополнение Office к отчёту"
        verbose_name_plural = "Дополнения Office к отчётам"

    def __str__(self):
        return f"Дополнение Office · отправка {self.submission_id} · {self.created_at:%d.%m.%Y %H:%M}"


class WorkSubmissionEvent(models.Model):
    class Type(models.TextChoices):
        SUBMITTED = "submitted", "Отправлен отчёт"
        APPROVED = "approved", "Отчёт принят"
        REVISION = "revision", "Отправлен на доработку"
        REOPENED = "reopened", "Возвращён на проверку"

    submission = models.ForeignKey(WorkSubmission, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField("Событие", max_length=12, choices=Type.choices)
    text = models.TextField("Сообщение", blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField("Время", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Событие переписки по отчёту"
        verbose_name_plural = "События переписки по отчётам"


class WorkPhoto(models.Model):
    submission = models.ForeignKey(WorkSubmission, on_delete=models.CASCADE, related_name="photos")
    photo_slot = models.ForeignKey(
        SitePhotoRequirement, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="photos", verbose_name="Требуемое фото",
    )
    category = models.ForeignKey(PhotoCategory, on_delete=models.PROTECT, null=True, related_name="photos", verbose_name="Категория")
    image = models.ImageField("Фото", upload_to="work/%Y/%m/")
    stamped_image = models.ImageField("Фото с геометкой", upload_to="work/geotagged/%Y/%m/", null=True, blank=True)
    location_latitude = models.DecimalField("Широта места съёмки", max_digits=9, decimal_places=6, null=True, blank=True)
    location_longitude = models.DecimalField("Долгота места съёмки", max_digits=9, decimal_places=6, null=True, blank=True)
    location_accuracy = models.DecimalField("Точность геолокации фото, м", max_digits=9, decimal_places=2, null=True, blank=True)
    location_captured_at = models.DateTimeField("Время фиксации геолокации фото", null=True, blank=True)
    location_address = models.CharField("Примерный адрес места съёмки", max_length=255, blank=True, default="")
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


class LocationGeocodeCache(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    address = models.CharField("Примерный адрес", max_length=255)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Кэш примерных адресов геолокации"
        verbose_name_plural = "Кэш примерных адресов геолокации"


class LocationGeocodeGate(models.Model):
    last_request_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Ограничитель запросов геокодирования"
        verbose_name_plural = "Ограничители запросов геокодирования"
