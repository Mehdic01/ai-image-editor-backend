#Tablolar (ORM modelleri) – Job tablosu burada

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, String

class Job(SQLModel, table=True):
    id: str = Field(primary_key=True, index=True)
    prompt: str
    status: str = Field(default="processing", index=True)  # processing | done | error
    result_url: Optional[str] = None
    error: Optional[str] = None
    raw_path: Optional[str] = None
    out_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

