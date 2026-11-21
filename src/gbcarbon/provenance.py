"""Raw-data provenance: a manifest entry for every pull under data/raw.

Every raw artifact records what was fetched, from where, when, how many rows,
and a content hash, so each number in the report traces back to a pinned pull.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(manifest_path: Path, name: str, **fields) -> dict:
    """Upsert one named entry; stamps pulled_utc if absent."""
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"entries": {}}
    fields.setdefault("pulled_utc", datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"))
    manifest["entries"][name] = fields
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
