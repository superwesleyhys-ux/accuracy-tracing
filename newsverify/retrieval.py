"""Task-directed retrieval over supplied snapshots with explicit coverage feedback.

This provider is an offline searchable index, not a claim of live web coverage.
Fetch, search and reanalysis tasks are executed against the same fixed pool in
every experiment. Every returned version still passes through the engine's psi.
"""
from __future__ import annotations

from dataclasses import asdict
import re

from .provenance import MaterialVersion, RetrievalHit, _fingerprint


_STOPWORDS = {"the", "and", "for", "that", "with", "find", "provide",
              "source", "record", "target", "evidence"}


def _search_terms(value):
    """Deterministic Latin words plus CJK bi/trigrams for multilingual routing."""
    lowered = value.lower()
    terms = set(re.findall(r"[a-z0-9]{3,}", lowered)) - _STOPWORDS
    for sequence in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", lowered):
        for width in (1, 2, 3):
            terms.update(sequence[index:index + width]
                         for index in range(len(sequence) - width + 1))
    return terms


class SnapshotSearchProvider:
    def __init__(self, snapshots, seed_ids):
        self.materials = {}
        for item in snapshots:
            if not isinstance(item, MaterialVersion): raise TypeError("Expected MaterialVersion")
            old = self.materials.get(item.version_id)
            if old is not None:
                message = ("version_id collision in retrieval index"
                           if _fingerprint(old) != _fingerprint(item)
                           else "duplicate version_id in retrieval index")
                raise ValueError(message)
            self.materials[item.version_id] = item
        self.seed_ids = tuple(seed_ids)
        if len(self.seed_ids) != len(set(self.seed_ids)):
            raise ValueError("duplicate seed version_id")
        if not set(self.seed_ids) <= self.materials.keys(): raise ValueError("Unknown seed")
        self.returned = set()
        self.last_feedback = []
        # Optional protocol sidecar consumed by the provenance runner.  The
        # provider still yields bare MaterialVersion objects for compatibility,
        # while every returned version can be tied to the exact task(s) that
        # selected it.
        self.last_attribution = {}
        self.history = []

    def _select(self, tasks, round_number, limit):
        self.last_feedback = []
        attribution = {}
        chosen = []
        ordered_tasks = []
        candidates = {}
        if round_number == 1:
            chosen = [self.materials[k] for k in self.seed_ids][:limit]
        else:
            # Exact retrieval and explicit reanalysis are validation-loop
            # obligations. A broad lexical search must not consume their whole
            # round budget merely because its gap happened to be inserted first.
            priority = {"fetch": 0, "reanalyse": 1, "search": 2}
            ordered_tasks = sorted(tasks, key=lambda task: (
                priority[task.action], task.action, task.locator or "",
                task.question, task.id))
            for task in ordered_tasks:
                locator = task.locator
                if task.action == "fetch":
                    matches = [m for m in self.materials.values() if m.url == locator or m.version_id == locator]
                elif task.action == "reanalyse":
                    matches = [m for m in self.materials.values() if m.version_id == locator and m.version_id in self.returned]
                else:
                    query = locator or task.question
                    words = _search_terms(query)
                    scores = [(len(words & _search_terms(m.url + " " + m.content)), m)
                              for m in self.materials.values() if m.version_id not in self.returned]
                    matches = [m for score, m in sorted(scores, key=lambda pair: (-pair[0], pair[1].version_id)) if score > 0]
                if task.action != "reanalyse":
                    matches = [m for m in matches if m.version_id not in self.returned]
                candidates[task.id] = sorted(matches, key=lambda item: item.version_id)

            def assign(task, matches, one=False):
                matched = [item for item in chosen
                           if any(item.version_id == candidate.version_id
                                  for candidate in matches)]
                for item in matches:
                    if item.version_id in {value.version_id for value in chosen}:
                        continue
                    if len(chosen) >= limit:
                        break
                    chosen.append(item)
                    matched.append(item)
                    if one:
                        break
                for item in matched:
                    attribution.setdefault(item.version_id, set()).add(task.id)

            def cover_one_each(group):
                """Greedily cover constrained tasks before filling capacity."""
                pending = list(group)
                while pending and len(chosen) < limit:
                    # Existing selections can satisfy several obligations.
                    covered = []
                    for task in pending:
                        matches = candidates[task.id]
                        matching_chosen = [
                            item for item in chosen
                            if any(item.version_id == candidate.version_id
                                   for candidate in matches)
                        ]
                        if matching_chosen:
                            for item in matching_chosen:
                                attribution.setdefault(
                                    item.version_id, set()).add(task.id)
                            covered.append(task.id)
                    if covered:
                        pending = [task for task in pending
                                   if task.id not in covered]
                        continue

                    selectable = [task for task in pending
                                  if any(item.version_id not in {
                                      value.version_id for value in chosen}
                                         for item in candidates[task.id])]
                    if not selectable:
                        break
                    # Most constrained task first. For it, choose the version
                    # covering the most still-pending tasks (deterministic
                    # bounded set-cover heuristic).
                    task = min(selectable, key=lambda item: (
                        len(candidates[item.id]),
                        priority[item.action], item.locator or "",
                        item.question, item.id))
                    remaining_ids = {item.id for item in pending}
                    options = [item for item in candidates[task.id]
                               if item.version_id not in {
                                   value.version_id for value in chosen}]
                    selected = min(options, key=lambda item: (
                        -sum(item.version_id in {
                            candidate.version_id
                            for candidate in candidates[other.id]}
                             for other in ordered_tasks
                             if other.id in remaining_ids),
                        item.version_id))
                    chosen.append(selected)
                    for other in ordered_tasks:
                        if any(selected.version_id == candidate.version_id
                               for candidate in candidates[other.id]):
                            attribution.setdefault(
                                selected.version_id, set()).add(other.id)

            # Exact obligations keep priority, but one shared version can
            # satisfy several and constrained tasks are scheduled first.
            cover_one_each([
                task for task in ordered_tasks
                if task.action in {"fetch", "reanalyse"}
            ])
            # Then give each broad query one result before any query fills the
            # rest of the bounded round capacity.
            cover_one_each([
                task for task in ordered_tasks if task.action == "search"
            ])
            for task in ordered_tasks:
                assign(task, candidates[task.id])

        return chosen, attribution, ordered_tasks, candidates

    def _commit(self, tasks, round_number, limit, chosen, consumed,
                attribution, ordered_tasks, candidates):
        consumed_ids = {item.version_id for item in consumed}
        actual_attribution = {
            version_id: tuple(sorted(task_ids))
            for version_id, task_ids in attribution.items()
            if version_id in consumed_ids
        }
        feedback = []
        for task in ordered_tasks:
            attributed = [item for item in consumed
                          if task.id in actual_attribution.get(item.version_id, ())]
            unconsumed_match = any(
                item.version_id not in consumed_ids
                for item in candidates.get(task.id, ()))
            status = ("returned" if attributed else
                      "budget_exhausted" if unconsumed_match else "unavailable")
            reason = ("matching snapshots returned" if attributed else
                      "round capacity ended before this task returned" if status == "budget_exhausted" else
                      "no unseen match in fixed snapshot index; live web unavailable")
            feedback.append({
                "gap_id": task.id, "action": task.action,
                "locator": task.locator, "status": status,
                "reason": reason,
                "version_ids": [item.version_id for item in attributed],
            })
        self.last_attribution = actual_attribution
        self.last_feedback = feedback
        self.returned.update(consumed_ids)
        self.history.append({
            "round": round_number, "tasks": [asdict(task) for task in tasks],
            "planned_ids": [item.version_id for item in chosen],
            "returned_ids": [item.version_id for item in consumed],
            "attribution": {key: list(value)
                            for key, value in actual_attribution.items()},
            "feedback": feedback[:],
        })

    def _stream(self, tasks, round_number, limit, envelopes):
        chosen, attribution, ordered_tasks, candidates = self._select(
            tasks, round_number, limit)
        consumed = []
        try:
            for material in chosen:
                consumed.append(material)
                if envelopes:
                    yield RetrievalHit(
                        material,
                        tuple(sorted(attribution.get(material.version_id, ()))))
                else:
                    yield material
        finally:
            self._commit(tasks, round_number, limit, chosen, consumed,
                         attribution, ordered_tasks, candidates)

    def search(self, target, tasks, round_number, limit):
        """Legacy bare-material API; the engine prefers ``search_hits``."""
        return self._stream(tasks, round_number, limit, False)

    def search_hits(self, target, tasks, round_number, limit):
        return self._stream(tasks, round_number, limit, True)
