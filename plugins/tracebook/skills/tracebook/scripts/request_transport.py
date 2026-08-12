"""Lossless, cross-platform transport for Tracebook capture requests."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from typing import Any


TRANSPORT_VERSION = 1
TRANSPORT_ENCODING = "base64+utf-8"
MAX_REQUEST_BYTES = 4 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOSSY_RUN = re.compile(r"\?{3,}")
_MOJIBAKE_MARKERS = ("\ufffd", "\u951f\u65a4\u62f7", "\u00ef\u00bf\u00bd")
_ENVELOPE_FIELDS = {"transport_version", "encoding", "payload", "sha256"}


@dataclass(frozen=True)
class DecodedRequest:
    payload: dict[str, Any]
    transport: str
    sha256: str


def suspicious_text_findings(value: object, path: str = "$") -> list[str]:
    """Return high-confidence signs that Unicode text was already destroyed.

    ASCII question-mark runs are intentionally used instead of language-specific
    character ranges. Arabic ``؟``, full-width ``？`` and ordinary single question
    marks therefore remain valid.
    """
    findings: list[str] = []
    if isinstance(value, str):
        marker = next((item for item in _MOJIBAKE_MARKERS if item in value), None)
        match = _LOSSY_RUN.search(value)
        if marker is not None:
            findings.append(f"{path}: contains known replacement/mojibake marker {marker!r}")
        if match is not None:
            findings.append(
                f"{path}: contains {len(match.group(0))} consecutive ASCII question marks"
            )
        return findings
    if isinstance(value, dict):
        for key, item in value.items():
            findings.extend(suspicious_text_findings(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(suspicious_text_findings(item, f"{path}[{index}]"))
    return findings


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError(
            f"INVALID_REQUEST: {label} exceeds the {MAX_REQUEST_BYTES}-byte limit"
        )
    try:
        # Accept one UTF-8 BOM for compatibility with Windows-authored JSON
        # files. The SHA-256 still covers the exact bytes, including the BOM.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"INVALID_REQUEST: {label} is not valid UTF-8: {error}") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"INVALID_REQUEST: {label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"INVALID_REQUEST: {label} must be a JSON object")
    return value


def decode_request(raw: bytes, *, allow_suspicious: bool = False) -> DecodedRequest:
    """Decode a legacy UTF-8 request or an ASCII-safe, integrity-checked envelope."""
    outer = _json_object(raw, "request")
    envelope_keys = _ENVELOPE_FIELDS.intersection(outer)
    if envelope_keys:
        unknown = sorted(set(outer) - _ENVELOPE_FIELDS)
        missing = sorted(_ENVELOPE_FIELDS - set(outer))
        if missing or unknown:
            detail = []
            if missing:
                detail.append(f"missing fields: {', '.join(missing)}")
            if unknown:
                detail.append(f"unknown fields: {', '.join(unknown)}")
            raise ValueError(f"INVALID_REQUEST: invalid transport envelope ({'; '.join(detail)})")
        if outer["transport_version"] != TRANSPORT_VERSION:
            raise ValueError(
                "INVALID_REQUEST: unsupported transport_version "
                f"{outer['transport_version']!r}; expected {TRANSPORT_VERSION}"
            )
        if outer["encoding"] != TRANSPORT_ENCODING:
            raise ValueError(
                f"INVALID_REQUEST: unsupported transport encoding {outer['encoding']!r}"
            )
        payload = outer["payload"]
        digest = outer["sha256"]
        if not isinstance(payload, str) or not payload.isascii():
            raise ValueError("INVALID_REQUEST: envelope payload must be an ASCII base64 string")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError("INVALID_REQUEST: envelope sha256 must be 64 lowercase hex characters")
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError(f"INVALID_REQUEST: envelope payload is not strict base64: {error}") from error
        actual = hashlib.sha256(decoded).hexdigest()
        if not hmac.compare_digest(actual, digest):
            raise ValueError(
                f"INVALID_REQUEST: envelope SHA-256 mismatch (expected {digest}, actual {actual})"
            )
        request = _json_object(decoded, "envelope payload")
        transport = TRANSPORT_ENCODING
        request_sha256 = actual
    else:
        request = outer
        transport = "legacy-raw-utf-8"
        request_sha256 = hashlib.sha256(raw).hexdigest()

    findings = suspicious_text_findings(request)
    if findings and not allow_suspicious:
        raise ValueError(
            "SUSPECTED_LOSSY_ENCODING: capture request contains high-confidence signs "
            f"of destroyed text ({'; '.join(findings)}). Recreate the text from its "
            "source and use the ASCII-safe envelope; use --allow-suspicious-encoding "
            "only when the ASCII question marks are intentional."
        )
    return DecodedRequest(request, transport, request_sha256)


def encode_envelope(raw: bytes) -> bytes:
    """Wrap UTF-8 JSON bytes in the canonical ASCII-only transport envelope."""
    _json_object(raw, "request")
    envelope = {
        "transport_version": TRANSPORT_VERSION,
        "encoding": TRANSPORT_ENCODING,
        "payload": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return json.dumps(envelope, ensure_ascii=True, separators=(",", ":")).encode("ascii")
