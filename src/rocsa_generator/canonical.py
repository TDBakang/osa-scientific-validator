"""Byte-level canonicalization primitives fixed by contract 1.0.0."""

import hashlib
import json
import unicodedata
from pathlib import PurePosixPath


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    raw_parts = value.split("/")
    invalid = (
        value != unicodedata.normalize("NFC", value)
        or "\\" in value or "\x00" in value or value.startswith("/")
        or (len(value) >= 2 and value[1] == ":") or "//" in value
        or any(part in ("", ".", "..") for part in raw_parts)
    )
    if invalid:
        raise ValueError(f"unsafe relative path: {value!r}")
    return value


def text_bytes(value: str) -> bytes:
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return (value.rstrip("\n") + "\n").encode("utf-8")
