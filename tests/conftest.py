"""Test bootstrap — supply dummy NIM keys before config is imported anywhere.

config.py raises if any NIM_KEY_* is missing. Tests don't make real API calls,
so we inject placeholder values into the environment before the first
`import config` resolves.
"""
from __future__ import annotations

import os

for _i, _k in enumerate(("NIM_KEY_1", "NIM_KEY_2", "NIM_KEY_3", "NIM_KEY_4", "NIM_KEY_5"), start=1):
    os.environ.setdefault(_k, f"test-key-{_i}-not-real")
