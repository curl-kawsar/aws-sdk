import os


class Settings:
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:7000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "uploads")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

    # If true, upload + /url return API /files/.../download links (no signature expiry).
    # Presigned MinIO URLs always expire (SDK max is typically 7 days).
    PERMANENT_DOWNLOAD_URLS: bool = (
        os.getenv("PERMANENT_DOWNLOAD_URLS", "true").lower() == "true"
    )
    # Optional absolute base (e.g. https://cdn.example.com). Empty = use each request's Host.
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    # Used only when PERMANENT_DOWNLOAD_URLS is false
    PRESIGNED_URL_EXPIRES_HOURS: int = int(os.getenv("PRESIGNED_URL_EXPIRES_HOURS", "1"))

    # Comma-separated list like "jpg,png,pdf" — empty means allow all
    _raw_extensions: str = os.getenv("ALLOWED_EXTENSIONS", "")
    ALLOWED_EXTENSIONS: set[str] = (
        {ext.strip().lower().lstrip(".") for ext in _raw_extensions.split(",") if ext.strip()}
        if _raw_extensions
        else set()
    )

    # CORS: comma-separated origins, e.g. "https://app.example.com,https://example.com"
    # Empty = allow all origins (dev only)
    _raw_cors: str = os.getenv("CORS_ORIGINS", "").strip()
    CORS_ORIGINS: list[str] = (
        [o.strip() for o in _raw_cors.split(",") if o.strip()] if _raw_cors else ["*"]
    )

    # Host header allowlist (mitigates Host header attacks). Empty = disabled.
    # Example: "files.example.com,203.0.113.10" — include your public hostname or IP
    _raw_hosts: str = os.getenv("TRUSTED_HOSTS", "").strip()
    TRUSTED_HOSTS: list[str] | None = (
        [h.strip() for h in _raw_hosts.split(",") if h.strip()] if _raw_hosts else None
    )

    # Comma-separated API keys; empty = no key required (not for public production)
    _raw_api_keys: str = os.getenv("API_KEYS", "").strip()
    API_KEYS: frozenset[str] = frozenset(
        k.strip() for k in _raw_api_keys.split(",") if k.strip()
    )

    # Disable /docs + /redoc in production (Nginx also blocks them, but belt-and-suspenders)
    DISABLE_DOCS: bool = os.getenv("DISABLE_DOCS", "true").lower() == "true"


settings = Settings()
