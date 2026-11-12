"""Create the first demo administrator from Render environment variables."""

import os
import sys
from pathlib import Path

import django

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "b2b.settings")
django.setup()

username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
if username and password:
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    if not user_model.objects.filter(username=username).exists():
        user_model.objects.create_superuser(
            username=username,
            email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
            password=password,
        )
