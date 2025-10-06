# app/db.py
from sqlmodel import SQLModel, create_engine, Session
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from .config import settings, BASE_DIR

#BASE_DIR = Path(__file__).resolve().parent.parent

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
