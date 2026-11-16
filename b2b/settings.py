from pathlib import Path
import os

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Render supplies RENDER at runtime; local development remains convenient.
debug_default = "False" if os.environ.get("RENDER") else "True"
DEBUG = os.environ.get("DEBUG", debug_default).strip().lower() in {"1", "true", "yes"}
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-key-only")
if not DEBUG and SECRET_KEY == "local-development-key-only":
    raise RuntimeError("Set DJANGO_SECRET_KEY in the environment when DEBUG is disabled.")

ALLOWED_HOSTS = [host.strip() for host in os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",") if host.strip()]
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
csrf_default = "https://*.onrender.com" if os.environ.get("RENDER") else ""
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "CSRF_TRUSTED_ORIGINS", csrf_default
).split(",") if origin.strip()]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "django_filters",
    "storages",
    'work',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'b2b.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'b2b.wsgi.application'

DATABASE_URL = os.environ.get("DATABASE_URL")
if os.environ.get("RENDER") and not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL to the Render PostgreSQL connection string.")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('de', 'Deutsch'),
    ('bg', 'Български'),
]
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True
LOCATION_GEOCODER_URL = os.environ.get(
    "LOCATION_GEOCODER_URL", "https://nominatim.openstreetmap.org/reverse"
)
LOCATION_GEOCODER_USER_AGENT = os.environ.get(
    "LOCATION_GEOCODER_USER_AGENT",
    "B2BObjectReports/1.0 (photo location reverse geocoding)",
)

MEDIA_URL = "/media/"
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
MEDIA_ROOT = DATA_DIR / "media"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Use an S3-compatible bucket for uploaded media when configured. This is
# required on Render Free because its local filesystem is ephemeral.
if os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    s3_options = {
        "bucket_name": os.environ["AWS_STORAGE_BUCKET_NAME"],
        "region_name": os.environ.get("AWS_S3_REGION_NAME") or None,
        "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL") or None,
        "custom_domain": os.environ.get("AWS_S3_CUSTOM_DOMAIN") or None,
        "querystring_auth": True,
        "file_overwrite": False,
    }
    addressing_style = os.environ.get("AWS_S3_ADDRESSING_STYLE")
    if addressing_style:
        s3_options["addressing_style"] = addressing_style
    signature_version = os.environ.get("AWS_S3_SIGNATURE_VERSION")
    if signature_version:
        s3_options["signature_version"] = signature_version

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": s3_options,
    }

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
