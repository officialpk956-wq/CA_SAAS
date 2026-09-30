import asyncio
import os
import sys
from pathlib import Path

# Add project root to path so we can run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from backend.gst_copilot.auth import hash_password
from backend.gst_copilot.db.database import AsyncSessionLocal
from backend.gst_copilot.db.models import Organization, User, Client, GSTRegistration, FilingPeriod
from sqlalchemy import select

FIRM_NAME = "GST Helper Demo CA Firm"
ADMIN_EMAIL = "admin@demo.com"

async def seed():
    """Idempotent: ensures the firm, its admin login and one fictional client/period exist.

    The admin gets a password only when SEED_ADMIN_PASSWORD is set (the E2E launcher sets a test-only value).
    For the development database, set the password privately with: python scripts/firm_admin.py set-password admin@demo.com
    """
    async with AsyncSessionLocal() as db:
        print("Seeding database...")
        user = (await db.execute(select(User).where(User.email == ADMIN_EMAIL))).scalars().first()
        org = await db.get(Organization, user.organization_id) if user else None
        if not org:
            org = Organization(name=FIRM_NAME)
            db.add(org)
            await db.flush()
            print("Created firm")
        if not user:
            user = User(email=ADMIN_EMAIL, organization_id=org.id)
            db.add(user)
            await db.flush()
            print("Created admin user (no password yet)")
        if os.environ.get("SEED_ADMIN_PASSWORD"):
            user.password_hash = hash_password(os.environ["SEED_ADMIN_PASSWORD"])
            print("Set admin password from SEED_ADMIN_PASSWORD")

        client = (await db.execute(select(Client).where(Client.name == "Fictional Client A", Client.organization_id == org.id))).scalars().first()
        if not client:
            client = Client(name="Fictional Client A", organization_id=org.id)
            db.add(client)
            await db.flush()
            print("Created Client")
        reg = (await db.execute(select(GSTRegistration).where(GSTRegistration.gstin == "DEMO-REG-001", GSTRegistration.client_id == client.id))).scalars().first()
        if not reg:
            reg = GSTRegistration(client_id=client.id, gstin="DEMO-REG-001", legal_name="Fictional Client A")
            db.add(reg)
            await db.flush()
            print("Created GST Registration")
        per = (await db.execute(select(FilingPeriod).where(FilingPeriod.period_code == "2026-08", FilingPeriod.registration_id == reg.id))).scalars().first()
        if not per:
            db.add(FilingPeriod(registration_id=reg.id, period_code="2026-08"))
            print("Created Filing Period")
        await db.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
