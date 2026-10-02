"""Audit-event writer (M3: device lifecycle events).

Writers run inside the request transaction via the shared session, so an
audit row commits exactly when the change it describes commits. Metadata
keys are allow-listed and values must be JSON scalars (or lists of them);
anything else is a programmer error and raises instead of being stored.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from labguard_api.models import AuditLog, User

DEVICE_REGISTERED = "device.registered"
DEVICE_UPDATED = "device.updated"
DEVICE_DEACTIVATED = "device.deactivated"
DEVICE_REACTIVATED = "device.reactivated"

DEVICE_ACTIONS = frozenset(
    {DEVICE_REGISTERED, DEVICE_UPDATED, DEVICE_DEACTIVATED, DEVICE_REACTIVATED}
)

# Never secrets, tokens, hashes, or free-form user input beyond the values below.
METADATA_KEYS = frozenset(
    {"hostname", "lab_id", "display_name", "platform", "agent_version", "is_active", "changed"}
)

_SCALARS = (str, int, float, bool, type(None))


def _check_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in METADATA_KEYS:
            raise ValueError(f"Audit metadata key is not allow-listed: {key!r}.")
        if isinstance(value, _SCALARS):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, _SCALARS) for item in value):
            clean[key] = list(value)
        else:
            raise ValueError(f"Audit metadata value for {key!r} is not a JSON scalar.")
    return clean


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: UUID | str | None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Append one audit row to the current transaction (flush, no commit)."""
    if action not in DEVICE_ACTIONS:
        raise ValueError(f"Unknown audit action: {action!r}.")
    row = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        meta=_check_metadata(metadata),
    )
    db.add(row)
    db.flush()
    return row
