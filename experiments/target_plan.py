"""Deterministic, immutable target obligations for staged verification.

The plan is derived only from the frozen target text.  It never sees material,
model output or gold labels, so later retrieval cannot silently rewrite what
has to be checked.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
import re


TARGET_PLAN_VERSION = "deterministic-target-plan-v6"
MAX_PROBES = 8

_SENTENCE_BREAK = re.compile(r"[;；。!?！？]+|(?<!\d)\.(?!\d)")
_CLAUSE_BREAK = re.compile(r"\s+(?:and|as well as)\s+|并且|且", re.IGNORECASE)
_CONDITIONAL = re.compile(r"\b(?:if|unless|provided that|when)\b|如果|若|除非", re.IGNORECASE)
_MONTHS = ("january|february|march|april|may|june|july|august|"
           "september|october|november|december")
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_YEAR = r"(?:19|20)\d{2}"
_QUARTER_PERIOD = (
    rf"(?:(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter"
    rf"(?:\s+of)?\s+{_YEAR}|q[1-4]\s+{_YEAR})"
)
_YEAR_PERIOD = rf"(?:in|during|by|through|throughout)\s+{_YEAR}"
_TIME_SIGNAL = re.compile(
    rf"\b(?:before|after|until|since|today|tomorrow|yesterday|as of|"
    rf"{_WEEKDAYS}|{_MONTHS}|{_QUARTER_PERIOD}|{_YEAR_PERIOD})\b|"
    r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|"
    r"\b\d{1,2}:\d{2}(?:\s*[ap]m)?\b|\b\d{1,2}\s*[ap]m\b|"
    r"截至|之前|之后|直到|今天|明天|昨日|周[一二三四五六日天]|"
    r"\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?",
    re.IGNORECASE,
)
_TEMPORAL_VALUE = re.compile(
    rf"\b(?:{_QUARTER_PERIOD}|{_YEAR_PERIOD})\b|"
    rf"\b(?:{_MONTHS})(?:\s+\d{{1,2}}(?:,?\s+\d{{4}})?|\s+{_YEAR})\b|"
    r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|"
    r"\b\d{1,2}:\d{2}(?:\s*[ap]m)?\b|\b\d{1,2}\s*[ap]m\b|"
    r"\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?",
    re.IGNORECASE,
)
_IRREGULAR_PREDICATES = (
    "arose|ate|became|began|broke|brought|built|bought|burst|came|caught|"
    "chose|cost|cut|did|drew|drove|fell|felt|found|gave|got|grew|had|heard|"
    "held|hit|hurt|kept|knew|led|left|let|lost|made|meant|met|paid|put|ran|"
    "read|said|saw|sent|set|shut|sold|spoke|spread|stood|taught|thought|"
    "told|took|understood|went|won|wrote"
)
_PREDICATE = re.compile(
    r"\b(?:is|are|was|were|be|been|has|have|had|do|does|did|will|would|"
    r"can|could|may|might|must|should|" + _IRREGULAR_PREDICATES +
    r"|[a-z]{3,}(?:ed|ing|s))\b",
    re.IGNORECASE,
)
_SCOPE_VERB_THAT = re.compile(
    r"\b(?:allege[ds]?|say|says|said|report(?:s|ed)?|claim(?:s|ed)?|"
    r"state[ds]?|announce[ds]?|believe[ds]?|expect(?:s|ed)?)\s+that\b",
    re.IGNORECASE,
)
_REPORTING_PREDICATE = re.compile(
    r"\b(?:allege[ds]?|say|says|said|report(?:s|ed)?|claim(?:s|ed)?|"
    r"state[ds]?|announce[ds]?|believe[ds]?|expect(?:s|ed)?|deny|denies|"
    r"denied)\b",
    re.IGNORECASE,
)
_NEGATION_SIGNAL = re.compile(
    r"\b(?:not|no|never|without|neither)\b|未|没有|并非|不得|无",
    re.IGNORECASE,
)
_PASSIVE_BY = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\b"
    r"[^.;!?。！？\n]*\bby\b",
    re.IGNORECASE,
)
_EVENT_BOUNDARY = re.compile(
    r"(?<!\d)[,.:]|[,.:](?!\d)|[，;；。!?！？\n]|"
    r"(?:--|—|–)|"
    r"\b(?:after|before|since|until)\b(?=\s+"
    r"(?:[A-Za-z]+\s+){0,4}" + _PREDICATE.pattern + r")|"
    r"\b(?:and|as|but|while|whereas|then|because|although|though|when|if|"
    r"unless)\b",
    re.IGNORECASE,
)
_TAIL_EVENT = re.compile(
    r"\b(?:[A-Z][A-Za-z]*|(?i:he|she|they|we|you|it|who)|"
    r"(?i:(?:the|a|an|another|other)\s+[a-z][a-z-]*))"
    r"(?:\s+(?i:not|never|also|then|now|already|directly|quickly|"
    r"successfully|is|are|was|were|has|have|had|will|would|can|could|"
    r"may|might|must|should)){0,4}\s+(?i:" + _PREDICATE.pattern + r")"
)
_LEADING_SCOPE_ONLY = re.compile(
    rf"^(?:"
    rf"(?:in|during|by|through|throughout|on|at|as\s+of)\s+"
    rf"(?:the\s+|a\s+)?(?:{_YEAR}|(?:{_MONTHS})(?:\s+{_YEAR})?|"
    rf"q[1-4]\s+{_YEAR}|{_QUARTER_PERIOD}|full[- ]year(?:\s+basis)?)|"
    rf"for\s+the\s+(?:full[- ]?)?year(?:\s+ended\s+.+)?"
    rf")$",
    re.IGNORECASE,
)
_HEADER_PUBLICATION_SUFFIX = re.compile(
    r"\b(?:filing\s+dated|filed|published|publication\s+date|dated)\b.*$",
    re.IGNORECASE,
)
_BODY_REPORT_PERIOD = re.compile(
    r"\b(?:full[- ]year|year\s+ended|fiscal\s+year|annual|quarter|"
    r"reporting\s+period|for\s+the\s+year)\b",
    re.IGNORECASE,
)
_LEADING_SHARED_SCOPE = re.compile(
    r"^(?:\s*(?:in|at|on|near|within|outside|across|under|over|before|after|"
    r"according\s+to)\b|\s*(?:在|于|截至|据))",
    re.IGNORECASE,
)
_CORE_DIMENSIONS = {"actor_subject", "predicate_object", "scope_location"}
_POTENTIALLY_SHARED_DIMENSIONS = {
    "time", "negation", "modality", "comparison_baseline",
}
_CORE_ACTION_EQUIVALENTS = {
    "commence": "start", "commenced": "start", "commences": "start",
    "commencing": "start", "begin": "start", "began": "start",
    "begun": "start", "begins": "start", "beginning": "start",
    "start": "start", "started": "start", "starts": "start",
    "starting": "start",
    "manufacture": "produce", "manufactured": "produce",
    "manufactures": "produce", "manufacturing": "produce",
    "produce": "produce", "produced": "produce", "produces": "produce",
    "producing": "produce",
    "reopen": "reopen", "reopened": "reopen", "reopens": "reopen",
    "reopening": "reopen", "remain": "remain", "remained": "remain",
    "remains": "remain", "remaining": "remain", "close": "close",
    "closed": "close", "closes": "close", "closing": "close",
    "operate": "operate", "operated": "operate", "operates": "operate",
    "operating": "operate",
}
_EVENT_QUALIFIER_TOKENS = {
    "will", "would", "can", "could", "may", "might", "must", "should",
    "more", "less", "than", "over", "under", "above", "below", "least",
    "most", "approximately", "about", "around", "nearly", "almost",
}
_SOURCE_HEADER = re.compile(
    r"\b(?:sec|form\s+\d+(?:[- ]?[kq])?|filing|filed|exhibit|results|"
    r"annual\s+report|quarterly\s+report|press\s+release)\b",
    re.IGNORECASE,
)
_TEMPORAL_LINKER = re.compile(
    r"\b(?:in|during|by|through|throughout|on|at)\s+(?:the\s+)?$",
    re.IGNORECASE,
)


def _sha(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def _trim(text, start, end):
    while start < end and (text[start].isspace() or text[start] in ",，"):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ",，"):
        end -= 1
    return start, end


def _has_predicate(value):
    return bool(_PREDICATE.search(value) or re.search(
        r"[\u3400-\u4dbf\u4e00-\u9fff]{2,}", value))


def _looks_like_clause(value):
    latin = re.findall(r"[A-Za-z]+", value)
    if len(latin) >= 2:
        return len(latin[-1]) >= 3 and latin[-1].islower()
    return len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value)) >= 4


def _has_independent_subject(value):
    """Require a visible subject before the first recognised Latin predicate."""
    if not re.search(r"[A-Za-z]", value):
        return True
    predicate = _PREDICATE.search(value)
    return bool(predicate and re.search(r"[A-Za-z]", value[:predicate.start()]))


def _compound_has_shared_scope(chunk, candidates, first_break_start):
    """Keep a compound intact when splitting could detach a shared modifier."""
    if _SCOPE_VERB_THAT.search(chunk[:first_break_start]):
        return True
    if _LEADING_SHARED_SCOPE.search(chunk):
        return True
    if "," in chunk[:first_break_start] or "，" in chunk[:first_break_start]:
        return True
    whole_dimensions = set(_dimensions(chunk))
    for dimension in _POTENTIALLY_SHARED_DIMENSIONS & whole_dimensions:
        if any(dimension not in _dimensions(value) for value in candidates):
            return True
    return False


def _dimensions(value):
    checks = ["actor_subject", "predicate_object", "scope_location"]
    without_temporal_values = _TEMPORAL_VALUE.sub("", value)
    if re.search(r"\d|%|％|\bpercent\b|百分之|[$€£¥￥]",
                 without_temporal_values, re.IGNORECASE):
        checks.append("quantity_unit_denominator")
    if _TIME_SIGNAL.search(value):
        checks.append("time")
    patterns = (
        ("negation", r"\b(?:not|no|never|without|neither)\b|未|没有|并非|不得|无"),
        ("condition", r"\b(?:if|unless|provided that|when)\b|如果|若|除非"),
        ("modality", r"\b(?:may|might|could|must|should|planned|expected|alleged)\b|"
                     r"可能|必须|应当|计划|预计|据称"),
        ("comparison_baseline", r"\b(?:more|less|than|versus|compared|increase|decrease)\b|"
                                r"相比|高于|低于|增加|减少"),
        ("attribution_causality", r"\b(?:according to|said|reported|because|caused by)\b|"
                                  r"据|表示|报道|因为|导致"),
    )
    for name, pattern in patterns:
        if re.search(pattern, value, re.IGNORECASE):
            checks.append(name)
    return checks


def build_target_plan(target):
    """Return stable, exact target spans that must each receive one result."""
    raw = asdict(target) if is_dataclass(target) else dict(target)
    text = raw.get("text")
    identifier = raw.get("id")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("target plan needs nonempty target text")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("target plan needs nonempty target id")

    chunks = []
    cursor = 0
    for match in _SENTENCE_BREAK.finditer(text):
        start, end = _trim(text, cursor, match.start())
        if start < end:
            chunks.append((start, end))
        cursor = match.end()
    start, end = _trim(text, cursor, len(text))
    if start < end:
        chunks.append((start, end))
    if not chunks:
        start, end = _trim(text, 0, len(text))
        chunks = [(start, end)]
    # Period heuristics can see abbreviations as boundaries. Merge any fragment
    # without a predicate into its following clause (or the prior clause at
    # end) so "U.S." and "Dr." never become standalone obligations.
    normalized, pending_start = [], None
    for chunk_start, chunk_end in chunks:
        if pending_start is not None:
            chunk_start = pending_start
            pending_start = None
        candidate_text = text[chunk_start:chunk_end]
        abbreviation_prefix = bool(re.search(
            r"(?:^|[.\s])[A-Za-z]$", candidate_text))
        if abbreviation_prefix or not _has_predicate(candidate_text):
            pending_start = chunk_start
        else:
            normalized.append((chunk_start, chunk_end))
    if pending_start is not None:
        if normalized:
            normalized[-1] = (normalized[-1][0], chunks[-1][1])
        else:
            normalized = [(pending_start, chunks[-1][1])]
    chunks = normalized

    spans = []
    for chunk_start, chunk_end in chunks:
        chunk = text[chunk_start:chunk_end]
        if _CONDITIONAL.search(chunk):
            spans.append((chunk_start, chunk_end))
            continue
        candidates, local, breaks = [], 0, []
        for match in _CLAUSE_BREAK.finditer(chunk):
            breaks.append(match)
            left = _trim(text, chunk_start + local, chunk_start + match.start())
            if left[0] < left[1]:
                candidates.append(left)
            local = match.end()
        tail = _trim(text, chunk_start + local, chunk_end)
        if tail[0] < tail[1]:
            candidates.append(tail)
        candidate_texts = [text[item_start:item_end]
                           for item_start, item_end in candidates]
        shared_scope = bool(
            len(candidates) > 1 and breaks
            and _compound_has_shared_scope(
                chunk, candidate_texts, breaks[0].start()))
        if shared_scope:
            spans.append((chunk_start, chunk_end))
        elif len(candidates) > 1 and all(
                _has_predicate(value) and _has_independent_subject(value)
                for value in candidate_texts):
            spans.extend(candidates)
        elif len(candidates) > 1 and all(
                _looks_like_clause(value) for value in candidate_texts):
            raise ValueError(
                "ambiguous compound target cannot be safely split")
        else:
            spans.append((chunk_start, chunk_end))

    if len(spans) > MAX_PROBES:
        raise ValueError("target exceeds deterministic probe bound")
    probes = []
    for number, (probe_start, probe_end) in enumerate(spans, 1):
        probe_text = text[probe_start:probe_end]
        probe_id = identifier + ":probe:" + _sha(
            [identifier, probe_start, probe_end, probe_text])[:20]
        probes.append({
            "number": number,
            "id": probe_id,
            "text": probe_text,
            "start": probe_start,
            "end": probe_end,
            "required_dimensions": _dimensions(probe_text),
        })
    body = {
        "version": TARGET_PLAN_VERSION,
        "target_id": identifier,
        "target_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "operator": "all",
        "probes": probes,
    }
    body["plan_sha256"] = _sha(body)
    return body


def evidence_terms(value):
    """High-signal overlap gate for a probe and its purported exact basis."""
    stop = {"the", "and", "that", "this", "with", "from", "before", "after",
            "until", "has", "have", "had", "was", "were", "will"}
    terms = set(re.findall(r"[a-z0-9%]{3,}", value.lower())) - stop
    for sequence in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", value):
        widths = (1,) if len(sequence) == 1 else (2, 3)
        for width in widths:
            terms.update(sequence[index:index + width]
                         for index in range(len(sequence) - width + 1))
    return terms


def _word_forms(token):
    token = token.lower()
    forms = {token}
    if token.endswith("ing") and len(token) > 5:
        root = token[:-3]
        forms.update((root, root + "e"))
    if token.endswith("ed") and len(token) > 4:
        root = token[:-2]
        forms.update((root, root + "e"))
    if token.endswith("es") and len(token) > 4:
        root = token[:-2]
        forms.update((root, root + "e", token[:-1]))
    elif token.endswith("s") and len(token) > 3:
        forms.add(token[:-1])
    return forms


def _content_tokens(value):
    ignored = {
        "the", "and", "that", "this", "with", "from", "before", "after",
        "until", "since", "today", "tomorrow", "yesterday", "well", "also",
        "for", "into", "onto", "over", "under", "between", "during", "about",
        "will", "would", "can", "could", "may", "might", "must", "should",
        "has", "have", "had", "was", "were", "are", "does", "did", "not",
    }
    return [token for token in re.findall(r"[a-z]{3,}", value.lower())
            if token not in ignored]


def _claim_tokens(value):
    """Surface tokens whose order preserves actors and scope binding."""
    ignored = {"the", "a", "an"}
    return [token for token in re.findall(r"[a-z]+", value.lower())
            if token not in ignored]


def _without_temporal_surface(value):
    """Blank only target-plan-recognised temporal spans and their linkers."""
    covered = [False] * len(value)
    for pattern in (_TEMPORAL_VALUE, _TIME_SIGNAL):
        for match in pattern.finditer(value):
            start, end = match.span()
            linker = _TEMPORAL_LINKER.search(value[:start])
            if linker is not None:
                start = linker.start()
            covered[start:end] = [True] * (end - start)
    return "".join(" " if hidden else character
                   for character, hidden in zip(value, covered))


def _core_claim_tokens(value):
    """Canonical core surface while retaining role and conjunction order."""
    tokens = _claim_tokens(_without_temporal_surface(value))
    result = []
    for index, token in enumerate(tokens):
        # A retrospective outcome can support the future action without
        # repeating its auxiliary, but do not discard auxiliaries generally.
        if (token in {"will", "would"} and index + 1 < len(tokens)
                and tokens[index + 1] in _CORE_ACTION_EQUIVALENTS):
            continue
        result.append(_CORE_ACTION_EQUIVALENTS.get(token, token))
    return result


def _predicate_role_parts(value):
    """Return conservative subject, predicate and object/scope token roles."""
    surface = _without_temporal_surface(value)
    auxiliaries = {
        "is", "are", "was", "were", "be", "been", "has", "have", "had",
        "do", "does", "did", "will", "would", "can", "could", "may",
        "might", "must", "should",
    }
    candidates = list(_PREDICATE.finditer(surface))
    candidates.extend(
        match for match in re.finditer(r"\b[a-z]+\b", surface, re.IGNORECASE)
        if match.group().lower() in _CORE_ACTION_EQUIVALENTS)
    candidates.sort(key=lambda item: (item.start(), item.end()))
    # Suffix heuristics can mistake a capitalized subject such as "Boeing"
    # or "Officials" for a verb. Prefer an explicit auxiliary; otherwise
    # require a visible subject before the predicate when one exists.
    predicate = next(
        (item for item in candidates if item.group().lower() in auxiliaries),
        None)
    if predicate is None:
        predicate = next(
            (item for item in candidates
             if _content_tokens(surface[:item.start()])),
            candidates[0] if candidates else None)
    if predicate is None:
        tokens = _core_claim_tokens(surface)
        return tokens, [], []
    before = _core_claim_tokens(surface[:predicate.start()])
    after = _core_claim_tokens(surface[predicate.end():])
    if predicate.group().lower() in auxiliaries and after:
        # The first content word after an auxiliary is the predicate head.
        while after and after[0] in {
                "not", "never", "currently", "expected", "planned"}:
            after = after[1:]
        if not after:
            return before, [], []
        head, after = [after[0]], after[1:]
    else:
        head = [_CORE_ACTION_EQUIVALENTS.get(
            predicate.group().lower(), predicate.group().lower())]
    return before, head, after


def _event_role_parts(value):
    """Return the actor/action/object skeleton after removing qualifiers."""
    subject, predicate, object_scope = _predicate_role_parts(value)
    clean = lambda values: [
        token for token in values
        if token not in _EVENT_QUALIFIER_TOKENS and not token.isdigit()
    ]
    return clean(subject), clean(predicate), clean(object_scope)


def _sequence_positions(needles, haystack, start=0):
    """Return ordered matching token positions or ``None``."""
    positions, cursor = [], start
    for needle in needles:
        forms = _word_forms(needle)
        while cursor < len(haystack):
            candidate = haystack[cursor]
            cursor += 1
            if forms & _word_forms(candidate):
                positions.append(cursor - 1)
                break
        else:
            return None
    return positions


def _canonical_tokens(value):
    return [_CORE_ACTION_EQUIVALENTS.get(token, token)
            for token in _claim_tokens(_without_temporal_surface(value))
            if token not in _EVENT_QUALIFIER_TOKENS]


def _bounded_action_object_spans(action, object_scope, value):
    """Return action/object spans that do not cross an event boundary.

    A comma in a thousands-formatted number is not a boundary.  All other
    listed punctuation and coordinating words fail closed: evidence for an
    object after one of them belongs to a potentially different event.
    """
    surface = _without_temporal_surface(value)
    words = list(re.finditer(r"[A-Za-z]+", surface))
    tokens = [_CORE_ACTION_EQUIVALENTS.get(
        item.group().lower(), item.group().lower()) for item in words]
    spans, cursor = [], 0
    while cursor < len(tokens):
        action_positions = _sequence_positions(action, tokens, cursor)
        if action_positions is None:
            break
        action_start = words[action_positions[0]].start()
        action_end = words[action_positions[-1]].end()
        prior_boundaries = list(_EVENT_BOUNDARY.finditer(
            value[:action_start]))
        clause_start = (prior_boundaries[-1].end()
                        if prior_boundaries else 0)
        next_boundary = _EVENT_BOUNDARY.search(value, action_end)
        clause_end = next_boundary.start() if next_boundary else len(value)

        object_positions = (_sequence_positions(
            object_scope, tokens, action_positions[-1] + 1)
                            if object_scope else [])
        if (object_scope and (object_positions is None
                              or words[object_positions[-1]].end()
                              > clause_end)):
            cursor = action_positions[0] + 1
            continue
        if object_positions:
            gap = surface[action_end:words[object_positions[0]].start()]
            # Punctuation and conjunction lists are not exhaustive. A second
            # predicate or capitalized actor before the requested object is
            # independent evidence that the object belongs to another event.
            if (_PREDICATE.search(gap)
                    or re.search(r"\b[A-Z][A-Za-z]*\b", gap)):
                cursor = action_positions[0] + 1
                continue
        phrase_end = (words[object_positions[-1]].end()
                      if object_positions else action_end)
        later_event = _TAIL_EVENT.search(value[phrase_end:clause_end])
        if later_event is not None:
            clause_end = phrase_end + later_event.start()
        spans.append((clause_start, action_start, phrase_end, clause_end))
        cursor = action_positions[0] + 1
    return tuple(spans)


def _body_action_object_matches(action, object_scope, value):
    """Bind one action and its object within one visible clause."""
    if _PASSIVE_BY.search(value):
        return False
    return len(_bounded_action_object_spans(action, object_scope, value)) == 1


def _leading_scope_start(value, clause_start):
    """Attach one non-event leading time/report modifier to a binding."""
    if clause_start <= 0:
        return 0
    earlier = list(_EVENT_BOUNDARY.finditer(value[:clause_start - 1]))
    candidate_start = earlier[-1].end() if earlier else 0
    candidate = value[candidate_start:clause_start].strip(" \t,，")
    if not _LEADING_SCOPE_ONLY.fullmatch(candidate):
        return clause_start
    return candidate_start


def _normal_event_passages(subject, action, object_scope, value):
    """Return locally bound actor/action/object passages."""
    if _PASSIVE_BY.search(value):
        return ()
    bindings = _bounded_action_object_spans(action, object_scope, value)
    # Multiple same-metric events in one supplied passage make qualifier and
    # number ownership ambiguous.  Fail closed instead of selecting one by
    # position or aggregating their values.
    if len(bindings) != 1:
        return ()
    result = []
    for clause_start, _, _, clause_end in bindings:
        event = value[clause_start:clause_end]
        tokens = _canonical_tokens(event)
        subject_positions = _sequence_positions(subject, tokens)
        if subject_positions is None:
            continue
        action_positions = _sequence_positions(
            action, tokens, subject_positions[-1] + 1)
        if action_positions is None:
            continue
        object_positions = (_sequence_positions(
            object_scope, tokens, action_positions[-1] + 1)
                            if object_scope else [])
        if object_scope and object_positions is None:
            continue

        # A reporting predicate or a second named actor between the target
        # actor and action changes who performed the action. This rejects, for
        # example, "Alice said Bob bought Widget" for "Alice bought Widget".
        raw_tokens = list(re.finditer(r"[A-Za-z]+", event))
        canonical_matches = [
            _CORE_ACTION_EQUIVALENTS.get(
                item.group().lower(), item.group().lower())
            for item in raw_tokens
        ]
        raw_subject = _sequence_positions(subject, canonical_matches)
        raw_action = (_sequence_positions(
            action, canonical_matches, raw_subject[-1] + 1)
                      if raw_subject is not None else None)
        if raw_subject is None or raw_action is None:
            continue
        prefix = event[:raw_tokens[raw_subject[0]].start()]
        binding_prefix = prefix.rsplit(",", 1)[-1]
        if (_REPORTING_PREDICATE.search(prefix)
                or _PREDICATE.search(binding_prefix)):
            continue
        between = raw_tokens[raw_subject[-1] + 1:raw_action[0]]
        auxiliaries = {
            "is", "are", "was", "were", "be", "been", "has", "have",
            "had", "do", "does", "did", "will", "would", "can", "could",
            "may", "might", "must", "should",
        }
        safe_modifiers = {
            "also", "then", "now", "already", "directly", "personally",
            "successfully", "subsequently", "previously", "recently",
            "not", "never",
        }
        invalid = False
        passive_auxiliaries = {"is", "are", "was", "were", "be", "been",
                               "being"}
        action_surface = raw_tokens[raw_action[-1]].group().lower()
        for item in between:
            token = item.group()
            lowered = token.lower()
            if (subject != ["there"] and lowered in passive_auxiliaries
                    and not action_surface.endswith("ing")):
                invalid = True
                break
            if lowered not in auxiliaries and _PREDICATE.fullmatch(token):
                invalid = True
                break
            if token[:1].isupper():
                invalid = True
                break
            if (lowered not in auxiliaries and lowered not in safe_modifiers
                    and not lowered.endswith("ly")):
                invalid = True
                break
        if not invalid:
            passage_start = _leading_scope_start(value, clause_start)
            passage = value[passage_start:clause_end].strip()
            if passage:
                result.append(passage)
    return tuple(result)


def _normal_event_clause_matches(subject, action, object_scope, value):
    """Bind actor, action and object without crossing a clause boundary."""
    return bool(_normal_event_passages(subject, action, object_scope, value))


def _issuer_alias_passages(alias, action, object_scope, value):
    """Accept a filing pronoun only as the event's independent subject."""
    allowed_tail = {
        "also", "then", "now", "already", "directly", "personally",
        "successfully", "subsequently", "previously", "recently", "not",
        "never", "is", "are", "was", "were", "be", "been", "has",
        "have", "had", "do", "does", "did", "will", "would", "can",
        "could", "may", "might", "must", "should",
    }
    result = []
    for passage in _normal_event_passages(
            alias, action, object_scope, value):
        bindings = _bounded_action_object_spans(
            action, object_scope, passage)
        if len(bindings) != 1:
            continue
        clause_start, action_start, _, _ = bindings[0]
        prefix = [token.lower() for token in re.findall(
            r"[A-Za-z]+", passage[clause_start:action_start])]
        expected = (["we"] if alias == ["we"] else
                    ["our", "company"] if alias == ["our", "company"] else
                    ["company"])
        if alias == ["company"] and prefix[:2] == ["the", "company"]:
            prefix = prefix[1:]
        if (prefix[:len(expected)] == expected
                and all(token in allowed_tail
                        for token in prefix[len(expected):])):
            result.append(passage)
    return tuple(result)


