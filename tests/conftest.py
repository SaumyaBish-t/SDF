"""Test bootstrap — supply dummy provider keys before config is imported.

config.py raises if any required key env var is missing. Tests don't make
real API calls, so we inject placeholder values before the first
`import config` resolves.
"""
from __future__ import annotations

import os

os.environ.setdefault("GROQ_API_KEY", "test-groq-key-not-real")
os.environ.setdefault("CEREBRAS_API_KEY", "test-cerebras-key-not-real")
# NIM keys kept around so old tests that monkeypatch via NIM paths still
# import config without raising — even though the live pipeline runs on
# Groq + Cerebras.
for _i, _k in enumerate(("NIM_KEY_1", "NIM_KEY_2", "NIM_KEY_3", "NIM_KEY_4", "NIM_KEY_5"), start=1):
    os.environ.setdefault(_k, f"test-key-{_i}-not-real")
