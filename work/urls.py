from django.urls import path
from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("sites/", views.SiteListView.as_view(), name="site_list"),
    path("workers/", views.WorkerListView.as_view(), name="worker_list"),
    path("report/new/", views.ReportCreateView.as_view(), name="report_create"),
]
