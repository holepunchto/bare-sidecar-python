"""Start and manage Bare sidecar processes from Python."""

from ._versions import versions
from .sidecar import Sidecar, executable, spawn

__all__ = [
    "Sidecar",
    "executable",
    "spawn",
    "versions",
]
