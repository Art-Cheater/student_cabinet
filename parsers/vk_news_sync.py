#!/usr/bin/env python3
"""Fetch VK news into DB cache (run hourly via cron or docker)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.vk_news import refresh_vk_news_cache


def main():
    ok, err = refresh_vk_news_cache(force=True, limit=10)
    if ok:
        print('VK news cache updated.')
        if err:
            print(f'Note: {err}')
    elif err:
        print(f'Skip/failed: {err}')
    else:
        print('Cache is fresh, nothing to do.')


if __name__ == '__main__':
    main()
