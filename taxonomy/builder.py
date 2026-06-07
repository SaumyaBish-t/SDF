"""Taxonomy builder — loads and validates per-domain dimension definitions.

A taxonomy is a dict {dimension: [value, ...]}, stored as JSON under
`taxonomy/domains/{domain}.json`. The builder is deterministic and offline;
it does not call any LLM. See PROJECT_SPEC.md §4.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DEFAULT_DOMAINS_DIR: Path = Path(__file__).resolve().parent / "domains"

Taxonomy = dict[str, list[str]]


class TaxonomyError(ValueError):
    """Raised when a taxonomy JSON file is missing or malformed."""


def load_taxonomy(domain: str, domains_dir: Optional[Path] = None) -> Taxonomy:
    """Load and validate `{domains_dir}/{domain}.json`.

    Returns a dict of {dimension_name: [allowed_values, ...]}.
    Raises TaxonomyError if the file is missing, not JSON, not a dict,
    or contains any dimension that is not a non-empty list of strings.
    """
    base = domains_dir if domains_dir is not None else _DEFAULT_DOMAINS_DIR
    path = base / f"{domain}.json"
    if not path.exists():
        raise TaxonomyError(f"No taxonomy file for domain '{domain}' at {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TaxonomyError(f"{path} is not valid JSON: {e}") from e

    if not isinstance(raw, dict) or not raw:
        raise TaxonomyError(f"{path} must be a non-empty JSON object")

    taxonomy: Taxonomy = {}
    for dim, values in raw.items():
        if not isinstance(dim, str) or not dim:
            raise TaxonomyError(f"{path}: dimension name must be a non-empty string")
        if not isinstance(values, list) or not values:
            raise TaxonomyError(
                f"{path}: dimension '{dim}' must map to a non-empty list"
            )
        if not all(isinstance(v, str) and v for v in values):
            raise TaxonomyError(
                f"{path}: dimension '{dim}' values must all be non-empty strings"
            )
        if len(set(values)) != len(values):
            raise TaxonomyError(f"{path}: dimension '{dim}' has duplicate values")
        taxonomy[dim] = list(values)

    return taxonomy


def list_domains(domains_dir: Optional[Path] = None) -> list[str]:
    """Return the domain names with a taxonomy file on disk (sorted)."""
    base = domains_dir if domains_dir is not None else _DEFAULT_DOMAINS_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.json"))
