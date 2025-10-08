# API’nin dışarı döndüğü Pydantic şemaları

from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

# JobOut'un API yanıtı için şeması (örneğin /api/jobs, /api/jobs/{job_id})
class JobOut(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    prompt: str

# JobListItem'ın API yanıtı için şeması (örneğin /api/jobs listesi)
class JobListItem(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    prompt: str
    created_at: datetime
