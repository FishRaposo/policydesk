"""Synthetic replay boundary. No SDK import, credentials, transport, or live fallback."""

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .resources import DATA, digest


class CassetteMissing(RuntimeError):
    pass


class CassetteInvalid(RuntimeError):
    pass


class NetworkModeDisabled(RuntimeError):
    pass


class ResponseClient(Protocol):
    def call(self, request: dict[str, Any], /) -> dict[str, Any]: ...


class ReplayClient:
    def __init__(self, directory: Path | None = None, mode: str | None = None):
        mode = mode or os.environ.get("POLICYDESK_MODE", "replay")
        if mode != "replay":
            raise NetworkModeDisabled(
                "This synthetic prototype supports replay only; live and record are disabled"
            )
        self.directory = directory or DATA / "cassettes"

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        key = digest(request)
        path = self.directory / f"{key}.json"
        if not path.is_file():
            raise CassetteMissing(f"No synthetic cassette for request {key}; no fallback was used")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            if set(envelope) != {
                "schema_version",
                "provenance",
                "request_hash",
                "response",
                "integrity",
            }:
                raise ValueError("Unknown cassette fields")
            integrity = envelope.pop("integrity")
            if envelope["schema_version"] != 1 or envelope["provenance"] != "synthetic":
                raise ValueError("Unsupported cassette version or provenance")
            if envelope["request_hash"] != key or digest(envelope) != integrity:
                raise ValueError("Cassette hash mismatch")
            if not isinstance(envelope["response"], dict):
                raise ValueError("Response must be an object")
            return envelope["response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise CassetteInvalid(f"Invalid cassette {key}: {exc}") from exc


def request(step: str, **payload: Any) -> dict[str, Any]:
    from .resources import load_policy

    return {
        "protocol": "synthetic-v1",
        "step": step,
        "policy_hash": digest(load_policy()),
        **payload,
    }
