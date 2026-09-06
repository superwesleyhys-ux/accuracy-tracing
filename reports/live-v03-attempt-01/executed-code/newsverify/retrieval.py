"""Task-directed retrieval over supplied snapshots with explicit coverage feedback.

This provider is an offline searchable index, not a claim of live web coverage.
Fetch, search and reanalysis tasks are executed against the same fixed pool in
every experiment. Every returned version still passes through the engine's psi.
"""
from __future__ import annotations

from dataclasses import asdict
import re

from .provenance import MaterialVersion, _fingerprint


class SnapshotSearchProvider:
    def __init__(self, snapshots, seed_ids):
        self.materials = {}
        for item in snapshots:
            if not isinstance(item, MaterialVersion): raise TypeError("Expected MaterialVersion")
            old = self.materials.get(item.version_id)
            if old is not None and _fingerprint(old) != _fingerprint(item):
                raise ValueError("version_id collision in retrieval index")
            self.materials[item.version_id] = item
        self.seed_ids = tuple(seed_ids)
        if not set(self.seed_ids) <= self.materials.keys(): raise ValueError("Unknown seed")
        self.returned = set()
        self.last_feedback = []
        self.history = []

    def search(self, target, tasks, round_number, limit):
        self.last_feedback = []
        chosen = []
        if round_number == 1:
            chosen = [self.materials[k] for k in self.seed_ids][:limit]
        else:
            for task in tasks:
                locator = task.locator
                if task.action == "fetch":
                    matches = [m for m in self.materials.values() if m.url == locator or m.version_id == locator]
                elif task.action == "reanalyse":
                    matches = [m for m in self.materials.values() if m.version_id == locator and m.version_id in self.returned]
                else:
                    query = locator or task.question
                    words = set(re.findall(r"[a-z0-9]{3,}", query.lower())) - {
                        "the", "and", "for", "that", "with", "find", "provide", "source", "record", "target", "evidence"}
                    scores = [(len(words & set(re.findall(r"[a-z0-9]{3,}", (m.url + " " + m.content).lower()))), m)
                              for m in self.materials.values() if m.version_id not in self.returned]
                    matches = [m for score, m in sorted(scores, key=lambda pair: (-pair[0], pair[1].version_id)) if score > 0]
                if task.action != "reanalyse":
                    matches = [m for m in matches if m.version_id not in self.returned]
                room = limit - len(chosen)
                selected = [m for m in matches if m.version_id not in {v.version_id for v in chosen}][:room]
                chosen.extend(selected)
                reason = ("matching snapshots returned" if selected else
                          "retrieval budget filled" if room <= 0 and matches else
                          "no unseen match in fixed snapshot index; live web unavailable")
                self.last_feedback.append({"gap_id": task.id, "action": task.action,
                    "locator": locator, "status": "returned" if selected else "unavailable",
                    "reason": reason, "version_ids": [m.version_id for m in selected]})
        self.returned.update(m.version_id for m in chosen)
        self.history.append({"round": round_number, "tasks": [asdict(t) for t in tasks],
                             "returned_ids": [m.version_id for m in chosen], "feedback": self.last_feedback[:]})
        return iter(chosen)
