"""Verify a real backend, then generate a preview-only Vercel config."""
import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx

TEMPLATE = Path(__file__).with_name('vercel.template.json')
OUTPUT = Path(__file__).with_name('vercel.preview.json')


def https_origin(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port not in (None, 443)):
        raise ValueError('Use an HTTPS origin only, without credentials, /api, query, or fragment.')
    if (host in ('localhost', 'example.com', 'example.org', 'example.net')
            or '.' not in host or host.endswith(('.localhost', '.local', '.invalid', '.test', '.example', '.example.com', '.example.org', '.example.net'))
            or not re.fullmatch(r'[a-z0-9.-]+', host, re.I)):
        raise ValueError('A real publicly hosted HTTPS hostname is required.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError('Loopback and private IP addresses cannot be the hosted backend.')
    return f'https://{host}'


def config_for_backend(origin):
    origin = https_origin(origin)
    config = json.loads(TEMPLATE.read_text(encoding='utf-8'))
    config['rewrites'][0]['destination'] = f'{origin}/api/:path*'
    return config


def check_health(client):
    response = client.get('/api/health')
    if response.status_code != 200:
        raise ValueError(f'Backend /api/health returned HTTP {response.status_code}.')
    try:
        data = response.json()
    except ValueError:
        raise ValueError('Backend health returned non-JSON content, possibly an HTML fallback.') from None
    if not isinstance(data, dict) or data.get('status') != 'ok':
        raise ValueError('Backend did not report status=ok.')
    if data.get('gnani_configured') is not True:
        raise ValueError('Set GNANI_API_KEY in the backend host secret settings before testing audio.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend_url', help='Actual HTTPS origin assigned by the backend host')
    args = parser.parse_args()
    try:
        origin = https_origin(args.backend_url)
        with httpx.Client(base_url=origin, timeout=90, follow_redirects=False, trust_env=False) as client:
            check_health(client)
        OUTPUT.write_text(json.dumps(config_for_backend(origin), indent=2) + '\n', encoding='utf-8')
    except (ValueError, httpx.RequestError) as error:
        # Never print provider keys, response bodies, headers, or exception URLs.
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f'Preview config not written: {detail}\n')
    print(f'HTTPS health verified. Preview config written to {OUTPUT.relative_to(Path.cwd())}.')
    print('API rewrite preserves /api and precedes the SPA catch-all. Production was not deployed.')


if __name__ == '__main__':
    main()
