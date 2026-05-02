from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from minio.error import S3Error
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.middleware_auth import ApiKeyMiddleware
from app.storage import (
    delete_file,
    ensure_bucket,
    get_file,
    get_presigned_url,
    list_files,
    upload_file,
)

# ── Lifespan ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: make sure the bucket exists
    ensure_bucket()
    yield


# ── App ───────────────────────────────────────────────────────────────
_docs_kwargs = {}
if settings.DISABLE_DOCS:
    _docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(
    title="MinIO Upload Service",
    description="Self-hosted S3-compatible file/image upload API",
    version="1.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
)

# Order: last added runs first on the request. CORS must run before auth for OPTIONS.
app.add_middleware(ApiKeyMiddleware)
if settings.TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────
MAX_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024


def _validate_file(filename: str, size: int) -> None:
    if size > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {settings.MAX_FILE_SIZE_MB} MB.",
        )
    if settings.ALLOWED_EXTENSIONS:
        ext = PurePosixPath(filename).suffix.lstrip(".").lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '.{ext}' not allowed. Allowed: {sorted(settings.ALLOWED_EXTENSIONS)}",
            )


def _permanent_download_url(request: Request, object_name: str) -> str:
    """Stable URL through this API (no presigned expiry). Encode each path segment."""
    path = "/".join(quote(seg, safe="") for seg in object_name.split("/") if seg)
    base = settings.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}/files/{path}/download"


def _file_url(request: Request, object_name: str) -> str:
    if settings.PERMANENT_DOWNLOAD_URLS:
        return _permanent_download_url(request, object_name)
    return get_presigned_url(
        object_name, expires_hours=settings.PRESIGNED_URL_EXPIRES_HOURS
    )


# ── Endpoints ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Serve a minimal upload test page."""
    return UPLOAD_PAGE_HTML


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form(default=""),
):
    """
    Upload a file to MinIO.

    - **file**: The file to upload (multipart form data).
    - **folder**: Optional subfolder/prefix inside the bucket.
    """
    contents = await file.read()
    _validate_file(file.filename, len(contents))

    try:
        meta = upload_file(
            file_data=contents,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            folder=folder,
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=str(e))

    meta["url"] = _file_url(request, meta["object_name"])
    return meta


@app.post("/upload/multiple")
async def upload_multiple(
    request: Request,
    files: list[UploadFile] = File(...),
    folder: str = Form(default=""),
):
    """Upload multiple files in one request."""
    results = []
    for f in files:
        contents = await f.read()
        _validate_file(f.filename, len(contents))
        try:
            meta = upload_file(
                file_data=contents,
                original_filename=f.filename,
                content_type=f.content_type or "application/octet-stream",
                folder=folder,
            )
            meta["url"] = _file_url(request, meta["object_name"])
            results.append(meta)
        except S3Error as e:
            results.append({"filename": f.filename, "error": str(e)})
    return results


@app.get("/files")
async def files_list(
    prefix: str = Query(default="", description="Filter by prefix/folder"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """List uploaded files."""
    return list_files(prefix=prefix, max_keys=limit)


@app.get("/files/{object_name:path}/url")
async def file_url(
    request: Request,
    object_name: str,
    expires: int = Query(default=1, ge=1, le=168),
):
    """Get a download URL: permanent API link, or presigned MinIO URL (expires in hours, max 7 days)."""
    if settings.PERMANENT_DOWNLOAD_URLS:
        return {
            "object_name": object_name,
            "url": _permanent_download_url(request, object_name),
            "permanent": True,
        }
    try:
        url = get_presigned_url(object_name, expires_hours=expires)
    except S3Error as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"object_name": object_name, "url": url, "expires_hours": expires}


@app.get("/files/{object_name:path}/download")
async def file_download(object_name: str):
    """Download a file directly through the API."""
    try:
        data, content_type = get_file(object_name)
    except S3Error as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{PurePosixPath(object_name).name}"'},
    )


@app.delete("/files/{object_name:path}")
async def file_delete(object_name: str):
    """Delete a file from storage."""
    try:
        delete_file(object_name)
    except S3Error as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"deleted": object_name}


# ── Minimal upload test page ──────────────────────────────────────────

