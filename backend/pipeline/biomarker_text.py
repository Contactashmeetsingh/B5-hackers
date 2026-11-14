"""Read a profile biomarker's status out of free text: trial criteria, paper titles.

Used by stage 4 (does a trial require HER2-positive? a PIK3CA mutation?) and by
stage 1 (is a search hit about HER2-negative disease?). Generalised from the old
scoring module's HER2 heuristic, which had been tested on ClinicalTrials.gov text.

classify(text, biomarker) looks at every occurrence of the biomarker's aliases:

  negated   right after it: "HER2-negative", "HER2-", "HER2[-]", "PIK3CA wild-type";
            or just before it: "no PIK3CA mutation", "negative for HER2", "without HER2 amplification";
            or a cue between it and its status word: "HER2 not overexpressed", "PIK3CA non-mutated"
  low       "HER2-low", "HER2-ultralow": a HER2-negative category, so it conflicts with "positive"
  positive  "HER2+", or a status word on the same line within STATUS_WINDOW_CHARS:
            expression kind: positive, overexpression, amplified, IHC, ISH/FISH, 3+
            mutation kind:   mutated, mutation, mutant, variant, alteration, hotspot
            ("PIK3CA mutation status" / "testing" is a hedge, not a requirement)

The decision is per text, not per occurrence:
  required   some occurrence is positive and none is negated
  mentioned  named, but not as a requirement (or both positive and negated: mixed cohorts)
  conflicts  negated or low (when the profile wants positive), and never positive
  absent     not named at all

Known misses: status word first ("positive for HER2") reads as mentioned. Good enough
for a demo; the matched line is always shown so a person can check it.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from backend import config
from backend.pipeline.textmatch import alias_pattern, line_around
from backend.schemas import ProfileBiomarker

REQUIRED, MENTIONED, CONFLICTS, ABSENT = "required", "mentioned", "conflicts", "absent"

_STATUS = {
    "expression": re.compile(r"(?i:positiv|over-?express|amplif)|IHC|FISH|ISH\b|(?<![0-9])[0-3]\+"),
    "mutation": re.compile(r"(?i:mutat|mutant|(?<![A-Za-z])variant|alteration|altered|hotspot)"),
}
# "PIK3CA mutation status", "HER2 amplification testing": the trial records the status, it does not select on it.
_HEDGE_AFTER_STATUS = re.compile(r"[A-Za-z]*\s+(?:status|testing|test)\b", re.IGNORECASE)
_LOW = re.compile(r"(?i)(?<![A-Za-z])(?:ultra-?)?low\b")
_NEG_AFTER = {
    "expression": re.compile(r"\s*-?\s*neg(?:ative)?\b|-(?![A-Za-z0-9])|\[\s*-\s*\]", re.IGNORECASE),
    "mutation": re.compile(r"\s*-?\s*(?:wild[\s-]?type|wt\b|non-?mutat|unmutated|neg(?:ative)?\b)", re.IGNORECASE),
}
_POSITIVE_SIGN = re.compile(r"\+(?![0-9])|\[\s*\+\s*\]")
_CUE = re.compile(
    r"(?i:(?P<neg>\bnot\b|\bno\b|\bwithout\b|\bnon-?(?=amplif|over|positiv|mutat)|negativ|wild[\s-]?type)"
    r"|equivocal|ineligib|unknown)"
)
# Text just before the alias that negates it: "no PIK3CA", "without a PIK3CA", "negative for HER2".
_NEG_BEFORE = re.compile(
    r"(?i:(?<![A-Za-z])(?:no|not|without|absence\s+of|negative\s+for|non)(?:[\s-]+[A-Za-z]+)?[\s-]+)$"
)


class Status(NamedTuple):
    requirement: str
    evidence: str  # the line that decided it ("" when absent)


def kind(b: ProfileBiomarker) -> str:
    return "mutation" if "mutat" in b.alteration.lower() else "expression"


def aliases(b: ProfileBiomarker) -> list[str]:
    return [b.biomarker, b.gene, *b.aliases]


def classify(text: str, b: ProfileBiomarker) -> Status:
    """Status of biomarker `b` in `text` (see module docstring)."""
    k = kind(b)
    wants_low = "low" in b.status.lower()
    pattern = alias_pattern(aliases(b))
    positive = negated = low = None  # each holds the first (start, end) that set it
    for m in pattern.finditer(text):
        start, at = m.span()
        line_start = text.rfind("\n", 0, start) + 1
        if _NEG_BEFORE.search(text[max(line_start, start - config.NEGATION_LOOKBACK_CHARS):start]):
            negated = negated or m.span()
            continue
        if _NEG_AFTER[k].match(text, at):
            negated = negated or m.span()
            continue
        if k == "expression" and _POSITIVE_SIGN.match(text, at):
            positive = positive or m.span()
            continue
        line_end = text.find("\n", at)
        stop = min(at + config.STATUS_WINDOW_CHARS, line_end if line_end != -1 else len(text))
        if k == "expression" and (lo := _LOW.search(text, at, stop)) and not _STATUS[k].search(text, at, lo.start()):
            if wants_low:
                positive = positive or m.span()
            else:
                low = low or m.span()
            continue
        status = _STATUS[k].search(text, at, stop)
        # End the cue search at the status word's end, so "non-(?=mutat)" can see "mutated".
        cue = _CUE.search(text, at, status.end() if status else stop)
        if cue:
            if cue.group("neg") is not None:
                negated = negated or m.span()
        elif status and not _HEDGE_AFTER_STATUS.match(text, status.end()):
            positive = positive or m.span()

    if positive and not negated:
        return Status(REQUIRED, line_around(text, *positive))
    if negated or low:
        if positive:
            return Status(MENTIONED, line_around(text, *positive))
        return Status(CONFLICTS, line_around(text, *(negated or low)))
    first = pattern.search(text)
    if first:
        return Status(MENTIONED, line_around(text, *first.span()))
    return Status(ABSENT, "")
