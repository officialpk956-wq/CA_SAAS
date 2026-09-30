"""Firm account administration for the database in DATABASE_URL (defaults to the development database).

    python scripts/firm_admin.py set-password admin@demo.com       # prompts privately, twice; nothing is echoed or logged
    python scripts/firm_admin.py rename-firm admin@demo.com "GST Helper Demo CA Firm"
    python scripts/firm_admin.py disable admin@demo.com             # blocks login and ends the user's sessions

Passwords are never passed on the command line (they would land in shell history).
"""
import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import func, select, update
from backend.gst_copilot.auth import MIN_PASSWORD_LENGTH, hash_password
from backend.gst_copilot.db.database import AsyncSessionLocal
from backend.gst_copilot.db.models import Organization, User, UserSession
from backend.gst_copilot.services.audit import record as audit

async def find_user(db, email):
    user = (await db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))).scalars().first()
    if not user: raise SystemExit(f'No user with email {email}')
    return user

async def end_sessions(db, user):
    await db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))

async def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('set-password').add_argument('email')
    rename = sub.add_parser('rename-firm'); rename.add_argument('email'); rename.add_argument('name')
    sub.add_parser('disable').add_argument('email')
    args = parser.parse_args()
    async with AsyncSessionLocal() as db:
        user = await find_user(db, args.email)
        org = await db.get(Organization, user.organization_id)
        if args.cmd == 'set-password':
            first = getpass.getpass(f'New password for {user.email} (min {MIN_PASSWORD_LENGTH} characters): ')
            if getpass.getpass('Repeat it: ') != first: raise SystemExit('Passwords did not match; nothing changed.')
            try: user.password_hash = hash_password(first)
            except ValueError as exc: raise SystemExit(f'{exc}; nothing changed.')
            user.is_active = True
            await end_sessions(db, user)  # other browsers must log in again with the new password
            audit(db, org.id, user.id, 'password_set', 'user', user.id, None, user.email)
            print(f'Password set for {user.email} ({org.name}). Existing sessions were ended.')
        elif args.cmd == 'rename-firm':
            old = org.name; org.name = args.name.strip()
            audit(db, org.id, user.id, 'firm_renamed', 'organization', org.id, None, f'{old} → {org.name}')
            print(f'Renamed "{old}" to "{org.name}".')
        else:
            user.is_active = False
            await end_sessions(db, user)
            audit(db, org.id, user.id, 'user_disabled', 'user', user.id, None, user.email)
            print(f'Disabled {user.email}; sessions ended.')
        await db.commit()

if __name__ == '__main__':
    asyncio.run(main())
