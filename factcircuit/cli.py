"""Canonical FactCircuit command-line interface."""

from newsverify.cli import benchmark, run_fixture
from newsverify.cli import main as _compatibility_main

__all__ = ["benchmark", "main", "run_fixture"]


def main(argv=None):
    return _compatibility_main(argv, prog="factcircuit")
