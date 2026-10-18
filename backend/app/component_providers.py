"""Opt-in provider protocol: GET /search?q=MPN -> {items:[{assets:[{url,sha256}]}]}.

No provider is enabled by default. The operator records authorization and asset
license permission; credentials come from a named server environment variable.
Downloads are bounded, same-origin, hashed, and then parsed by normal importers.
"""
import hashlib
import json
import os
import urllib.parse
from pathlib import Path
import httpx
from .engine import OperationError, atomic_text

MAX_BYTES = 50*1024*1024


def providers(library):
    path = library.root/'providers.json'
    return json.loads(path.read_text()) if path.is_file() else []


def configure(library, name, base_url, authorized=False, source_license=None, token_env=''):
    from .component_library import identifier, license_policy
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OperationError('Provider base URL must be HTTPS without embedded credentials or query parameters.')
    key = identifier(base_url.rstrip('/'))
    policy = license_policy(source_license)
    row = dict(id=key, name=str(name)[:100], base_url=base_url.rstrip('/'),
               authorized=bool(authorized), source_license=policy, token_env=token_env)
    rows = [p for p in providers(library) if p['id'] != key]+[row]
    atomic_text(library.root/'providers.json', json.dumps(rows, indent=1))
    cached = library.root/'provider-cache'/key
    if cached.is_dir():library.configure(cached,'Provider',policy)
    return row


def acquire(library, query, transport=None):
    from .component_library import FORMATS
    trace = []
    for provider in providers(library):
        if not provider['authorized'] or not provider['source_license']['allow_import']:
            trace.append(dict(stage='external provider', provider=provider['name'], status='authorization or import permission missing'))
            continue
        headers = {}
        if provider.get('token_env'):
            token = os.getenv(provider['token_env'])
            if not token:
                trace.append(dict(stage='external provider', provider=provider['name'], status='credential unavailable'))
                continue
            headers['Authorization'] = 'Bearer '+token
        try:
            with httpx.Client(timeout=30, follow_redirects=False, headers=headers, transport=transport) as client:
                response = client.get(provider['base_url']+'/search', params={'q':query})
                response.raise_for_status()
                if len(response.content)>2*1024*1024:
                    raise OperationError('Provider search response exceeds 2 MB.')
                folder = library.root/'provider-cache'/provider['id']
                folder.mkdir(parents=True, exist_ok=True)
                count = 0
                for item in response.json().get('items', [])[:10]:
                    for asset in item.get('assets', [])[:8]:
                        url = urllib.parse.urljoin(provider['base_url']+'/', asset['url'])
                        parsed = urllib.parse.urlsplit(url)
                        if (parsed.scheme,parsed.netloc) != (urllib.parse.urlsplit(provider['base_url']).scheme,
                                                           urllib.parse.urlsplit(provider['base_url']).netloc):
                            raise OperationError('Provider asset URL must use the authorized origin.')
                        filename = Path(urllib.parse.unquote(parsed.path)).name
                        if Path(filename).suffix.lower() not in FORMATS or any(c in filename for c in '\\:'):
                            continue
                        data = bytearray()
                        with client.stream('GET', url) as download:
                            download.raise_for_status()
                            for chunk in download.iter_bytes():
                                data.extend(chunk)
                                if len(data)>MAX_BYTES:
                                    raise OperationError('Provider asset exceeds 50 MB.')
                        sha = hashlib.sha256(data).hexdigest()
                        if asset.get('sha256') and sha != asset['sha256']:
                            raise OperationError('Provider asset checksum mismatch.')
                        target = folder/(sha[:16]+'-'+filename)
                        # Same-origin content-addressed cache; never execute downloaded content.
                        if not target.exists():
                            temp = target.with_suffix(target.suffix+'.tmp')
                            temp.write_bytes(data);temp.replace(target)
                        count += 1
                key = library.configure(folder, 'Provider', provider['source_license'])
                scan = library.scan(key)
                trace.append(dict(stage='external provider', provider=provider['name'], downloaded=count, scan=scan))
        except (httpx.HTTPError,ValueError,OSError,KeyError) as exc:
            # Do not expose request URLs or secrets in provider diagnostics.
            trace.append(dict(stage='external provider', provider=provider['name'], status='failed', error=type(exc).__name__))
    if not trace:
        trace.append(dict(stage='external provider', status='no authorized providers configured'))
    return trace
