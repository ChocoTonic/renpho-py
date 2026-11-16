"""Internal session validation and persistence; no HTTP or login operations."""

import base64
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import RenphoSessionError


def positive_timestamp(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("invalid token timestamp")
    try:
        timestamp = float(value)
    except (OverflowError, ValueError):
        raise ValueError("invalid token timestamp") from None
    if not math.isfinite(timestamp) or timestamp <= 0:
        raise ValueError("invalid token timestamp")
    return timestamp


@dataclass(frozen=True)
class ImportedSession:
    token: str = field(repr=False)
    user_id: int | str
    email: str
    expires_at: float | None


def parse_session(data: object, expected_user_id: int | str | None) -> ImportedSession:
    if not isinstance(data, dict):
        raise ValueError("session must be an object")
    token, uid = data.get("token"), data.get("user_id")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("session requires a nonempty token")
    if (not isinstance(uid, (int, str)) or isinstance(uid, bool)
            or not str(uid).isascii() or not str(uid).isdigit()):
        raise ValueError("session requires a numeric user_id")
    if expected_user_id is not None and str(uid) != str(expected_user_id):
        raise ValueError("session user_id does not match expected_user_id")
    email = data.get("email", "")
    if not isinstance(email, str):
        raise ValueError("session email must be a string")
    expiry = data.get("expires_at")
    return ImportedSession(
        token=token, user_id=uid, email=email,
        expires_at=positive_timestamp(expiry) if expiry is not None else None,
    )


def read_session_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        raise ValueError("cannot read session JSON file") from None
    if not isinstance(data, dict):
        raise ValueError("session must be an object")
    return data


def token_expiry(token: str | None) -> float | None:
    """Decode an expiry claim without verifying the token or making a request."""
    try:
        part = (token or "").split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return positive_timestamp(claims.get("exp"))
    except (ValueError, IndexError, TypeError, AttributeError):
        return None


def write_session_file(target: Path, data: dict) -> None:
    """Keep the old file intact on failure; publish a mode-0600 replacement."""
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


@dataclass(frozen=True)
class TokenTime:
    token: str | None = field(repr=False)
    issued_at: float | None
    expires_at: float | None


def parse_token_time(data: object, user_id: int | str) -> TokenTime:
    """Validate every field before the client adopts a replacement token."""
    if not isinstance(data, dict):
        raise RenphoSessionError("RefreshSession", None, "Invalid token-time response")
    if data.get("userId") is not None and str(data["userId"]) != str(user_id):
        raise RenphoSessionError("RefreshSession", None, "Token-time account mismatch")
    token = data.get("token")
    if token is not None and not isinstance(token, str):
        raise RenphoSessionError("RefreshSession", None, "Invalid replacement token")
    times: dict[str, float] = {}
    for key in ("issAt", "expAt"):
        value = data.get(key)
        if value is not None:
            try:
                times[key] = positive_timestamp(value) / 1000
            except ValueError:
                raise RenphoSessionError(
                    "RefreshSession", None, "Invalid token timestamp",
                ) from None
    return TokenTime(token, times.get("issAt"), times.get("expAt"))
