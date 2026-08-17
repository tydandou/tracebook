"""Shared schema-v2 machine-field contracts."""

from __future__ import annotations


LIFECYCLE_STATUSES = frozenset({"current", "pending", "deprecated", "superseded"})
