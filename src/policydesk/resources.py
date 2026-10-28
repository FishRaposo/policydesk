"""Single packaged source for fixtures, policy and replay data."""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

DATA = Path(__file__).parent / "data"


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load_policy() -> dict[str, Any]:
    return yaml.safe_load((DATA / "policy.yaml").read_text(encoding="utf-8"))
