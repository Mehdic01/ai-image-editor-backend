# app/main.py
# FastAPI uygulamasının giriş noktası

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional, List
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import shutil
import time
import json
import base64
import mimetypes

import httpx
from sqlmodel import select, Session

from .config import settings, BASE_DIR
from .db import init_db, get_session
from .models import Job
from .schemas import JobOut, JobListItem

from fastapi.responses import FileResponse, RedirectResponse
from urllib.parse import urljoin
from sqlalchemy import func

# -------------------------------------------------------------------
# Klasörler
# -------------------------------------------------------------------
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
STATIC_DIR.mkdir(exist_ok=True, parents=True)

# -------------------------------------------------------------------
# FastAPI & CORS
# -------------------------------------------------------------------
app = FastAPI(title="AI Image Editor Backend", version="1.0.0")

origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def on_startup():
    init_db()
    print(f"[FAL] model: {settings.FAL_MODEL}  endpoint: {settings.FAL_ENDPOINT}")

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

# -------------------------------------------------------------------
# Yardımcılar
# -------------------------------------------------------------------
def _safe_unlink(p: str | Path | None) -> None:
    try:
        if not p:
            return
        path = Path(p)
        if path.exists():
            path.unlink(missing_ok=True)
    except Exception:
        pass

# bu fonksiyon fal.run'e base64 data-URL formatında resim gönderiyor
# (küçük resimler için uygun, büyük resimler için değil)    
#*******************************************************************************************************
def _image_to_data_url(image_path: Path) -> str:
    """Yerel dosyayı base64 data-URL'e çevirir."""
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "application/octet-stream"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# bu fonksiyon fal.run'e istek atar ve sonucu bekler
# ve hata durumlarını işler
# POLLING vs SYNC (POLL_MAX_WAIT ile sınırlandırılmış ve POLL_INTERVAL ile bekleme aralığı ayarlanabilir)
#*******************************************************************************************************
def _fal_infer_sync(model: str, image_path: Path, prompt: str) -> str:
    """
    fal.run'e bu modelin beklediği şekilde JSON body ile istek atar.
    Giriş: {"prompt": "...", "image_urls": ["data:<mime>;base64,<...>"]}
    Çıkış: {"images": [{"url": "..."}], ...}
    """
    if not settings.FAL_API_KEY:
        raise RuntimeError("FAL_API_KEY is missing in .env")

    endpoint = settings.FAL_ENDPOINT.rstrip("/")
    url = f"{endpoint}/{model.lstrip('/')}"
    headers = {
        "Authorization": f"Key {settings.FAL_API_KEY}",
        "Content-Type": "application/json",
    }

    data_url = _image_to_data_url(image_path)
    payload = {
        "prompt": prompt,
        "image_urls": [data_url],  # model top-level bekliyor
    }

    # TÜM istek ve polling bu bloğun İÇİNDE gerçekleşiyor
    with httpx.Client(timeout=settings.FAL_TIMEOUT) as client:
        r = client.post(url, headers=headers, json=payload)

        if r.status_code == 200:
            pp = r.json()
            images = pp.get("images") or []
            if images and isinstance(images[0], dict) and "url" in images[0]:
                return images[0]["url"]
            raise RuntimeError(f"no image url in response (200): {pp}")

        if r.status_code == 202:
            poll_url = r.headers.get("Location")
            if not poll_url:
                try:
                    pp = r.json()
                except Exception:
                    raise RuntimeError(f"no poll url (202): {r.text[:300]}")
                poll_url = pp.get("poll_url") or pp.get("status_url") or pp.get("result_url")
            if not poll_url:
                raise RuntimeError(f"no poll url (202): {r.text[:300]}")

            waited = 0.0
            while waited < settings.POLL_MAX_WAIT:
                pr = client.get(poll_url, headers={"Authorization": f"Key {settings.FAL_API_KEY}"})
                if pr.status_code not in (200, 202):
                    raise RuntimeError(f"poll failed {pr.status_code}: {pr.text[:300]}")
                pp = pr.json()

                images = pp.get("images") or []
                if images and isinstance(images[0], dict) and "url" in images[0]:
                    return images[0]["url"]

                status = (pp.get("status") or pp.get("state") or "").lower()
                if status in ("failed", "error"):
                    raise RuntimeError(f"fal job failed: {pp}")
                if status in ("succeeded", "completed", "done", "success"):
                    raise RuntimeError(f"completed but no image url: {pp}")

                time.sleep(settings.POLL_INTERVAL)
                waited += settings.POLL_INTERVAL

            raise RuntimeError("fal polling timeout")

        # 4xx/5xx
        raise RuntimeError(f"fal error {r.status_code}: {r.text[:300]}")

# Bu fonksiyon verilen URL'den resmi indirip belirtilen çıkış yoluna kaydeder
#*******************************************************************************************************
def _download_to_static(url: str, out_path: Path) -> None:
    """Deprecated: use _store_result(url, out_path) instead."""
    _store_result(url, out_path)

