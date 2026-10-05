"""Client requests: upload links (no client login), client contact details, and reminder drafts.

Upload links: a random token is shown once; only its SHA-256 is stored. Links expire, have a use limit and can be
revoked. Files arrive as PREVIEW imports attributed to the staff member who created the link; staff still review
and commit them. Reminders are drafts: the app builds the text and mailto / WhatsApp links, and the user sends them
from their own mail or WhatsApp. The app never sends messages.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_active_organization, get_current_user
from .board import _purchase_cell, _sales_cell
from .sales import owned_period, store_sales_upload
from ...config import settings
from ...db.models import Client, FilingPeriod, GSTRegistration, Organization, UploadLink, User
from ...parser import parse_suppliers
from ...services.audit import record as audit
from ...services.import_service import process_upload

router = APIRouter(tags=['client requests'])
KIND_LABEL = {'sales': 'sales register', 'purchase': 'purchase register'}
MAX_BYTES = 5 * 1024 * 1024

def _hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def _link_view(l: UploadLink):
    now = datetime.now(timezone.utc)
    state = 'revoked' if l.revoked_at else 'expired' if l.expires_at <= now else 'used_up' if l.uses >= l.max_uses else 'active'
    return {'id': str(l.id), 'kind': l.kind, 'expires_at': l.expires_at.isoformat(), 'uses': l.uses, 'max_uses': l.max_uses, 'state': state, 'created_at': l.created_at.isoformat()}

async def _client_of(db, period):
    return (await db.execute(select(Client).join(GSTRegistration).where(GSTRegistration.id == period.registration_id))).scalars().first()

# --- Staff side ---------------------------------------------------------------------------------

class LinkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['sales', 'purchase']
    days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=5, ge=1, le=20)

async def _create_link(db, period, org_id, user, data: LinkInput):
    token = secrets.token_urlsafe(24)
    link = UploadLink(period_id=period.id, kind=data.kind, token_hash=_hash(token), created_by=user.id, max_uses=data.max_uses,
                      expires_at=datetime.now(timezone.utc) + timedelta(days=data.days))
    db.add(link); await db.flush()
    audit(db, org_id, user.id, 'upload_link_created', 'upload_link', link.id, period.id, f'{data.kind}, {data.days} day(s), {data.max_uses} use(s)')
    return link, token

@router.post('/periods/{period_id}/upload-links')
async def create_link(period_id: UUID, data: LinkInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, period_id, org_id)
    link, token = await _create_link(db, period, org_id, user, data)
    await db.commit()
    return _link_view(link) | {'path': f'/u/{token}', 'notice': 'Copy the link now: it is shown only once.'}

@router.get('/periods/{period_id}/upload-links')
async def list_links(period_id: UUID, org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, period_id, org_id)
    rows = (await db.execute(select(UploadLink).where(UploadLink.period_id == period.id).order_by(UploadLink.created_at.desc()))).scalars().all()
    return [_link_view(l) for l in rows]

@router.post('/upload-links/{link_id}/revoke')
async def revoke_link(link_id: UUID, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    link = (await db.execute(select(UploadLink).join(FilingPeriod).join(GSTRegistration).join(Client).where(UploadLink.id == link_id, Client.organization_id == org_id))).scalars().first()
    if not link: raise HTTPException(404, 'Link not found')
    if not link.revoked_at:
        link.revoked_at = datetime.now(timezone.utc)
        audit(db, org_id, user.id, 'upload_link_revoked', 'upload_link', link.id, link.period_id, link.kind)
        await db.commit()
    return _link_view(link)

class ContactInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contact_email: str | None = Field(default=None, max_length=254, pattern=r'^$|^[^@\s]+@[^@\s]+\.[^@\s]+$')
    contact_phone: str | None = Field(default=None, max_length=20, pattern=r'^$|^\+?[0-9 ]{8,18}$')

@router.patch('/clients/{client_id}/contact')
async def set_contact(client_id: UUID, data: ContactInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    client = (await db.execute(select(Client).where(Client.id == client_id, Client.organization_id == org_id))).scalars().first()
    if not client: raise HTTPException(404, 'Client not found')
    client.contact_email = (data.contact_email or '').strip() or None
    client.contact_phone = (data.contact_phone or '').strip() or None
    audit(db, org_id, user.id, 'client_contact_updated', 'client', client.id, None, 'contact details updated')  # no addresses in the audit text
    await db.commit()
    return {'contact_email': client.contact_email, 'contact_phone': client.contact_phone}

class ReminderInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    include_links: bool = True
    base_url: str = Field(default='', max_length=200, pattern=r'^$|^https?://[^\s/]+(:\d+)?$')

@router.post('/periods/{period_id}/reminder')
async def reminder(period_id: UUID, data: ReminderInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Draft (not send) a reminder listing what is still missing, optionally with fresh upload links."""
    period = await owned_period(db, period_id, org_id)
    client = await _client_of(db, period)
    firm = await db.get(Organization, org_id)
    sales, purchases = await _sales_cell(db, period.id), await _purchase_cell(db, period.id)
    missing = [k for k, cell in (('sales', sales), ('purchase', purchases)) if cell['tone'] == 'waiting' and 'Awaiting' in cell['label']]
    y, m = period.period_code.split('-')
    month = datetime(int(y), int(m), 1).strftime('%B %Y')
    if not missing:
        return {'missing': [], 'subject': None, 'body': None, 'mailto': None, 'whatsapp': None, 'note': f'Nothing is awaiting files for {month}.'}
    lines = []
    for kind in missing:
        line = f'- {KIND_LABEL[kind]} for {month}'
        if data.include_links:
            _, token = await _create_link(db, period, org_id, user, LinkInput(kind=kind))
            line += f': upload here {data.base_url}/u/{token} (valid 7 days)'
        lines.append(line)
    subject = f'{client.name}: GST documents needed for {month}'
    body = f'Dear {client.name},\n\nTo prepare your GST work for {month}, we still need:\n' + '\n'.join(lines) + f'\n\nThank you,\n{firm.name}'
    audit(db, org_id, user.id, 'reminder_drafted', 'filing_period', period.id, period.id, f"missing: {', '.join(missing)}; links: {'yes' if data.include_links else 'no'}")
    await db.commit()
    phone = ''.join(ch for ch in (client.contact_phone or '') if ch.isdigit())
    return {'missing': missing, 'subject': subject, 'body': body, 'to_email': client.contact_email, 'to_phone': client.contact_phone,
            'mailto': f"mailto:{quote(client.contact_email or '')}?subject={quote(subject)}&body={quote(body)}",
            'whatsapp': f'https://wa.me/{phone}?text={quote(body)}' if phone else f'https://wa.me/?text={quote(body)}',
            'note': 'Draft only: opening these links starts a message in your own mail or WhatsApp app. GST Helper does not send anything.'}

