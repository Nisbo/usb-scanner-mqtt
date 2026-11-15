"""Optional dashboard authentication; password hashes and session state stay on the server."""
import hashlib
import hmac
import secrets
import threading
import time

ITERATIONS = 600_000
IDLE_SECONDS = 30 * 60
COOKIE = 'scanner_session'


def password_hash(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 1024:
        raise ValueError('Das Passwort muss 8 bis 1024 Zeichen lang sein.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2-sha256${ITERATIONS}${salt}${digest}'


def valid_hash(value):
    try:
        algorithm, iterations, salt, digest = value.split('$')
        return (algorithm == 'pbkdf2-sha256' and int(iterations) == ITERATIONS
                and len(salt) == 32 and len(digest) == 64
                and len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32)
    except (AttributeError, ValueError, TypeError):
        return False


def verify(password, encoded):
    if not isinstance(password, str) or len(password) > 1024 or not valid_hash(encoded):
        return False
    _, iterations, salt, expected = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    return hmac.compare_digest(actual, expected)


class Auth:
    def __init__(self, auto_logout=False):
        self.lock = threading.Lock()
        self.auto_logout = auto_logout
        self.sessions = {}
        self.failures = 0
        self.blocked_until = 0

    def bind(self, web, revoke=False):
        """Reuse login state across receiver reloads only while access settings match."""
        access = (web.get('auth_enabled', False), web.get('password_hash', ''),
                  web.get('auto_logout', False))
        with self.lock:
            if revoke or getattr(self, '_access', None) != access:
                self.sessions.clear()
            self._access = access
            self.auto_logout = access[2]

    def valid(self, session, touch=False):
        with self.lock:
            now = time.monotonic()
            self.sessions = {key: value for key, value in self.sessions.items()
                             if value is None or value > now}
            if session not in self.sessions:
                return False
            if touch and self.auto_logout:
                self.sessions[session] = now + IDLE_SECONDS
            return True

    def login(self, password, encoded, issue_session=True):
        # One bounded, global backoff also limits distributed guesses and hashing work.
        with self.lock:
            now = time.monotonic()
            if now < self.blocked_until:
                return None, 429
            if not verify(password, encoded):
                self.failures += 1
                self.blocked_until = now + min(300, 2 ** min(self.failures, 9))
                return None, 401
            self.failures = 0
            self.blocked_until = 0
            if not issue_session:
                return True, 200
            session = secrets.token_urlsafe(32)
            self.sessions[session] = now + IDLE_SECONDS if self.auto_logout else None
            # Bound memory and expire older sessions without displacing this login.
            self.sessions = dict(list(self.sessions.items())[-32:])
            return session, 200

    def logout(self, session):
        with self.lock:
            self.sessions.pop(session, None)

    def configure(self, auto_logout):
        with self.lock:
            self.auto_logout = auto_logout
            self.sessions.clear()