def _header_names_issuer(subject, header):
    """Require a report heading to begin with the target issuer name."""
    if not subject or not _SOURCE_HEADER.search(header):
        return False
    subject_pattern = r"\W+".join(re.escape(token) for token in subject)
    match = re.match(rf"^\s*{subject_pattern}\b", header, re.IGNORECASE)
    if match is None:
        return False
    suffix = header[match.end():]
    if re.search(r"\b(?:about|by|for|on|versus|vs\.?)\b", suffix,
                 re.IGNORECASE):
        return False
    return bool(re.match(
        r"^\s*(?:(?:q[1-4]|fy)\s+)?(?:(?:19|20)\d{2}\s+)?"
        r"(?:form\b|results\b|annual\s+report\b|quarterly\s+report\b|"
        r"press\s+release\b)", suffix, re.IGNORECASE))


def _direct_opposition_passages(subject, action, object_scope, value):
    """Return local passages containing one closed, explicit opposition."""
    if action != ["reopen"]:
        return ()
    parts, cursor = [], 0
    for boundary in _EVENT_BOUNDARY.finditer(value):
        if cursor < boundary.start():
            parts.append(value[cursor:boundary.start()].strip())
        cursor = boundary.end()
    if cursor < len(value):
        parts.append(value[cursor:].strip())

    result = []
    for passage in parts:
        if not passage:
            continue
        basis_subject, basis_action, basis_object = _event_role_parts(passage)
        if _sequence_positions(subject, basis_subject) is None:
            continue
        if (object_scope
                and _sequence_positions(object_scope, basis_object) is None):
            continue
        if basis_action == ["remain"] and "close" in basis_object:
            result.append(passage)
    return tuple(result)


