"""Replay captured/annotated evidence without network or model credentials."""
from copy import deepcopy


class ReplayProvider:
    """Return one captured batch per round. This does not perform live search."""

    def __init__(self, rounds):
        if not isinstance(rounds, list) or any(not isinstance(r, list) for r in rounds):
            raise ValueError("rounds must be a list of evidence lists")
        self.rounds = deepcopy(rounds)

    def search(self, claim, round_number, intent, limit):
        if round_number < 1 or round_number > len(self.rounds):
            return []
        return deepcopy(self.rounds[round_number - 1][:limit])
