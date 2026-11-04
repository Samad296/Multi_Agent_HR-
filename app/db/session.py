from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.runtime_db_url, pool_pre_ping=True, pool_size=5, max_overflow=2)
admin_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=2, max_overflow=0)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)