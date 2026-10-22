#!/usr/bin/env python3
"""Restore the TrustCache headers that xnu-10063 omitted.

The public xnu-10063 tree already carries iokit/DriverKit. The TrustCache
headers only exist in the earlier xnu-8796 tag; they are vendored next to
this script so the kernel build does not depend on the GitHub API.
"""
from pathlib import Path
import shutil

root = Path('.cache/xnu-work')
driverkit = root / 'iokit/DriverKit'
trustcache = root / 'EXTERNAL_HEADERS/TrustCache'

if not driverkit.is_dir():
    raise SystemExit(f'xnu source is missing {driverkit}')

driverkit_headers = Path(__file__).resolve().parent / 'driverkit-headers'
if driverkit_headers.is_dir():
    for source in driverkit_headers.rglob('*'):
        if not source.is_file():
            continue
        target = driverkit / source.relative_to(driverkit_headers)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

if not trustcache.is_dir():
    headers = Path(__file__).resolve().parent / 'trustcache-headers'
    if not headers.is_dir():
        raise SystemExit(f'vendored TrustCache headers are missing: {headers}')
    trustcache.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(headers, trustcache)
    print(f'restored {len(list(trustcache.iterdir()))} TrustCache headers')
else:
    print('TrustCache headers already present')
