"""Password hashing, session tokens and login throttling. Standard library only.

Passwords: scrypt with a random per-user salt; stored as "scrypt$n$r$p$salt$hash".
Sessions: a random token goes to the browser in an HttpOnly cookie; only its SHA-256 is stored.
"""
import hashlib
import hmac
import secrets
import time

N, R, P, KEY_LEN = 2 ** 14, 8, 1, 64
MIN_PASSWORD_LENGTH = 10

def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH: raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=KEY_LEN)
    return f'scrypt${N}${R}${P}${salt.hex()}${digest.hex()}'

def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time comparison. With no stored hash, still does the work so timing doesn't reveal the account exists."""
    try:
        scheme, n, r, p, salt, digest = (stored or DUMMY_HASH).split('$')
        if scheme != 'scrypt': return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest)))
        return stored is not None and hmac.compare_digest(candidate, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

DUMMY_HASH = f'scrypt${N}${R}${P}$' + '00' * 16 + '$' + '00' * KEY_LEN

def new_session_token() -> str:
    return secrets.token_urlsafe(32)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

class LoginThrottle:
    """Locks an email after too many failures inside the lockout window.

    ponytail: in-process memory — each API worker counts separately and counts reset on restart. Move to the
    database or a shared store if several workers serve logins.
    """
    def __init__(self, attempts: int, lockout_seconds: int, clock=time.monotonic):
        self.attempts, self.lockout, self.clock = attempts, lockout_seconds, clock
        self.failures: dict[str, list[float]] = {}

    def locked_for(self, key: str) -> int:
        """Seconds remaining on a lock, or 0."""
        recent = [t for t in self.failures.get(key, []) if self.clock() - t < self.lockout]
        self.failures[key] = recent
        return int(self.lockout - (self.clock() - recent[-self.attempts])) + 1 if len(recent) >= self.attempts else 0

    def fail(self, key: str):
        self.failures.setdefault(key, []).append(self.clock())

    def succeed(self, key: str):
        self.failures.pop(key, None)