def _direct_opposition_clause_matches(subject, action, object_scope, value):
    """Recognise only closed, explicit action oppositions."""
    return bool(_direct_opposition_passages(
        subject, action, object_scope, value))


def _event_anchor_passages(probe_text, basis_text):
    """Return visible sub-passages that bind the target event skeleton.

    A source heading may supply the issuer only when it is visibly a filing or
    results heading and the immediately supplied body carries the action and
    object. Ordinary prose must bind all three roles inside one clause.
    """
    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", probe_text):
        passages = [item.strip() for item in re.split(
            r"[，,；;。!?！？\n]+|(?:然而|然后|因为|尽管|同时|而|但)",
            basis_text) if item.strip()]
        return [passage for passage in passages
                if _ordered_supported_surface(probe_text, passage)]
    subject, action, object_scope = _event_role_parts(probe_text)
    if not subject or not action:
        # English role grounding without a recognized action is not safe to
        # infer by token overlap: doing so can stitch an actor in one event to
        # an unknown verb/object in another. Unsupported grammar stays
        # unresolved until a deterministic predicate rule is added.
        return []

    clauses = [item.strip() for item in re.split(
        r"(?:[;；。!?！？]+|(?<!\d)\.(?!\d)|\n+|"
        r"\s+(?:and|as\s+well\s+as)\s+)", basis_text,
        flags=re.IGNORECASE)
               if item.strip()]
    result = []
    for clause in clauses:
        result.extend(_normal_event_passages(
            subject, action, object_scope, clause))
        result.extend(_direct_opposition_passages(
            subject, action, object_scope, clause))

    lines = [item.strip() for item in basis_text.splitlines() if item.strip()]
    if len(lines) < 2 or not _header_names_issuer(subject, lines[0]):
        return result
    # Only the immediately adjacent body may inherit issuer context. Remove
    # publication-date suffixes from the semantic projection so a filing date
    # can never masquerade as the event date.
    body = lines[1]
    issuer_passages = []
    for alias in (["company"], ["we"], ["our", "company"]):
        issuer_passages.extend(_issuer_alias_passages(
            alias, action, object_scope, body))
    issuer_passages = list(dict.fromkeys(issuer_passages))
    # A nominal event can inherit the filing issuer only through explicit
    # first-person ownership in the body.  A quoted product or flight brand is
    # not actor evidence: e.g. "Beta's 'Acme One' flight" must not be assigned
    # to Acme merely because Acme appears in the quoted name.
    issuer_owned_start = (
        action == ["start"]
        and not _REPORTING_PREDICATE.search(body)
        and bool(re.fullmatch(
            r"\s*(?:in\s+[^,]+,\s+)?we\s+[^,]+,\s*"
            r"(?:['\"][^'\"]+['\"]\s*)?which\s+marked\s+the\s+"
            r"(?:start|beginning)\s+of\s+our\b[^.!?]*[.!?]?\s*",
            body, re.IGNORECASE))
        and bool(re.search(
            r"\bmarked\s+the\s+(?:start|beginning)\s+of\s+our\b",
            body, re.IGNORECASE)))
    body_passages = issuer_passages or ([body] if issuer_owned_start else [])
    if (body_passages
            and _body_action_object_matches(action, object_scope, body)):
        semantic_header = _HEADER_PUBLICATION_SUFFIX.sub("", lines[0]).rstrip()
        body_time_markers = _temporal_markers(body)
        body_has_calendar = any(marker.startswith(("year:", "quarter:"))
                                for marker in body_time_markers)
        if body_has_calendar or not _BODY_REPORT_PERIOD.search(body):
            semantic_header = re.sub(r"\b(?:19|20)\d{2}\b", "",
                                     semantic_header)
        result.extend(semantic_header + "\n" + passage
                      for passage in body_passages)
    return list(dict.fromkeys(result))


