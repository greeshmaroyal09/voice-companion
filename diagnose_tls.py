"""Safe local TLS diagnostics; never prints credentials or sends speech data."""
import json
import os
import ssl
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from httpx._config import create_ssl_context

from backend import main  # Loads the same project .env as FastAPI.


def configuration():
    configured = os.getenv('SSL_CERT_FILE')
    report = {
        'pid': os.getpid(),
        'dotenv_ssl_cert_file_set': bool(dotenv_values(Path(main.__file__).resolve().parents[1] / '.env').get('SSL_CERT_FILE')),
        'effective_ssl_cert_file_set': bool(configured),
        'ssl_cert_file_exists': Path(configured).is_file() if configured else None,
        'ssl_cert_dir_set': bool(os.getenv('SSL_CERT_DIR')),
        'trust_source': 'SSL_CERT_FILE' if configured else 'SSL_CERT_DIR' if os.getenv('SSL_CERT_DIR') else 'certifi default bundle',
    }
    try:
        context = create_ssl_context(verify=True, trust_env=True)
        report.update(certificate_required=context.verify_mode == ssl.CERT_REQUIRED,
                      hostname_verification=context.check_hostname,
                      trusted_ca_count=context.cert_store_stats()['x509_ca'])
    except (OSError, ValueError) as error:
        report['context_error_type'] = type(error).__name__
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    configuration()
    if '--serve' in sys.argv:
        import uvicorn
        uvicorn.run(main.app, host='127.0.0.1', port=8000)
    else:
        # Credential-free HTTPS request: no API key, history, or request body.
        try:
            with httpx.Client(verify=True, trust_env=True, timeout=15) as client:
                result = client.head(main.TTS_URL)
            print(json.dumps({'tls_connected': True, 'http_status': result.status_code}))
        except httpx.RequestError as error:
            diagnostic, message = main.transport_failure(error)
            print(json.dumps({'tls_connected': False, 'diagnostic': diagnostic, 'detail': message}))