# --- Public side (no login: the token is the credential) -------------------------------------------

async def _valid_link(db, token: str, lock=False):
    q = select(UploadLink).where(UploadLink.token_hash == _hash(token))
    if lock: q = q.with_for_update()
    link = (await db.execute(q)).scalars().first()
    if not link: raise HTTPException(404, 'This upload link is not valid.')
    if _link_view(link)['state'] != 'active': raise HTTPException(410, 'This upload link has expired, been revoked or been used up. Ask your accountant for a new one.')
    return link

@router.get('/public/upload/{token}')
async def public_link(token: str, db: AsyncSession = Depends(get_db)):
    link = await _valid_link(db, token)
    period = await db.get(FilingPeriod, link.period_id)
    client = await _client_of(db, period)
    firm = await db.get(Organization, client.organization_id)
    return {'firm': firm.name, 'client': client.name, 'period_code': period.period_code, 'kind': link.kind, 'what': KIND_LABEL[link.kind],
            'expires_at': link.expires_at.isoformat(), 'uses_left': link.max_uses - link.uses}

@router.post('/public/upload/{token}')
async def public_upload(token: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    link = await _valid_link(db, token, lock=True)  # the row lock makes the use count exact under concurrent uploads
    period = await db.get(FilingPeriod, link.period_id)
    client = await _client_of(db, period)
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES: raise HTTPException(413, 'File exceeds 5 MiB')
    link.uses += 1
    await db.flush()
    via = f' (uploaded by the client via link {str(link.id)[:8]})'
    if link.kind == 'sales':
        await store_sales_upload(db, period, client.organization_id, link.created_by, file.filename, content, via)
    else:
        try:
            batch = await process_upload(db=db, org_id=client.organization_id, period_id=period.id, source_type='purchase', original_filename=f'{file.filename or "purchase.csv"} (client upload)',
                                         file_content=content, storage_dir=settings.STORAGE_DIR, valid_suppliers=parse_suppliers(Path(__file__).resolve().parents[4] / 'sample_data/v1/suppliers.csv'))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        audit(db, client.organization_id, link.created_by, 'import_uploaded', 'import_batch', batch.id, period.id, f'purchase: {batch.record_count} rows, {batch.invalid_count} invalid{via}')
        await db.commit()
    return {'status': 'received', 'message': f'Thank you. Your {KIND_LABEL[link.kind]} for {period.period_code} was received; your accountant will review it.'}