def _supported_dimension_surface(dimension, probe_text, basis_text):
    """Check the target role locally; assembly supplies the shared anchor."""
    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", probe_text):
        return _ordered_supported_surface(probe_text, basis_text)
    subject, action, object_scope = _event_role_parts(probe_text)
    basis_tokens = _canonical_tokens(basis_text)
    if dimension == "actor_subject":
        return bool(subject) and _sequence_positions(subject, basis_tokens) is not None
    if dimension == "predicate_object":
        action_positions = _sequence_positions(action, basis_tokens)
        return bool(action_positions is not None and (
            not object_scope or _sequence_positions(
                object_scope, basis_tokens, action_positions[-1] + 1) is not None))
    if dimension == "scope_location":
        anchors = object_scope or subject
        return bool(anchors) and _sequence_positions(anchors, basis_tokens) is not None
    return True


def _ordered_token_match(target_tokens, basis_tokens):
    cursor = 0
    for target_token in target_tokens:
        target_forms = _word_forms(target_token)
        while cursor < len(basis_tokens):
            current = basis_tokens[cursor]
            cursor += 1
            if target_forms & _word_forms(current):
                break
        else:
            return False
    return True


def _ordered_supported_surface(probe_text, basis_text):
    """Fail closed on role reversal and detached conjunction scope."""
    target_tokens = _core_claim_tokens(probe_text)
    if target_tokens and not _ordered_token_match(
            target_tokens, _core_claim_tokens(basis_text)):
        return False
    target_cjk = re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff]", _without_temporal_surface(probe_text))
    basis_cjk = re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff]", _without_temporal_surface(basis_text))
    if target_cjk and not _ordered_token_match(target_cjk, basis_cjk):
        return False
    return True


