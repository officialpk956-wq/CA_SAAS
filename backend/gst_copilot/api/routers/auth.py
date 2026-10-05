"""Login, logout and the current user. Sessions live in an HttpOnly, SameSite=Strict cookie."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies import get_current_user, get_db
from ...auth import LoginThrottle, new_session_token, token_hash, verify_password
from ...config import settings
from ...db.models import Organization, User, UserSession
from ...services.audit import record as audit

router = APIRouter(tags=['auth'])
throttle = LoginThrottle(settings.LOGIN_MAX_FAILURES, settings.LOGIN_LOCKOUT_MINUTES * 60)
WRONG = 'Email or password is incorrect.'

class LoginInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

async def _me(db, user):
    org = await db.get(Organization, user.organization_id)
    return {'id': str(user.id), 'email': user.email, 'display_name': user.display_name or user.email.split('@')[0], 'role': user.role,
            'firm': org.name if org else None, 'require_separate_approver': bool(org and org.require_separate_approver)}

@router.post('/auth/login')
async def login(data: LoginInput, response: Response, db: AsyncSession = Depends(get_db)):
    email = data.email.strip().lower()
    wait = throttle.locked_for(email)
    if wait: raise HTTPException(429, f'Too many failed attempts. Try again in {wait // 60 + 1} minute(s).')
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    # verify_password runs even for unknown emails, so response time doesn't reveal which accounts exist.
    ok = verify_password(data.password, user.password_hash if user else None) and user is not None and user.is_active
    if not ok:
        throttle.fail(email)
        raise HTTPException(401, WRONG)
    throttle.succeed(email)
    token = new_session_token()
    db.add(UserSession(user_id=user.id, token_hash=token_hash(token), expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_HOURS)))
    audit(db, user.organization_id, user.id, 'user_login', 'user', user.id, None, user.email)
    await db.commit()
    response.set_cookie(settings.SESSION_COOKIE, token, max_age=settings.SESSION_HOURS * 3600, httponly=True, samesite='strict', secure=settings.COOKIE_SECURE, path='/')
    return await _me(db, user)

@router.post('/auth/logout')
async def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(settings.SESSION_COOKIE)
    session = (await db.execute(select(UserSession).where(UserSession.token_hash == token_hash(token)))).scalars().first()
    session.revoked_at = datetime.now(timezone.utc)
    audit(db, user.organization_id, user.id, 'user_logout', 'user', user.id, None, user.email)
    await db.commit()
    response.delete_cookie(settings.SESSION_COOKIE, path='/', httponly=True, samesite='strict', secure=settings.COOKIE_SECURE)
    return {'status': 'logged out'}

@router.get('/auth/me')
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _me(db, user)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)

@router.post('/auth/password')
async def change_password(data: PasswordChange, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Change your own password. Ends every other session; this browser stays signed in."""
    from ...auth import hash_password
    key = user.email.lower()
    wait = throttle.locked_for(key)
    if wait: raise HTTPException(429, f'Too many failed attempts. Try again in {wait // 60 + 1} minute(s).')
    if not verify_password(data.current_password, user.password_hash):
        throttle.fail(key)
        raise HTTPException(400, 'Current password is incorrect.')
    if data.new_password == data.current_password: raise HTTPException(400, 'Choose a password different from the current one.')
    try: new_hash = hash_password(data.new_password)
    except ValueError as exc: raise HTTPException(400, str(exc))
    db_user = await db.get(User, user.id)
    db_user.password_hash = new_hash
    current = token_hash(request.cookies.get(settings.SESSION_COOKIE, ''))
    others = (await db.execute(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.token_hash != current))).scalars().all()
    for s in others: s.revoked_at = datetime.now(timezone.utc)
    audit(db, user.organization_id, user.id, 'password_changed', 'user', user.id, None, f'{len(others)} other session(s) ended')
    await db.commit()
    return {'status': 'changed', 'other_sessions_ended': len(others)}
