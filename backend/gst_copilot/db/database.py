from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from ..config import settings

# ponytail: small pool sized for Supabase's free session pooler; raise pool_size with a bigger plan.
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=5, max_overflow=5, pool_pre_ping=True, connect_args=settings.db_connect_args)
AsyncSessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
