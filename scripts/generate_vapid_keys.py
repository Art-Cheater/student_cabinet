#!/usr/bin/env python3
"""Generate VAPID keys for Web Push. Add to .env:
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@example.com
"""
from py_vapid import Vapid


def main():
    vapid = Vapid()
    vapid.generate_keys()
    print('VAPID_PUBLIC_KEY=' + vapid.public_key.decode('utf-8'))
    print('VAPID_PRIVATE_KEY=' + vapid.private_key.decode('utf-8'))
    print('VAPID_SUBJECT=mailto:admin@vyatsu.ru')


if __name__ == '__main__':
    main()
