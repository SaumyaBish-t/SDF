"""Test bootstrap — supply dummy provider keys before config is imported.

config.py reads three role bindings (generator / prefilter / scorer) from env
with empty-string defaults. We pre-populate them with non-empty test values so
that tests which reference `config.GENERATOR_KEY.model` etc. as fixture data
get something usable. Tests never make real API calls — the AsyncOpenAI
client is monkeypatched per-test.
"""
from __future__ import annotations

import os

os.environ.setdefault("SDF_GENERATOR_API_KEY", "test-generator-key-not-real")
os.environ.setdefault("SDF_GENERATOR_MODEL", "test/generator-model")
os.environ.setdefault("SDF_GENERATOR_BASE_URL", "https://test.invalid/v1")

os.environ.setdefault("SDF_PREFILTER_API_KEY", "test-prefilter-key-not-real")
os.environ.setdefault("SDF_PREFILTER_MODEL", "test/prefilter-model")
os.environ.setdefault("SDF_PREFILTER_BASE_URL", "https://test.invalid/v1")

os.environ.setdefault("SDF_SCORER_API_KEY", "test-scorer-key-not-real")
os.environ.setdefault("SDF_SCORER_MODEL", "test/scorer-model")
os.environ.setdefault("SDF_SCORER_BASE_URL", "https://test.invalid/v1")
