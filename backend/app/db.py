import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv(Path(__file__).resolve().parents[2] / '.env')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL.startswith('postgresql'):
    raise RuntimeError('DATABASE_URL must point to PostgreSQL. No fallback is supported.')
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10, connect_args={'connect_timeout':5})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    with SessionLocal() as db:
        yield db