def _store_result(url: str, out_path: Path) -> str:
    """
    Çıktı URL'ini indirir ve storage backend'e kaydeder.
    - local: static/ altına yazar ve "/static/<file>" döner
    - s3: configured bucket'a yükler ve public URL döner
    """
    with httpx.Client(timeout=settings.FAL_TIMEOUT) as client:
        rr = client.get(url)
        rr.raise_for_status()
        content = rr.content

    if (settings.STORAGE_BACKEND or "local").lower() == "s3":
        # Lazy import to avoid hard dependency in local dev
        try:
            import boto3  # type: ignore
        except Exception as e:
            raise RuntimeError("boto3 is required for S3 storage; install and set STORAGE_BACKEND=s3") from e

        if not settings.S3_BUCKET:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")

        key = f"results/{out_path.name}"
        session_kwargs = {}
        if settings.S3_REGION:
            session_kwargs["region_name"] = settings.S3_REGION
        s3_session = boto3.session.Session(**session_kwargs)
        client_kwargs = {}
        if settings.S3_ENDPOINT:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT
        if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            client_kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
        s3 = s3_session.client("s3", **client_kwargs)
        s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=mimetypes.guess_type(out_path.name)[0] or "application/octet-stream")

        # Build a public URL
        if settings.S3_PUBLIC_BASE_URL:
            base = settings.S3_PUBLIC_BASE_URL.rstrip("/")
            return f"{base}/{key}"
        # Fallback to standard AWS S3 URL if region known
        if settings.S3_REGION:
            return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"
        # As a last resort, try endpoint URL
        if settings.S3_ENDPOINT:
            base = settings.S3_ENDPOINT.rstrip("/")
            return f"{base}/{settings.S3_BUCKET}/{key}"
        # If none available, we can't produce a public URL reliably
        raise RuntimeError("Unable to construct S3 public URL; set S3_PUBLIC_BASE_URL or REGION/ENDPOINT")

    # Default: local storage
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(content)
    return f"/static/{out_path.name}"

# Job tablosundan prompt'u alır
#*******************************************************************************************************
def _get_job_prompt(job_id: str, session: Session) -> str:
    job = session.get(Job, job_id)
    return job.prompt if job else ""

# Bu fonksiyon arka planda çalışır, fal ile işleme yapar ve DB'yi günceller
#*******************************************************************************************************
def _process_job_with_fal(job_id: str, raw_path: Path, out_path: Path, session: Session):
    try:
        result_url = _fal_infer_sync(settings.FAL_MODEL, raw_path, prompt=_get_job_prompt(job_id, session))
        public_url = _store_result(result_url, out_path)

        job = session.get(Job, job_id)
        if job:
            job.status = "done"
            job.result_url = public_url
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()
    except Exception as e:
        job = session.get(Job, job_id)
        if job:
            job.status = "error"
            job.error = str(e)
            job.updated_at = datetime.utcnow()
            session.add(job)
            session.commit()

# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------

#-----------MAIN API ENDPOINT 1---------------------------------------------------------------
#---------------------------------------------------------------------------------------------
# Job oluşturma endpointi
#*******************************************************************************************************
@app.post("/api/jobs", response_model=JobOut)
async def create_job(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not image.filename:
        raise HTTPException(status_code=400, detail="No file name")
    if not settings.FAL_API_KEY:
        raise HTTPException(status_code=500, detail="FAL_API_KEY not set in .env")

    job_id = str(uuid4())
    suffix = Path(image.filename).suffix or ".png"
    raw_path = UPLOAD_DIR / f"{job_id}_raw{suffix}"
    out_path = STATIC_DIR / f"{job_id}_out{suffix}"

    with raw_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    job = Job(
        id=job_id,
        prompt=prompt,
        status="processing",
        raw_path=str(raw_path),
        out_path=str(out_path),
    )
    session.add(job)
    session.commit()

    background_tasks.add_task(_process_job_with_fal, job_id, raw_path, out_path, session)

    return JobOut(
        job_id=job.id,
        status=job.status,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        prompt=job.prompt
    )

#-----------MAIN API ENDPOINT 2---------------------------------------------------------------
#---------------------------------------------------------------------------------------------
# Job detay endpointi (ID ile)
#*******************************************************************************************************
@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobOut(
        job_id=job.id,
        status=job.status,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        prompt=job.prompt
    )


#-----------MAIN API ENDPOINT 3---------------------------------------------------------------
#---------------------------------------------------------------------------------------------
# Tüm jobları listeleme endpointi (basit, sayfalama yok)
#*******************************************************************************************************
@app.get("/api/jobs", response_model=List[JobListItem])
def list_jobs(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
    return [
        JobListItem(job_id=j.id, status=j.status, result_url=j.result_url, created_at=j.created_at, prompt=j.prompt)
        for j in jobs
    ]


#-----------ALTERNATIF API ENDPOINT---------------------------------------------------------------
#---------------------------------------------------------------------------------------------
# job silme endpointi (safe unlink ile dosyaları da siler)
#*******************************************************************************************************
@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
        # dosyaları temizle
    _safe_unlink(job.raw_path)
    _safe_unlink(job.out_path)

    session.delete(job)
    session.commit()
    return {"detail": "Job deleted"}


#-----------ALTERNATIF API ENDPOINT---------------------------------------------------------------
#---------------------------------------------------------------------------------------------
# Sonuç dosyasını indirme endpointi (redirect veya local dosya)
#*******************************************************************************************************
@app.get("/api/jobs/{job_id}/download")
def download_job_result(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.result_url:
        raise HTTPException(status_code=400, detail="Job has no result yet")

    ru = job.result_url
    # tam URL ise 
    if ru.startswith("http://") or ru.startswith("https://"):
        return RedirectResponse(url=ru)

    # /static/xyz_out.png gibi ise 
    if ru.startswith("/static/"):
        filename = ru.split("/static/")[-1]
        path = STATIC_DIR / filename
        if not path.exists():
            raise HTTPException(status_code=404, detail="Result file not found")
        # indirme için filename set edilir
        return FileResponse(path, filename=filename, media_type="application/octet-stream")

   
    return RedirectResponse(url=ru)
