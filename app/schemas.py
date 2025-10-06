# API’nin dışarı döndüğü Pydantic şemaları

from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

class JobOut(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class JobListItem(BaseModel):
    job_id: str
    status: str
    result_url: Optional[str] = None
    created_at: datetime
