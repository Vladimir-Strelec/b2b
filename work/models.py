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
    name = models.CharField("Название объекта", max_length=150)
    address = models.CharField("Адрес", max_length=255)
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