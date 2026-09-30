import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.gst_copilot.db.models import Organization, User
import uuid

async def seed():
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/gst_copilot_dev")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        org_id = uuid.UUID("3cc6ae2b-d63a-4f7e-bbc2-e89e943f6f86")
        org = Organization(id=org_id, name="Test Org")
        session.add(org)
        
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            organization_id=org_id
        )
        session.add(user)
        await session.commit()
        print("Seeded successfully")

if __name__ == "__main__":
    asyncio.run(seed())
