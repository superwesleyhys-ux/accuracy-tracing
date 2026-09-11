"""Compatibility package for the FactCircuit verification harness."""

from .core import DEFAULT_CONFIG, EvidenceProvider, run_verification
from .early_risk import run_early_risk

__all__ = ["DEFAULT_CONFIG", "EvidenceProvider", "run_verification", "run_early_risk"]
__version__ = "0.3.2"
