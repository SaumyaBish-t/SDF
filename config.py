"""Centralized config. Import everything from here — no magic numbers in pipeline code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

NIM_BASE_URL: str = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")


@dataclass(frozen=True)
class KeyRole:
    api_key: str
    model: str
    role: str
    batch_size: int


def _require(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


KEY_1 = KeyRole(_require("NIM_KEY_1"), "deepseek-ai/deepseek-v4-flash",            "generator",    10)
KEY_2 = KeyRole(_require("NIM_KEY_2"), "z-ai/glm4.7",                              "generator",    10)
KEY_3 = KeyRole(_require("NIM_KEY_3"), "nvidia/nemotron-3-nano-30b-a3b",           "pre_filter",   3)
KEY_4 = KeyRole(_require("NIM_KEY_4"), "mistralai/mistral-small-4-119b-2603",      "pre_filter",   3)
KEY_5 = KeyRole(_require("NIM_KEY_5"), "deepseek-ai/deepseek-r1-0528",             "full_scorer",  1)

GENERATORS = (KEY_1, KEY_2)
PRE_FILTERS = (KEY_3, KEY_4)
FULL_SCORER = KEY_5

ACCEPT_THRESHOLD: float = 3.5
REVISE_RANGE: tuple[float, float] = (3.0, 3.4)
REJECT_BELOW: float = 3.0
SIMILARITY_REJECT: float = 0.92
MINHASH_THRESHOLD: float = 0.7

CHECKPOINT_INTERVAL: int = 100
MAX_RETRIES: int = 3
BACKOFF_BASE: int = 2

CHECKPOINT_DIR: str = "checkpoints"
LOG_DIR: str = "logs"
OUTPUT_DIR: str = "output"
