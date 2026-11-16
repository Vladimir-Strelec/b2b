from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.urls import reverse_lazy

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page=reverse_lazy("login")), name="logout"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("work.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