def _predicate_markers(value):
    match = _PREDICATE.search(value)
    if match is None:
        return set()
    verb = match.group().lower()
    auxiliaries = {
        "is", "are", "was", "were", "be", "been", "has", "have", "had",
        "do", "does", "did", "will", "would", "can", "could", "may",
        "might", "must", "should",
    }
    if verb not in auxiliaries:
        return _word_forms(verb)
    tail = re.findall(r"[a-z]{3,}", value[match.end():].lower())
    ignored = {"not", "never", "before", "after", "until", "since",
               "today", "tomorrow", "yesterday", "than", "with", "from"}
    markers = set().union(*(_word_forms(token) for token in tail
                            if token not in ignored))
    return markers or {verb}


def _temporal_markers(value):
    lowered = value.lower()
    markers = set(re.findall(
        rf"\b(?:before|after|until|since|today|tomorrow|yesterday|"
        rf"{_WEEKDAYS}|{_MONTHS})\b", lowered))
    for match in _TEMPORAL_VALUE.finditer(value):
        matched = match.group().lower()
        # Quarter/year phrases are normalized below so equivalent calendar
        # expressions such as "second quarter" and "June" can agree.
        if re.fullmatch(
                rf"(?:{_QUARTER_PERIOD}|{_YEAR_PERIOD})", matched,
                re.IGNORECASE):
            continue
        markers.add(re.sub(r"\W+", "", matched))
    markers.update(re.findall(
        r"截至|之前|之后|直到|今天|明天|昨日|周[一二三四五六日天]|"
        r"\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?", value))
    if _TIME_SIGNAL.search(value):
        markers.update("year:" + year for year in re.findall(
            rf"\b({_YEAR})\b", lowered))
    quarter_names = {
        "first": "1", "1st": "1", "second": "2", "2nd": "2",
        "third": "3", "3rd": "3", "fourth": "4", "4th": "4",
    }
    for match in re.finditer(
            r"\b(?:(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter|"
            r"q([1-4]))\b", lowered):
        number = match.group(2) or quarter_names[match.group(1)]
        markers.add("quarter:" + number)
    month_quarters = {
        "january": "1", "february": "1", "march": "1",
        "april": "2", "may": "2", "june": "2",
        "july": "3", "august": "3", "september": "3",
        "october": "4", "november": "4", "december": "4",
    }
    for month in re.findall(rf"\b({_MONTHS})\b", lowered):
        markers.add("quarter:" + month_quarters[month])
    return {marker for marker in markers if marker}


