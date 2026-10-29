import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

TYPES = ('ipv4', 'domain', 'url', 'md5', 'sha256')
FIELDS = ('indicator', 'type', 'confidence', 'source', 'first_seen')

def domain(value):
    value = value.rstrip('.').encode('idna').decode('ascii').lower()
    if len(value) > 253 or '.' not in value or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')):
        raise ValueError('invalid domain')
    return value

def normalize(row):
    if None in row or any(not isinstance(row.get(f), str) or not row[f].strip() for f in FIELDS):
        raise ValueError('missing fields or extra CSV columns')
    kind, value = row['type'].strip().lower(), row['indicator'].strip()
    if kind not in TYPES:
        raise ValueError('unknown type')
    try:
        if kind == 'ipv4':
            value = str(ipaddress.IPv4Address(value))
        elif kind == 'domain':
            value = domain(value)
        elif kind in ('md5', 'sha256'):
            if not re.fullmatch('[0-9a-fA-F]{%d}' % (32 if kind == 'md5' else 64), value):
                raise ValueError('incorrect hash length or non-hex characters')
            value = value.lower()
        else:
            if any(c.isspace() or ord(c) < 32 for c in value):
                raise ValueError('URL contains whitespace')
            url = urlsplit(value)
            if url.scheme.lower() not in ('http', 'https') or not url.hostname or url.username or url.password:
                raise ValueError('expected HTTP(S) URL without credentials')
            host = url.hostname
            try:
                address = ipaddress.ip_address(host)
                host = f'[{address}]' if address.version == 6 else str(address)
            except ValueError:
                host = domain(host)
            port = url.port
            authority = host + (f':{port}' if port and (url.scheme.lower(), port) not in (('http', 80), ('https', 443)) else '')
            value = urlunsplit((url.scheme.lower(), authority, url.path or '/', url.query, ''))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f'invalid {kind}: {exc}') from exc
    if len(value) > 8192:
        raise ValueError('indicator exceeds 8192 characters')
    if not re.fullmatch(r'[0-9]{1,3}', row['confidence'].strip()) or not 0 <= int(row['confidence']) <= 100:
        raise ValueError('confidence must be a whole number from 0 to 100')
    try:
        seen = datetime.fromisoformat(row['first_seen'].strip().replace('Z', '+00:00'))
        if seen.tzinfo:
            seen = seen.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError('first_seen must be an ISO-8601 date or datetime') from exc
    source = row['source'].strip()
    if len(source) > 255:
        raise ValueError('source exceeds 255 characters')
    return dict(key=hashlib.sha256((kind + '\0' + value).encode()).hexdigest(), type=kind, value=value,
                confidence=int(row['confidence']), source=source, first_seen=seen)
