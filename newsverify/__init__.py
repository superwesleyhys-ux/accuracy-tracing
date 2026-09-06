"""Offline, adapter-driven news evidence verification harness."""

from .core import DEFAULT_CONFIG, EvidenceProvider, run_verification

__all__ = ["DEFAULT_CONFIG", "EvidenceProvider", "run_verification"]
__version__ = "0.3.0"