def _quantity_markers(value):
    lowered = value.lower()
    markers = {"number:" + number
               for number in re.findall(r"\d+(?:\.\d+)?", lowered)}
    currency = {
        "$": "currency:usd", "usd": "currency:usd", "dollar": "currency:usd",
        "€": "currency:eur", "eur": "currency:eur", "euro": "currency:eur",
        "£": "currency:gbp", "gbp": "currency:gbp", "pound": "currency:gbp",
        "¥": "currency:yen-yuan", "￥": "currency:yen-yuan",
        "yuan": "currency:yen-yuan", "yen": "currency:yen-yuan",
    }
    for token, marker in currency.items():
        if token in lowered:
            markers.add(marker)
    if re.search(r"%|％|\bpercent(?:age)?\b|百分之", lowered):
        markers.add("unit:percent")
    for unit in re.findall(
            r"\b(?:thousand|million|billion|trillion|kg|kilogram|kilograms|"
            r"gram|grams|lb|lbs|pound|pounds|ounce|ounces|km|kilometer|"
            r"kilometers|meter|meters|centimeter|centimeters|mile|miles|"
            r"inch|inches|foot|feet|liter|liters|gallon|gallons|watt|watts|"
            r"kilowatt|kilowatts|volt|volts|amp|amps|hour|hours|day|days|"
            r"people|persons|users|shares|votes)\b", lowered):
        markers.add("unit:" + unit.rstrip("s"))
    for denominator in re.findall(
            r"\bper\s+([a-z]+)|/\s*([a-z]+)|\beach\s+([a-z]+)", lowered):
        value = next(item for item in denominator if item)
        markers.add("denominator:" + value.rstrip("s"))
    return markers


