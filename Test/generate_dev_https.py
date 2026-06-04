#!/usr/bin/env python3
"""Self-signed cert for Test HTTPS. Usage: python generate_dev_https.py [IP...]"""
from __future__ import annotations

import datetime
import ipaddress
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / 'dev_certs'
DEFAULT_HOSTS = ['localhost', '127.0.0.1', '192.168.137.1']


def main() -> int:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print('pip install cryptography')
        return 1

    extra = [a.strip() for a in sys.argv[1:] if a.strip()]
    hosts = list(dict.fromkeys(DEFAULT_HOSTS + extra))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key_path = OUT_DIR / 'key.pem'
    cert_path = OUT_DIR / 'cert.pem'

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'StudentCabinet Test'),
    ])
    alt_names = []
    for host in hosts:
        if _is_ip(host):
            alt_names.append(x509.IPAddress(ipaddress.ip_address(host)))
        else:
            alt_names.append(x509.DNSName(host))

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print('OK:', cert_path)
    print('SAN:', ', '.join(hosts))
    return 0


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    raise SystemExit(main())
