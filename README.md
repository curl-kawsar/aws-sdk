# MinIO Upload Service

Self-hosted S3-compatible file/image upload API built with **FastAPI** and **MinIO**.
Run it on your VPS once, use it from any project.

**Live:** `https://upload.1550plus.com`

## Quick Start (local dev)

```bash
# 1. Configure
cp env.example .env       # edit credentials in .env

# 2. Start everything
docker compose up -d --build

# 3. Open
#    Upload UI    → http://localhost:6500
#    API docs     → http://localhost:6500/docs  (only when DISABLE_DOCS=false)
#    MinIO console → http://localhost:19801  (ports from MINIO_HOST_PORT_* in .env)
```

## Production Deployment

```bash
# On your VPS:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This binds the API and MinIO to **localhost only** (ports from `.env`: `API_HOST_PORT`, `MINIO_HOST_PORT_S3`, `MINIO_HOST_PORT_CONSOLE`; defaults **6500** / **19800** / **19801**). Nginx is the sole public-facing entry.

### Setup checklist

1. **DNS:** `A` record for `upload.1550plus.com` → your VPS IP.
2. **`.env`:** strong `MINIO_ROOT_*`, `API_KEYS`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `PUBLIC_BASE_URL`.
3. **Nginx:** copy `deploy/nginx/upload-api.conf` → `/etc/nginx/sites-available/upload.1550plus.com`, symlink to `sites-enabled`, run `nginx -t && systemctl reload nginx`.
4. **TLS:** `sudo certbot --nginx -d upload.1550plus.com` then `systemctl reload nginx`.
5. **Firewall:** allow **22**, **80**, **443** only. Do not expose `API_HOST_PORT` or MinIO host ports on the public internet when using the production overlay.
6. **Backups:** snapshot `minio_data` volume or `mc mirror`.

## API Endpoints

| Method   | Path                              | Description                  |
|----------|-----------------------------------|------------------------------|
| `POST`   | `/upload`                         | Upload a single file         |
| `POST`   | `/upload/multiple`                | Upload multiple files        |
| `GET`    | `/files`                          | List all files               |
| `GET`    | `/files/{name}/url`               | Get download URL             |
| `GET`    | `/files/{name}/download`          | Download file directly       |
| `DELETE` | `/files/{name}`                   | Delete a file                |
| `GET`    | `/health`                         | Health check (no auth)       |

All endpoints except `/health` require **`X-API-Key`** header when `API_KEYS` is set.

## Usage Examples

### Upload (curl)
```bash
curl -X POST https://upload.1550plus.com/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@photo.jpg" \
  -F "folder=avatars"
```

### Upload (Python)
```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post(
        "https://upload.1550plus.com/upload",
        headers={"X-API-Key": "YOUR_API_KEY"},
        files={"file": ("photo.jpg", f, "image/jpeg")},
        data={"folder": "avatars"},
    )
print(r.json())
# {"object_name": "avatars/abc123.jpg", "url": "https://upload.1550plus.com/files/avatars/abc123.jpg/download", ...}
```

### Upload (JavaScript)
```javascript
const form = new FormData();
form.append("file", fileInput.files[0]);
form.append("folder", "avatars");

const res = await fetch("https://upload.1550plus.com/upload", {
  method: "POST",
  headers: { "X-API-Key": "YOUR_API_KEY" },
  body: form,
});
const data = await res.json();
console.log(data.url); // permanent download link
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MINIO_HOST_PORT_S3` | `19800` | Host port mapped to MinIO S3 API (increase if port busy). |
| `MINIO_HOST_PORT_CONSOLE` | `19801` | Host port for MinIO web console. |
| `API_HOST_PORT` | `6500` | Host port for FastAPI; **must match** Nginx `upstream` in `deploy/nginx/upload-api.conf`. |
| `MINIO_ROOT_USER` | `minioadmin` | MinIO root username |
| `MINIO_ROOT_PASSWORD` | `minioadmin123` | MinIO root password |
| `MINIO_BUCKET` | `uploads` | Default bucket name |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size in MB |
| `ALLOWED_EXTENSIONS` | _(empty = all)_ | Comma-separated: `jpg,png,pdf` |
| `PERMANENT_DOWNLOAD_URLS` | `true` | Use `/files/.../download` (no expiry) instead of presigned S3 URLs |
| `PUBLIC_BASE_URL` | _(empty)_ | e.g. `https://upload.1550plus.com` |
| `PRESIGNED_URL_EXPIRES_HOURS` | `1` | Presigned lifetime when `PERMANENT_DOWNLOAD_URLS=false` |
| `CORS_ORIGINS` | _(empty = *)_ | Comma-separated allowed browser origins |
| `TRUSTED_HOSTS` | _(disabled)_ | Allowed `Host` header values |
| `API_KEYS` | _(disabled)_ | Comma-separated; required on all routes except `/health` |
| `DISABLE_DOCS` | `true` | Hide `/docs`, `/redoc`, `/openapi.json` |
