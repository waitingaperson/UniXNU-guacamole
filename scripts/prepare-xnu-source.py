#!/usr/bin/env python3
"""The 8796 tree already carries the public DriverKit and TrustCache headers.

UniXNU's version of this script fetches omitted Darwin 23 headers from the
GitHub contents API.  That is unnecessary here and makes the build depend on
an unauthenticated API quota.
"""
from pathlib import Path

root = Path('.cache/xnu-work')
required = ('iokit/DriverKit', 'EXTERNAL_HEADERS/TrustCache')
missing = [str(root / name) for name in required if not (root / name).is_dir()]
if missing:
    raise SystemExit('8796 source is missing: ' + ', '.join(missing))
print('8796 source already carries DriverKit/TrustCache headers; nothing restored')
