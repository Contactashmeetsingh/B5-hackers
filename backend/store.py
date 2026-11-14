"""Read and write the JSON contract files, validated against backend.schemas.

Every stage goes through these two functions, so a malformed file fails at the
boundary with the file name in the error rather than deep inside pipeline code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, TypeAdapter

M = TypeVar("M", bound=BaseModel)


def read_rows(path: Path, model: type[M]) -> list[M]:
    """Load a JSON array file and validate every row as `model`."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run the stage that writes it first")
    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        return TypeAdapter(list[model]).validate_python(raw)
    except Exception as exc:  # pydantic.ValidationError, re-raised with the file name
        raise ValueError(f"{path} does not match the {model.__name__} contract: {exc}") from exc


def write_rows(path: Path, rows: Iterable[BaseModel]) -> None:
    """Write rows as a pretty JSON array (stable key order, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.model_dump(mode="json") for r in rows]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic: a crashed run never leaves a half-written contract file


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