UPLOAD_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>MinIO Upload Service</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@400;600;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0e1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --accent-glow: rgba(88, 166, 255, 0.15);
    --green: #3fb950;
    --red: #f85149;
    --radius: 12px;
  }

  body {
    font-family: 'Outfit', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }

  .container {
    max-width: 600px;
    width: 100%;
  }

  h1 {
    font-size: 1.8rem;
    font-weight: 700;
    margin-bottom: .25rem;
    background: linear-gradient(135deg, var(--accent), var(--green));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .subtitle { color: var(--muted); margin-bottom: 2rem; font-size: .95rem; }

  .drop-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    padding: 3rem 2rem;
    text-align: center;
    cursor: pointer;
    transition: all .2s;
    background: var(--surface);
  }

  .drop-zone:hover,
  .drop-zone.drag-over {
    border-color: var(--accent);
    background: var(--accent-glow);
  }

  .drop-zone p { color: var(--muted); margin-top: .5rem; font-size: .85rem; }
  .drop-zone .icon { font-size: 2.5rem; margin-bottom: .5rem; }

  input[type="file"] { display: none; }

  .folder-row {
    display: flex;
    gap: .75rem;
    margin-top: 1rem;
  }

  input[type="text"], button {
    font-family: 'JetBrains Mono', monospace;
    font-size: .85rem;
    padding: .65rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    outline: none;
  }

  input[type="text"]:focus { border-color: var(--accent); }
  input[type="text"] { flex: 1; }

  button {
    cursor: pointer;
    background: var(--accent);
    border: none;
    color: #fff;
    font-weight: 700;
    padding: .65rem 1.5rem;
    transition: opacity .15s;
  }

  button:hover { opacity: .85; }
  button:disabled { opacity: .4; cursor: not-allowed; }

  #status {
    margin-top: 1.25rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: .8rem;
    color: var(--muted);
  }

  #results {
    margin-top: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: .75rem;
  }

  .result-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    word-break: break-all;
  }

  .result-card .name { font-weight: 600; color: var(--green); }
  .result-card .meta { color: var(--muted); font-size: .8rem; margin-top: .25rem; }
  .result-card a {
    color: var(--accent);
    text-decoration: none;
    font-family: 'JetBrains Mono', monospace;
    font-size: .78rem;
  }
  .result-card a:hover { text-decoration: underline; }

  .file-list { margin-top: 2rem; }
  .file-list h2 { font-size: 1.1rem; margin-bottom: .75rem; }
</style>
</head>
<body>
<div class="container">
  <h1>MinIO Upload Service</h1>
  <p class="subtitle">Drop files here or click to browse — they land in your self-hosted bucket.</p>

  <div class="drop-zone" id="dropZone">
    <div class="icon">&#128230;</div>
    <strong>Choose files or drag &amp; drop</strong>
    <p>Any file type &bull; Up to 50 MB</p>
  </div>
  <input type="file" id="fileInput" multiple />

  <div class="folder-row">
    <input type="text" id="folder" placeholder="folder (optional)" />
    <button id="uploadBtn" disabled>Upload</button>
    <button id="listBtn" style="background:var(--green)">List</button>
  </div>

  <div id="status"></div>
  <div id="results"></div>
</div>

<script>
  const dropZone   = document.getElementById('dropZone');
  const fileInput  = document.getElementById('fileInput');
  const uploadBtn  = document.getElementById('uploadBtn');
  const listBtn    = document.getElementById('listBtn');
  const statusEl   = document.getElementById('status');
  const resultsEl  = document.getElementById('results');
  const folderEl   = document.getElementById('folder');

  let selectedFiles = [];

  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    selectedFiles = [...e.dataTransfer.files];
    onFilesSelected();
  });

  fileInput.addEventListener('change', () => {
    selectedFiles = [...fileInput.files];
    onFilesSelected();
  });

  function onFilesSelected() {
    uploadBtn.disabled = selectedFiles.length === 0;
    statusEl.textContent = selectedFiles.length
      ? `${selectedFiles.length} file(s) ready`
      : '';
  }

  uploadBtn.addEventListener('click', async () => {
    if (!selectedFiles.length) return;
    uploadBtn.disabled = true;
    statusEl.textContent = 'Uploading…';
    resultsEl.innerHTML = '';

    const fd = new FormData();
    selectedFiles.forEach(f => fd.append('files', f));
    fd.append('folder', folderEl.value.trim());

    try {
      const res  = await fetch('/upload/multiple', { method: 'POST', body: fd });
      const data = await res.json();
      statusEl.textContent = 'Done!';
      data.forEach(item => {
        if (item.error) {
          resultsEl.innerHTML += `<div class="result-card"><span class="name" style="color:var(--red)">${item.filename}</span><div class="meta">${item.error}</div></div>`;
        } else {
          resultsEl.innerHTML += `<div class="result-card"><span class="name">${item.original_filename}</span><div class="meta">${(item.size_bytes/1024).toFixed(1)} KB &bull; ${item.content_type}</div><a href="${item.url}" target="_blank">${item.object_name}</a></div>`;
        }
      });
    } catch (err) {
      statusEl.textContent = 'Upload failed: ' + err.message;
    }
    uploadBtn.disabled = false;
  });

  listBtn.addEventListener('click', async () => {
    resultsEl.innerHTML = '';
    statusEl.textContent = 'Loading…';
    try {
      const prefix = folderEl.value.trim();
      const res  = await fetch(`/files?prefix=${encodeURIComponent(prefix)}`);
      const data = await res.json();
      statusEl.textContent = `${data.length} file(s)`;
      data.forEach(item => {
        resultsEl.innerHTML += `<div class="result-card"><span class="name">${item.object_name}</span><div class="meta">${(item.size_bytes/1024).toFixed(1)} KB &bull; ${item.last_modified}</div></div>`;
      });
    } catch (err) {
      statusEl.textContent = 'Error: ' + err.message;
    }
  });
</script>
</body>
</html>
"""
