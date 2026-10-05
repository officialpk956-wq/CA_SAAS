from datetime import datetime, timezone
import uuid
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..auth import token_hash
from ..config import settings
from ..db.database import AsyncSessionLocal
from ..db.models import User, UserSession

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """The user behind a valid, unexpired, unrevoked session cookie. Everything except health and login depends on this."""
    token = request.cookies.get(settings.SESSION_COOKIE)
    if token:
        row = (await db.execute(select(User).join(UserSession, UserSession.user_id == User.id).where(
            UserSession.token_hash == token_hash(token), UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(timezone.utc), User.is_active.is_(True)))).scalars().first()
        if row: return row
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in.")

ROLES = ('owner', 'reviewer', 'preparer')
APPROVERS = ('owner', 'reviewer')

def require_role(user: User, *roles: str):
    """403 unless the user's firm role is one of `roles`."""
    if user.role not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({user.role}) can't do this. Ask a{'n' if roles[0][0] in 'aeiou' else ''} {' or '.join(roles)}.")

async def get_active_organization(current_user: User = Depends(get_current_user)) -> uuid.UUID:
    return current_user.organization_id
