"""Canonical, privacy-conscious evidence records for on-chain anchoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def canonical_json(value: Mapping[str, Any]) -> str:
    """Serialize a record deterministically so it can be hashed and rechecked."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def metadata_hash(value: Mapping[str, Any]) -> str:
    """Return the bytes32 SHA-256 hash used as the registry key."""
    return "0x" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def save_metadata(value: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write the exact canonical data which was anchored on chain."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")
    return path
