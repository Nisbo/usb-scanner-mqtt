"""Small shared GitHub metadata cache and actionable, sanitized update errors."""
import hashlib
import math
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request

API = 'https://api.github.com/repos/Nisbo/usb-scanner-mqtt'
CACHE_DIR = Path('/var/lib/usb-scanner-mqtt/update-cache')


class UpdateError(ValueError):
    def __init__(self, message, code, retry_at=None):
        super().__init__(message)
        self.code, self.retry_at = code, retry_at

    def __str__(self):
        message = super().__str__()
        if self.retry_at:
            message += ' Try again after ' + datetime.fromtimestamp(self.retry_at, timezone.utc).isoformat() + '.'
        return message


def _read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, value):
    temporary = None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.metadata-', dir=CACHE_DIR)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
        # Bound storage independently of the number of development revisions.
        entries = sorted(CACHE_DIR.glob('*.json'), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in entries[128:]:
            if old.name != 'rate-limit.json':
                old.unlink(missing_ok=True)
    except OSError:
        pass  # Read-only shell checks can still work without a writable cache.
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def _number(value, default=0):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else default
    except (ValueError, TypeError):
        return default


def github(path):
    cache_path = CACHE_DIR / (hashlib.sha256(path.encode()).hexdigest() + '.json')
    now = time.time()
    cached = _read(cache_path)
    if 'data' in cached and cached.get('path') == path and 0 <= now - _number(cached.get('saved')) < _number(cached.get('ttl')):
        return cached['data']
    blocked = _read(CACHE_DIR / 'rate-limit.json')
    if _number(blocked.get('retry_at')) > now:
        raise UpdateError('GitHub request limit reached. Please wait before checking again.', 'rate_limit', blocked['retry_at'])
    request = urllib.request.Request(API + path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'usb-scanner-mqtt-updater'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise UpdateError('GitHub returned invalid update metadata.', 'metadata')
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError):
            raise UpdateError('GitHub returned invalid update metadata.', 'metadata') from None
    except urllib.error.HTTPError as error:
        headers = error.headers or {}
        try:
            limited = b'rate limit' in error.read(4096).lower()
        except OSError:
            limited = False
        finally:
            error.close()
        if error.code == 429 or (error.code == 403 and (headers.get('X-RateLimit-Remaining') == '0' or headers.get('Retry-After') or limited)):
            retry_at = max(now + max(1, _number(headers.get('Retry-After'), 60)), _number(headers.get('X-RateLimit-Reset')) + 1)
            _write(CACHE_DIR / 'rate-limit.json', {'retry_at': retry_at})
            raise UpdateError('GitHub request limit reached. Please wait before checking again.', 'rate_limit', retry_at) from None
        if error.code == 404:
            raise UpdateError('The selected update channel or release is not available on GitHub.', 'not_found') from None
        raise UpdateError('GitHub rejected the update request (HTTP ' + str(error.code) + '). Try again later.', 'http') from None
    except OSError:
        raise UpdateError('Update check failed. Cannot reach GitHub. Check Internet access and try again.', 'network') from None
    # SHA comparisons and tag resolutions do not change in our release workflow.
    ttl = 86400 if path.startswith('/compare/') or (path.startswith('/commits/') and path != '/commits/dev') else 30
    _write(cache_path, {'path': path, 'saved': now, 'ttl': ttl, 'data': value})
    return value
