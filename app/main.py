# FastAPI uygulamasının giriş noktası (route’lar burada)


from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import shutil, time

from sqlmodel import select, Session

from .db import init_db, get_session, BASE_DIR
from .models import Job
from .schemas import JobOut, JobListItem

UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)
STATIC_DIR.mkdir(exist_ok=True, parents=True)

class Settings(BaseSettings):
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    FAL_API_KEY: Optional[str] = None
    class Config:
        env_file = BASE_DIR / ".env"

settings = Settings()

app = FastAPI(title="AI Image Editor Backend", version="0.1.0")

# CORS
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# statik çıktı servisi
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

def _simulate_processing(src: Path, dst: Path) -> None:
    """
    Gerçek entegrasyon öncesi: kısa 'işleme' simülasyonu.
    Burayı ileride fal.ai çağrısı ile değiştirirsin.
    """
    time.sleep(1.2)
    shutil.copyfile(src, dst)

def _process_job(job_id: str, raw_path: Path, out_path: Path, session: Session):
    try:
        _simulate_processing(raw_path, out_path)
        job = session.get(Job, job_id)
        if job:
            job.status = "done"
            job.result_url = f"/static/{out_path.name}"
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

@app.post("/api/jobs", response_model=JobOut)
async def create_job(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not image.filename:
        raise HTTPException(status_code=400, detail="No file name")

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

    # arka planda işleme
    background_tasks.add_task(_process_job, job_id, raw_path, out_path, session)

    return JobOut(
        job_id=job.id,
        status=job.status,
        result_url=job.result_url,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )

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
    )

@app.get("/api/jobs", response_model=List[JobListItem])
def list_jobs(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
    return [
        JobListItem(job_id=j.id, status=j.status, result_url=j.result_url, created_at=j.created_at)
        for j in jobs
    ]
