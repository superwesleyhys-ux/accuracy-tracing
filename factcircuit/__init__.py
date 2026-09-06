"""FactCircuit: an auditable claim-and-evidence verification loop."""

from newsverify import DEFAULT_CONFIG, EvidenceProvider, run_verification
from newsverify import __version__

__all__ = [
    "DEFAULT_CONFIG",
    "EvidenceProvider",
    "run_verification",
    "__version__",
]
