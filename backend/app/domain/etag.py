from __future__ import annotations

import hashlib
import json
from typing import Any


def proposal_etag(proposal: dict[str, Any], snapshot: list[dict[str, Any]]) -> str:
    """Stable hash of the proposal plus the pantry versions it was planned against.

    A confirm from a stale tab sends an older hash. The handler recomputes the
    hash from the checkpoint and rejects a mismatch before resuming the graph.
    """
    versions = [{"id": row["id"], "version": row["version"]} for row in snapshot]
    versions.sort(key=lambda row: str(row["id"]))
    payload = {"proposal": proposal, "versions": versions}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
