from __future__ import annotations

import hashlib
import json
import math
import zlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class CanonicalSnapshotEnvelope:
    payload: bytes
    compressed_bytes: int
    uncompressed_bytes: int
    content_hash: str
    maximum_uncompressed_bytes: int


@dataclass(frozen=True, slots=True)
class SnapshotIntegrityError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def decode_canonical_snapshot(envelope: CanonicalSnapshotEnvelope) -> bytes:
    if envelope.compressed_bytes != len(envelope.payload):
        raise SnapshotIntegrityError(
            "backtest input snapshot compressed byte count is invalid"
        )
    if not 0 <= envelope.uncompressed_bytes <= envelope.maximum_uncompressed_bytes:
        raise SnapshotIntegrityError(
            "backtest input snapshot uncompressed byte count is invalid"
        )
    decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        canonical = decompressor.decompress(
            envelope.payload, envelope.maximum_uncompressed_bytes + 1
        )
    except zlib.error as error:
        raise SnapshotIntegrityError(
            "backtest input snapshot gzip payload is invalid"
        ) from error
    if len(canonical) > envelope.maximum_uncompressed_bytes:
        raise SnapshotIntegrityError(
            "backtest input snapshot exceeds maximum uncompressed size"
        )
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise SnapshotIntegrityError("backtest input snapshot gzip payload is invalid")
    if len(canonical) != envelope.uncompressed_bytes:
        raise SnapshotIntegrityError(
            "backtest input snapshot uncompressed byte count is invalid"
        )
    if hashlib.sha256(canonical).hexdigest() != envelope.content_hash:
        raise SnapshotIntegrityError("backtest input snapshot content hash is invalid")
    _validate_canonical_json(canonical)
    return canonical


def _validate_canonical_json(canonical: bytes) -> None:
    try:
        value = json.loads(canonical.decode("utf-8"))
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise SnapshotIntegrityError(
            "backtest input snapshot canonical JSON is invalid"
        ) from error
    if encoded != canonical or not isinstance(value, dict):
        raise SnapshotIntegrityError(
            "backtest input snapshot canonical JSON is invalid"
        )
    for name in ("target", "benchmark"):
        frame = value.get(name)
        if not isinstance(frame, dict):
            continue
        rows = frame.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, list):
                continue
            for raw in row[1:]:
                if not isinstance(raw, str) or _canonical_decimal(raw) != raw:
                    raise SnapshotIntegrityError(
                        "backtest input snapshot canonical JSON is invalid"
                    )


def _canonical_decimal(raw: str) -> str:
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return ""
    if not value.is_finite() or not math.isfinite(float(value)):
        return ""
    normalized = format(value.normalize(), "f")
    return "0" if normalized in {"", "-0"} else normalized