def _numeric_values(value):
    surface = _without_temporal_surface(value)
    values = []
    for match in re.finditer(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?", surface):
        try:
            values.append(float(match.group().replace(",", "")))
        except ValueError:
            continue
    return tuple(values)


def _single_event_metric_phrase(probe_text, basis_text):
    """Return the sole bound event metric clause, or ``None``."""
    _, action, object_scope = _event_role_parts(probe_text)
    if not action:
        return None
    event_surface = basis_text.split("\n", 1)[-1]
    bindings = _bounded_action_object_spans(
        action, object_scope, event_surface)
    if len(bindings) != 1:
        return None
    clause_start, _, phrase_end, _ = bindings[0]
    # Metric evidence ends with the target object/scope. Numbers or operators
    # after it may belong to a trailing comparison, forecast, adjunct, or
    # nominalized second event and are therefore not safely attributable.
    phrase = event_surface[clause_start:phrase_end]
    if re.search(
            r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?\s*[-–—]\s*[A-Za-z]+",
            phrase):
        return None
    # An observed value plus a forecast, baseline, or second metric in the
    # same clause cannot be assigned safely with surface matching alone.
    # Refuse the metric instead of picking the first or last number.
    if len(_numeric_values(phrase)) != 1:
        return None
    return phrase


def _event_metric_numeric_values(probe_text, basis_text):
    """Read numbers only from the target action-to-object metric phrase."""
    phrase = _single_event_metric_phrase(probe_text, basis_text)
    return _numeric_values(phrase) if phrase is not None else ()


def _event_metric_quantity_markers(probe_text, basis_text):
    """Read units and numbers only from the single bound metric phrase."""
    phrase = _single_event_metric_phrase(probe_text, basis_text)
    return _quantity_markers(phrase) if phrase is not None else set()


def _quantity_contradiction_is_explicit(probe_text, basis_text):
    target_values = set(_numeric_values(probe_text))
    basis_values = set(_event_metric_numeric_values(probe_text, basis_text))
    return bool(target_values and basis_values
                and target_values.isdisjoint(basis_values))


def _comparison_constraint(value):
    lowered = value.lower()
    if re.search(r"\b(?:approximately|about|around|nearly|almost)\b", lowered):
        return "hedged", False
    if re.search(r"\b(?:at\s+most|up\s+to|no\s+more\s+than)\b", lowered):
        return "less", True
    if re.search(r"\b(?:at\s+least|no\s+less\s+than)\b", lowered):
        return "greater", True
    if re.search(r"\b(?:more\s+than|over|above|greater\s+than)\b", lowered):
        return "greater", False
    if re.search(r"\b(?:less\s+than|under|below|fewer\s+than)\b", lowered):
        return "less", False
    return None


def _comparison_relation(value):
    constraint = _comparison_constraint(value)
    return constraint[0] if constraint and constraint[0] != "hedged" else None


def _comparison_matches(probe_text, basis_text, verdict):
    target_constraint = _comparison_constraint(probe_text)
    target_values = _numeric_values(probe_text)
    basis_values = _event_metric_numeric_values(probe_text, basis_text)
    if (target_constraint is None or target_constraint[0] == "hedged"
            or len(target_values) != 1 or len(basis_values) != 1):
        return False
    target_units = {item for item in _quantity_markers(probe_text)
                    if not item.startswith("number:")}
    basis_units = {item for item in _event_metric_quantity_markers(
        probe_text, basis_text)
                   if not item.startswith("number:")}
    if target_units != basis_units:
        return False
    threshold = target_values[0]
    metric_phrase = _single_event_metric_phrase(probe_text, basis_text)
    basis_constraint = _comparison_constraint(metric_phrase or "")
    if basis_constraint and basis_constraint[0] == "hedged":
        return False
    direction, _ = target_constraint
    observed = basis_values[0]
    if basis_constraint is None:
        supported = (observed > threshold if direction == "greater"
                     else observed < threshold)
        contradicted = not supported
    else:
        basis_direction, inclusive = basis_constraint
        supported = contradicted = False
        if direction == "greater":
            if basis_direction == "greater":
                supported = (observed > threshold if inclusive
                             else observed >= threshold)
            else:
                contradicted = observed <= threshold
        else:
            if basis_direction == "less":
                supported = (observed < threshold if inclusive
                             else observed <= threshold)
            else:
                contradicted = observed >= threshold
    return supported if verdict == "supported" else contradicted


def _event_predicate_is_negated(probe_text, basis_text):
    """Recognise negation only when it binds the target predicate/object."""
    _, action, object_scope = _event_role_parts(probe_text)
    if not action:
        return False
    event_surface = basis_text.split("\n", 1)[-1]
    bindings = _bounded_action_object_spans(
        action, object_scope, event_surface)
    if len(bindings) != 1:
        return False
    clause_start, action_start, phrase_end, _ = bindings[0]
    before_action = event_surface[clause_start:action_start]
    action_object = event_surface[action_start:phrase_end]
    return bool(re.search(r"\b(?:not|never)\b", before_action,
                          re.IGNORECASE)
                or re.search(r"\bno\b", action_object, re.IGNORECASE))


def _time_contradiction_is_explicit(probe_text, basis_text):
    # A filing/results heading may identify issuer and report period, but its
    # publication date is never a contrary event date. Contradiction therefore
    # needs an explicit marker in the event body itself.
    event_surface = basis_text.split("\n", 1)[-1]
    target_markers = _temporal_markers(probe_text)
    basis_markers = _temporal_markers(event_surface)
    target_years = {item for item in target_markers if item.startswith("year:")}
    basis_years = {item for item in basis_markers if item.startswith("year:")}
    if target_years and basis_years and target_years.isdisjoint(basis_years):
        return True
    target_quarters = {
        item for item in target_markers if item.startswith("quarter:")}
    basis_quarters = {
        item for item in basis_markers if item.startswith("quarter:")}
    if (target_quarters and basis_quarters
            and target_quarters.isdisjoint(basis_quarters)):
        return True
    target_directions = target_markers & {"before", "after", "until", "since"}
    basis_directions = basis_markers & {"before", "after", "until", "since"}
    shared_reference = (target_markers - target_directions) & (
        basis_markers - basis_directions)
    incompatible = {
        ("before", "after"), ("before", "until"),
        ("after", "before"), ("until", "after"),
    }
    return bool(shared_reference and any(
        (left, right) in incompatible
        for left in target_directions for right in basis_directions))


def _predicate_contradiction_is_explicit(probe_text, basis_text):
    if (not _NEGATION_SIGNAL.search(probe_text)
            and _event_predicate_is_negated(probe_text, basis_text)):
        return True
    subject, action, object_scope = _event_role_parts(probe_text)
    clauses = [item.strip() for item in re.split(
        r"(?:[;；。!?！？]+|(?<!\d)\.(?!\d)|\n+|"
        r"\s+(?:and|as\s+well\s+as)\s+)", basis_text,
        flags=re.IGNORECASE) if item.strip()]
    return bool(subject and action and any(_direct_opposition_clause_matches(
        subject, action, object_scope, clause) for clause in clauses))


def dimension_signal_is_grounded(dimension, probe_text, basis_text,
                                 verdict="supported"):
    """Check one dimension locally; callers must also bind an event anchor."""
    if dimension == "time" and "\n" in basis_text:
        # Model-selected adjacent heading/body spans still contain filing
        # dates. Reuse the anchored semantic projection so publication time
        # cannot conflict with or satisfy the event's time obligation.
        anchored = _event_anchor_passages(probe_text, basis_text)
        if anchored:
            basis_text = "\n".join(anchored)
    probe_terms = evidence_terms(probe_text)
    basis_terms = evidence_terms(basis_text)
    quantity_terms = {term for term in probe_terms
                      if any(character.isdigit() for character in term)
                      or term in {"percent", "percentage"}}
    qualifier_terms = {
        "time": {"before", "after", "until", "since", "today", "tomorrow",
                 "yesterday", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "january", "february",
                 "march", "april", "june", "july", "august", "september",
                 "october", "november", "december"},
        "quantity_unit_denominator": quantity_terms,
        "modality": {"may", "might", "could", "must", "should", "planned",
                     "expected", "alleged"},
        "comparison_baseline": {"more", "less", "than", "versus", "compared",
                                "increase", "decrease", "higher", "lower"},
        "attribution_causality": {"according", "said", "reported", "because",
                                  "caused", "source", "statement"},
    }.get(dimension, set())
    anchor_patterns = {
        "time": r"\b(?:before|after|until|since|today|tomorrow|yesterday|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
                r"截至|之前|之后|直到|今天|明天|昨日|周[一二三四五六日天]",
        "negation": r"\b(?:not|no|never|without|neither)\b|未|没有|并非|不得|无",
        "condition": r"\b(?:if|unless|provided that|when)\b|如果|若|除非",
    }
    if dimension in anchor_patterns:
        for match in re.finditer(anchor_patterns[dimension], probe_text,
                                 re.IGNORECASE):
            qualifier_terms.update(evidence_terms(match.group()))
    core_terms = probe_terms - qualifier_terms
    if not (core_terms or probe_terms) & basis_terms:
        return False
    if verdict == "supported" and dimension in {
            "actor_subject", "predicate_object", "scope_location"}:
        if not _supported_dimension_surface(dimension, probe_text, basis_text):
            return False
    if dimension == "predicate_object" and verdict == "supported":
        if (not _NEGATION_SIGNAL.search(probe_text)
                and _event_predicate_is_negated(probe_text, basis_text)):
            return False
        markers = _predicate_markers(probe_text)
        basis_stems = set().union(*(
            _word_forms(token) for token in re.findall(
                r"[a-z]{3,}", basis_text.lower())))
        if markers and not markers & basis_stems:
            return False
    if dimension == "predicate_object" and verdict == "contradicted":
        if not _predicate_contradiction_is_explicit(probe_text, basis_text):
            return False
    if dimension == "time" and verdict == "supported":
        target_markers = _temporal_markers(probe_text)
        basis_markers = _temporal_markers(basis_text)
        if target_markers and not target_markers <= basis_markers:
            return False
        target_years = {item for item in target_markers
                        if item.startswith("year:")}
        basis_years = {item for item in basis_markers
                       if item.startswith("year:")}
        target_quarters = {item for item in target_markers
                           if item.startswith("quarter:")}
        basis_quarters = {item for item in basis_markers
                          if item.startswith("quarter:")}
        if ((target_years and basis_years - target_years)
                or (target_quarters and basis_quarters - target_quarters)
                or _time_contradiction_is_explicit(probe_text, basis_text)):
            return False
    if dimension == "time" and verdict == "contradicted":
        if not _time_contradiction_is_explicit(probe_text, basis_text):
            return False
    comparison_obligation = _comparison_relation(probe_text) is not None
    if dimension == "quantity_unit_denominator":
        if comparison_obligation and verdict in {"supported", "contradicted"}:
            # The threshold and operator form one obligation. A different
            # observed number is not independently a quantity contradiction.
            if not _comparison_matches(probe_text, basis_text, verdict):
                return False
        elif verdict == "supported":
            target_quantity = _quantity_markers(probe_text)
            basis_quantity = _event_metric_quantity_markers(
                probe_text, basis_text)
            if target_quantity and not target_quantity <= basis_quantity:
                return False
        elif verdict == "contradicted":
            if not _quantity_contradiction_is_explicit(probe_text, basis_text):
                return False
    if dimension == "comparison_baseline" and verdict in {
            "supported", "contradicted"}:
        if not _comparison_matches(probe_text, basis_text, verdict):
            return False
    signals = {
        "quantity_unit_denominator": r"\d|%|％|\bpercent\b|百分之|[$€£¥￥]",
        "time": r"\b(?:before|after|until|since|today|tomorrow|yesterday|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                r"january|february|march|april|may|june|july|august|september|"
                r"october|november|december|q[1-4]|full[- ]year|"
                r"year\s+ended|fiscal\s+year|(?:19|20)\d{2})\b|"
                r"\d{1,4}[-/:]\d|"
                r"截至|之前|之后|直到|今天|明天|昨日|周[一二三四五六日天]",
        "modality": r"\b(?:may|might|could|must|should|planned|expected|alleged|"
                    r"implemented|occurred|confirmed)\b|可能|必须|应当|计划|预计|据称|实施|发生|确认",
        "comparison_baseline": r"\b(?:more|less|than|versus|compared|increase|decrease|"
                               r"higher|lower)\b|相比|高于|低于|增加|减少|\d",
        "attribution_causality": r"\b(?:according to|said|reported|because|caused by|"
                                 r"source|statement)\b|据|表示|报道|因为|导致|来源|声明",
    }
    pattern = signals.get(dimension)
    if pattern is not None and not re.search(pattern, basis_text, re.IGNORECASE):
        return False
    if dimension == "negation" and verdict == "supported":
        return _event_predicate_is_negated(probe_text, basis_text)
    if dimension == "condition":
        return bool(re.search(
            r"\b(?:if|unless|provided that|when)\b|如果|若|除非",
            basis_text, re.IGNORECASE))
    return True


def dimension_evidence_is_grounded(dimension, probe_text, basis_text,
                                   verdict="supported"):
    """Require the dimension signal inside the same grounded event passage."""
    return any(dimension_signal_is_grounded(
        dimension, probe_text, passage, verdict)
               for passage in _event_anchor_passages(probe_text, basis_text))


__all__ = ["TARGET_PLAN_VERSION", "build_target_plan", "evidence_terms",
           "dimension_evidence_is_grounded", "dimension_signal_is_grounded"]
