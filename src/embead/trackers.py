"""Tracker-neutral acquisition contracts."""

from __future__ import annotations

from typing import Protocol

from .models import IssueRecord, WorkspaceSnapshot


class TrackerError(RuntimeError):
    """Raised when a tracker cannot provide a safe, valid snapshot."""


class TrackerAdapter(Protocol):
    """The read-only source boundary used by the analysis commands."""

    def load(self) -> tuple[WorkspaceSnapshot, tuple[IssueRecord, ...]]: ...
