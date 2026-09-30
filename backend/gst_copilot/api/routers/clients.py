from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from ..dependencies import get_db, get_active_organization, get_current_user
from ...services.audit import record as audit
from ..schemas import ClientCreate, ClientResponse, RegistrationCreate, RegistrationResponse, PeriodCreate, PeriodResponse
from ...db.models import Client, GSTRegistration, FilingPeriod, User

router = APIRouter(tags=["clients"])

@router.post("/clients", response_model=ClientResponse)
async def create_client(client_in: ClientCreate, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    client = Client(name=client_in.name, organization_id=org_id)
    db.add(client)
    await db.flush()
    audit(db, org_id, user.id, 'client_created', 'client', client.id, None, client.name)
    await db.commit()
    await db.refresh(client)
    return client

@router.get("/clients", response_model=List[ClientResponse])
async def list_clients(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.organization_id == org_id))
    return result.scalars().all()

@router.post("/clients/{client_id}/registrations", response_model=RegistrationResponse)
async def create_registration(client_id: UUID, reg_in: RegistrationCreate, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client or client.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Client not found")
        
    # Enforce uniqueness
    existing = await db.execute(select(GSTRegistration).where(GSTRegistration.client_id == client_id, GSTRegistration.gstin == reg_in.gstin))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="GSTIN already registered for this client")

    reg = GSTRegistration(client_id=client_id, gstin=reg_in.gstin, legal_name=reg_in.legal_name)
    db.add(reg)
    await db.flush()
    audit(db, org_id, user.id, 'registration_created', 'registration', reg.id, None, f'{client.name}: {reg.gstin}')
    await db.commit()
    await db.refresh(reg)
    return reg

@router.get("/clients/{client_id}/registrations", response_model=List[RegistrationResponse])
async def list_registrations(client_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client or client.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Client not found")
        
    result = await db.execute(select(GSTRegistration).where(GSTRegistration.client_id == client_id))
    return result.scalars().all()

@router.post("/registrations/{registration_id}/periods", response_model=PeriodResponse)
async def create_period(registration_id: UUID, period_in: PeriodCreate, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Authorize
    result = await db.execute(select(GSTRegistration).join(Client).where(GSTRegistration.id == registration_id, Client.organization_id == org_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
        
    existing = await db.execute(select(FilingPeriod).where(FilingPeriod.registration_id == registration_id, FilingPeriod.period_code == period_in.period_code))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Period already exists for this registration")

    period = FilingPeriod(registration_id=registration_id, period_code=period_in.period_code)
    db.add(period)
    await db.flush()
    audit(db, org_id, user.id, 'period_created', 'filing_period', period.id, period.id, period.period_code)
    await db.commit()
    await db.refresh(period)
    return period

@router.get("/registrations/{registration_id}/periods", response_model=List[PeriodResponse])
async def list_periods(registration_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GSTRegistration).join(Client).where(GSTRegistration.id == registration_id, Client.organization_id == org_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Registration not found")
        
    result = await db.execute(select(FilingPeriod).where(FilingPeriod.registration_id == registration_id))
    return result.scalars().all()

@router.get("/periods/{period_id}", response_model=PeriodResponse)
async def get_period(period_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    period = await db.get(FilingPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
    # Authorize via registration → client → org
    result = await db.execute(
        select(GSTRegistration).join(Client).where(
            GSTRegistration.id == period.registration_id,
            Client.organization_id == org_id
        )
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Period not found")
    return period
