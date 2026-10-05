"""Firm people: users and roles, the separate-approver policy, and who is assigned to each period.

Roles: owner (everything, manages people), reviewer (approves, confirms legal values), preparer (prepares;
cannot approve, reopen or confirm legal values). Owners manage users; everyone can see the team to assign work.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_db, get_active_organization, get_current_user, require_role
from .sales import owned_period
from ...auth import hash_password
from ...db.models import Organization, User, UserSession
from ...services.audit import record as audit

router = APIRouter(tags=['firm'])
Role = Literal['owner', 'reviewer', 'preparer']

def user_view(u: User):
    return {'id': str(u.id), 'email': u.email, 'display_name': u.display_name or u.email.split('@')[0], 'role': u.role, 'is_active': u.is_active}

@router.get('/firm')
async def firm(org_id: UUID = Depends(get_active_organization), db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, org_id)
    users = (await db.execute(select(User).where(User.organization_id == org_id).order_by(User.created_at))).scalars().all()
    return {'name': org.name, 'require_separate_approver': org.require_separate_approver, 'users': [user_view(u) for u in users]}

class SettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    require_separate_approver: bool

@router.patch('/firm/settings')
async def settings(data: SettingsInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(user, 'owner')
    org = await db.get(Organization, org_id)
    org.require_separate_approver = data.require_separate_approver
    audit(db, org_id, user.id, 'firm_policy_changed', 'organization', org_id, None, f'separate approver: {"on" if data.require_separate_approver else "off"}')
    await db.commit()
    return await firm(org_id, db)

class NewUser(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    display_name: str = Field(min_length=1, max_length=80)
    role: Role
    initial_password: str = Field(min_length=10, max_length=200)

@router.post('/firm/users')
async def add_user(data: NewUser, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(user, 'owner')
    email = data.email.strip().lower()
    if (await db.execute(select(User.id).where(func.lower(User.email) == email))).first(): raise HTTPException(409, 'A user with that email already exists.')
    try: password_hash = hash_password(data.initial_password)
    except ValueError as exc: raise HTTPException(400, str(exc))
    new = User(email=email, organization_id=org_id, password_hash=password_hash, role=data.role, display_name=data.display_name.strip())
    db.add(new); await db.flush()
    audit(db, org_id, user.id, 'user_added', 'user', new.id, None, f'{email} as {data.role}')  # never the password
    await db.commit()
    return user_view(new)

class UserChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role | None = None
    is_active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)

@router.patch('/firm/users/{user_id}')
async def change_user(user_id: UUID, data: UserChange, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_role(user, 'owner')
    await db.execute(select(Organization).where(Organization.id == org_id).with_for_update())  # serialise owner-count checks
    target = (await db.execute(select(User).where(User.id == user_id, User.organization_id == org_id))).scalars().first()
    if not target: raise HTTPException(404, 'User not found')
    losing_owner = target.role == 'owner' and ((data.role and data.role != 'owner') or data.is_active is False)
    if losing_owner:
        owners = (await db.execute(select(func.count(User.id)).where(User.organization_id == org_id, User.role == 'owner', User.is_active.is_(True)))).scalar_one()
        if owners <= 1: raise HTTPException(400, 'The firm must keep at least one active owner.')
    changes = []
    if data.role and data.role != target.role: changes.append(f'role {target.role} → {data.role}'); target.role = data.role
    if data.display_name: target.display_name = data.display_name.strip()
    if data.is_active is not None and data.is_active != target.is_active:
        target.is_active = data.is_active; changes.append('enabled' if data.is_active else 'disabled')
        if not data.is_active:  # end their sessions now
            await db.execute(update(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, org_id, user.id, 'user_changed', 'user', target.id, None, f"{target.email}: {', '.join(changes) or 'name updated'}")
    await db.commit()
    return user_view(target)

class AssignInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: UUID | None

@router.post('/periods/{period_id}/assign')
async def assign(period_id: UUID, data: AssignInput, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    period = await owned_period(db, period_id, org_id, lock=True)
    target = None
    if data.user_id:
        target = (await db.execute(select(User).where(User.id == data.user_id, User.organization_id == org_id, User.is_active.is_(True)))).scalars().first()
        if not target: raise HTTPException(404, 'Active user not found in this firm')
    period.assignee_id = target.id if target else None
    audit(db, org_id, user.id, 'period_assigned', 'filing_period', period.id, period.id, f'assigned to {target.email}' if target else 'unassigned')
    await db.commit()
    return {'period_id': str(period.id), 'assignee': user_view(target) if target else None}


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    new_password: str = Field(min_length=10, max_length=200)

@router.post('/firm/users/{user_id}/password')
async def reset_password(user_id: UUID, data: PasswordReset, org_id: UUID = Depends(get_active_organization), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Owner sets a temporary password for another member and ends all their sessions. Use /auth/password for yourself."""
    require_role(user, 'owner')
    target = (await db.execute(select(User).where(User.id == user_id, User.organization_id == org_id))).scalars().first()
    if not target: raise HTTPException(404, 'User not found')
    if target.id == user.id: raise HTTPException(400, 'Change your own password from your account page.')
    try: target.password_hash = hash_password(data.new_password)
    except ValueError as exc: raise HTTPException(400, str(exc))
    await db.execute(update(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, org_id, user.id, 'password_reset_by_owner', 'user', target.id, None, target.email)  # never the password
    await db.commit()
    return {'status': 'reset', 'user': user_view(target)}
