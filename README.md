---
title: B2B
emoji: 🏢
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# B2B

Private business workspace for site plans, worker reports, and work-time tracking.

## Space setup

- Add `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` as Space secrets to create the first owner account at startup. The account is created once.
- Attach persistent storage mounted at `/data`; the SQLite database, uploaded files, and generated Django secret key are stored there.
- The local SQLite database, media uploads, virtual environment, IDE files, and `.env` files are excluded from the Docker build.

## Heroku uploads

Heroku dynos use an ephemeral filesystem, so uploaded photos and PDFs must be stored in a durable object-storage bucket. Configure an S3-compatible bucket in the Heroku app settings with `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_S3_REGION_NAME`. For S3-compatible providers, also set `AWS_S3_ENDPOINT_URL`; optionally set `AWS_S3_CUSTOM_DOMAIN`. Once configured, Django stores all uploaded photos and PDFs in the bucket and serves them with signed URLs.
