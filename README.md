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

## Render uploads

- `DATA_DIR=/data` is set by the Docker image, and uploaded files are stored under `/data/media`. The app serves these files through an authenticated route that checks staff and worker access.
- Render Free services have ephemeral filesystems and do not support persistent disks. For uploads to survive restarts and redeploys, configure an S3-compatible bucket. A paid Render service can instead use a persistent disk mounted at `/data`.

For Cloudflare R2, create a private bucket and an API token restricted to **Object Read & Write** for that bucket. Add these variables in the Render service's Environment settings; keep the access keys secret:

```text
AWS_STORAGE_BUCKET_NAME=<bucket name>
AWS_ACCESS_KEY_ID=<R2 access key ID>
AWS_SECRET_ACCESS_KEY=<R2 secret access key>
AWS_S3_REGION_NAME=auto
AWS_S3_ENDPOINT_URL=https://<Cloudflare account ID>.r2.cloudflarestorage.com
AWS_S3_ADDRESSING_STYLE=path
AWS_S3_SIGNATURE_VERSION=s3v4
```

The app keeps the bucket private and uses signed URLs to open files. For another S3-compatible provider, use its bucket, access keys, region, and endpoint instead; `AWS_S3_ADDRESSING_STYLE` and `AWS_S3_SIGNATURE_VERSION` are optional provider settings.

## Heroku uploads

Configure an S3-compatible bucket in the hosting service settings with `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_S3_REGION_NAME`. For S3-compatible providers, also set `AWS_S3_ENDPOINT_URL`; optionally set `AWS_S3_CUSTOM_DOMAIN`. Once configured, Django stores uploaded photos and PDFs in the bucket and serves them with signed URLs.
