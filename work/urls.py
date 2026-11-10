from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("sites/", views.SiteListView.as_view(), name="site_list"),
    path("workers/", views.WorkerListView.as_view(), name="worker_list"),
    path("report/new/", views.ReportCreateView.as_view(), name="report_create"),
    path("reports/", views.ReportListView.as_view(), name="report_list"),
    path("plans/", views.WorkPlanListView.as_view(), name="plan_list"),
    path("plans/new/", views.WorkPlanCreateView.as_view(), name="plan_create"),
    path("plans/<int:pk>/edit/", views.WorkPlanUpdateView.as_view(), name="plan_edit"),
    path("plans/mine/", views.WorkerPlanListView.as_view(), name="worker_plans"),
    path("plans/<int:pk>/", views.WorkPlanDetailView.as_view(), name="plan_detail"),

    path("sites/new/", views.SiteCreateView.as_view(), name="site_create"),
    path("sites/<int:pk>/edit/", views.SiteUpdateView.as_view(), name="site_edit"),
    path("sites/<int:pk>/delete/", views.SiteDeleteView.as_view(), name="site_delete"),
    path("workers/new/", views.WorkerCreateView.as_view(), name="worker_create"),
    path("workers/<int:pk>/edit/", views.WorkerUpdateView.as_view(), name="worker_edit"),
    path("workers/<int:pk>/delete/", views.WorkerDeleteView.as_view(), name="worker_delete"),

    path("sites/<int:pk>/", views.SiteDetailView.as_view(), name="site_detail"),
    path("reports/<int:pk>/", views.ReportDetailView.as_view(), name="report_detail"),
    path("reports/submission/<int:pk>/", views.WorkSubmissionDetailView.as_view(), name="submission_detail"),
]
