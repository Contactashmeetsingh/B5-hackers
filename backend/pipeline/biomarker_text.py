"""Read a profile biomarker's status out of free text: trial criteria, paper titles, abstracts.

Used by stage 4 (does a trial require HER2-positive? a PIK3CA mutation?) and by stage 1
(is a search hit about HER2-negative disease?).

classify(text, biomarker, others) looks at every occurrence of the biomarker's aliases
and reads the clause around it: up to NEGATION_LOOKBACK_CHARS before and
STATUS_WINDOW_CHARS after, never past a ";", a sentence end, a line end, the next
occurrence, or a mention of another biomarker (so "HER2 status and ER positive" does not
make HER2 positive). Each occurrence is one of:

  therapy   "HER2-targeted therapy", "anti-HER2", "PIK3CA inhibitors": about a drug, not
            the tumour's status, so it only counts as a mention
  hedge     "any HER2 status", "PIK3CA status unknown", "PIK3CA mutation status",
            "PIK3CA mutation is not required", "HER2 by IHC (any score)"
  negated   "HER2-negative", "HER2-", "PIK3CA wild-type", "HER2 non-amplified",
            "PIK3CA mutation not detected", "no / without / lacking / absence of PIK3CA ...",
            "patients must not have HER2-positive disease", "HER2-positive disease is excluded"
  low       HER2-low / ultralow, IHC 0, 1+ or 2+, ISH-negative: HER2-negative categories,
            so they conflict with a "positive" profile (they match a "low" one)
  positive  "HER2+", "HER2-positive", overexpression, amplification, IHC 3+, ISH-positive;
            "PIK3CA-mutated", "mutation", "mutant", "variant", "alteration", "hotspot";
            status-first wording: "positive for HER2", "mutated PIK3CA", "mutation in PIK3CA"
  mixed     both states in one clause: "HER2-positive or -negative", "PIK3CA mutant or wild-type"

Decision for the whole text (inclusion criteria only; see exclusions below):
  required   some occurrence is positive, none negated, low or mixed
  mentioned  named, but not as a requirement, or both states (mixed cohorts)
  conflicts  negated or low, never positive
  absent     not named

Exclusion criteria (text after an "Exclusion Criteria" heading): if the profile's status is
named there as a requirement ("Exclusion: known PIK3CA mutation"), the text conflicts.

Known limits: free text is varied, so this is a heuristic. The line that decided each call
is always returned, so a person can check it.
"""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple, Optional

from backend import config
from backend.pipeline.textmatch import alias_pattern, line_around
from backend.schemas import ProfileBiomarker

REQUIRED, MENTIONED, CONFLICTS, ABSENT = "required", "mentioned", "conflicts", "absent"
_POS, _NEG, _LOW, _MIXED, _HEDGE, _THERAPY = "pos", "neg", "low", "mixed", "hedge", "therapy"

_EXCLUSION_HEADING = re.compile(r"exclusion criteria\s*:?", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[;\n]|\.(?=\s|$)")
# Other biomarkers that end a clause: hormone receptors are the usual neighbours of HER2.
_OTHER_MARKERS = re.compile(r"(?<![A-Za-z0-9])(?:ER|PR|HR|PgR)(?![A-Za-z0-9])|(?i:hormone receptor|estrogen|oestrogen|progesterone)")

# --- drug talk, not tumour status
_THERAPY_AFTER = re.compile(
    r"[\s)-]*(?i:targeted|targeting|directed|inhibitor|inhibition|therap|treatment|agent|antibod|blockade|-based|tki)")
_ANTI_BEFORE = re.compile(r"(?i:anti)[\s-]*$")

# --- hedges: the trial records the status but does not select on it
_HEDGE_BEFORE = re.compile(r"(?i:(?<![A-Za-z])(?:any|regardless\s+of|irrespective\s+of|unknown)\s+)$")
_HEDGE_AFTER = re.compile(
    r"(?i:\bunknown\b|not\s+(?:required|necessary|needed|mandatory)|\bany\s+(?:IHC\s+)?(?:score|status|level)"
    r"|regardless|irrespective)")
_TEST_WORD_AFTER = re.compile(r"[A-Za-z]*\s+(?i:status|testing|test\b|assessment|result)")  # "mutation status"

# --- negation
_NEG_IMMEDIATE = {
    "expression": re.compile(r"\s*-?\s*(?i:neg(?:ative)?)\b|-(?![A-Za-z0-9])|\[\s*-\s*\]|\(\s*-\s*\)"),
    "mutation": re.compile(r"[\s:-]*(?i:wild[\s-]?type|wt\b|non-?mutat|unmutated|neg(?:ative)?\b)"),
}
_NEG_BEFORE = re.compile(
    r"(?i:(?<![A-Za-z])(?:no(?:\s+evidence\s+of)?|not|without|lack(?:ing)?(?:\s+of)?|absence\s+of|free\s+of"
    r"|negative\s+for|non)(?:[\s-]+[A-Za-z]+){0,2}[\s-]+)$")
_NEG_AFTER = re.compile(
    r"(?i:negativ|not\s+(?:detected|present|overexpress|amplif|mutat|found|identified|positive)"
    r"|non-?(?:amplif|overexpress|mutat|positiv)|wild[\s-]?type|\bwt\b|unmutated|\babsent\b)")
_NOT_ALLOWED = re.compile(r"(?i:not\s+(?:allowed|permitted|eligible)|\b(?:is|are)\s+excluded|ineligible)")
_PRIOR = re.compile(r"(?i:\bprior\b|\bprevious|\bpreviously\b|\breceived\b)")

# --- positive
_POS_SIGN = re.compile(r"\+(?![0-9])|\[\s*\+\s*\]|\(\s*\+\s*\)")
_POS_WORDS = {
    "expression": re.compile(r"(?i:positiv|over-?express|amplif)"),
    "mutation": re.compile(r"(?i:mutat|mutant|(?<![A-Za-z])variant|alteration|altered|hotspot)"),
}
_POS_BEFORE = {
    "expression": re.compile(r"(?i:(?:positive|amplified|over-?expressed)(?:\s+for)?\s+)$"),
    "mutation": re.compile(
        r"(?i:(?:mutated|mutant|activating|harbou?ring(?:\s+an?)?(?:\s+activating)?|mutations?\s+(?:in|of|within)(?:\s+the)?)\s+)$"),
}
# HER2 IHC / ISH scoring
_SCORE_3 = re.compile(r"(?<![0-9.])3\s*\+")
_ISH_POS = re.compile(r"(?i:\b[FCS]?ISH)(?:\s*\+|[\s-]*(?i:pos|amplif))")
_SCORE_LOW = re.compile(r"(?<![0-9.])[0-2]\s*\+|(?i:\bIHC\b(?:\s+score)?(?:\s+of)?\s+0\b)|(?<![0-9.])0\s+(?i:or|and|/)\s+1\s*\+")
_ISH_NEG = re.compile(r"(?i:\b[FCS]?ISH)(?:\s*-(?![A-Za-z0-9])|[\s-]*(?i:neg|non))|(?i:(?:negative|non-?amplified)\s+[FCS]?ISH\b)")
_LOW_WORD = re.compile(r"(?i)(?<![A-Za-z])(?:ultra-?)?low\b")
_OR = re.compile(r"(?i:\bor\b|/)")


class Status(NamedTuple):
    requirement: str
    evidence: str  # the line that decided it ("" when absent)


def kind(b: ProfileBiomarker) -> str:
    return "mutation" if "mutat" in b.alteration.lower() else "expression"


def aliases(b: ProfileBiomarker) -> list[str]:
    return [b.biomarker, b.gene, *b.aliases]


def split_criteria(text: str) -> tuple[str, str]:
    """(inclusion, exclusion). Text with no "Exclusion Criteria" heading is all inclusion."""
    parts = _EXCLUSION_HEADING.split(text, maxsplit=1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    cs = 0
    for m in _CLAUSE_END.finditer(text, 0, start):
        cs = m.end()
    m = _CLAUSE_END.search(text, end)
    return cs, (m.start() if m else len(text))


def _occurrence(text: str, start: int, end: int, nxt: int, k: str, wants_low: bool,
                stop: Optional[re.Pattern]) -> Optional[str]:
    clause_start, clause_end = _clause_bounds(text, start, end)
    before = text[max(clause_start, start - config.NEGATION_LOOKBACK_CHARS):start]
    after_end = min(clause_end, nxt, end + config.STATUS_WINDOW_CHARS)
    after = text[end:after_end]
    for p in (stop, _OTHER_MARKERS):
        m = p.search(after) if p else None
        if m and m.start() > 0:
            after = after[: m.start()]

    if _THERAPY_AFTER.match(after) or _ANTI_BEFORE.search(before):
        return _THERAPY
    if _HEDGE_BEFORE.search(before):
        return _HEDGE
    if _NEG_IMMEDIATE[k].match(after) or _NEG_BEFORE.search(before):
        return _NEG
    if k == "expression" and _POS_SIGN.match(after):
        return _POS
    if _HEDGE_AFTER.search(after):
        return _HEDGE

    pos = _POS_WORDS[k].search(after)
    if pos and k == "mutation" and _TEST_WORD_AFTER.match(after, pos.end()):
        return _HEDGE  # "PIK3CA mutation status": recorded, not selected on
    if pos and k == "expression" and pos.group().lower().startswith("amplif") and _TEST_WORD_AFTER.match(after, pos.end()):
        return _HEDGE  # "HER2 amplification testing"
    is_pos = bool(pos) or bool(_POS_BEFORE[k].search(before))
    neg = _NEG_AFTER.search(after)
    low = None
    if k == "expression":
        if _SCORE_3.search(after) or _ISH_POS.search(after):
            is_pos = True
        elif _SCORE_LOW.search(after) or _ISH_NEG.search(after) or _LOW_WORD.search(after):
            low = True
    if wants_low and low:
        is_pos, low = True, None

    if neg and is_pos:
        a, b = sorted([neg.start(), pos.start() if pos else 0])
        if _OR.search(after, a, b) and not after[a:b].lower().startswith("non"):
            return _MIXED
        if _NOT_ALLOWED.search(after) and _PRIOR.search(text[clause_start:start]):
            return _THERAPY
        return _NEG
    if is_pos and _NOT_ALLOWED.search(after):
        # "Prior alpelisib for PIK3CA-mutant disease is not allowed" is about therapy;
        # "HER2-positive disease is not allowed" excludes the status.
        return _THERAPY if _PRIOR.search(text[clause_start:start]) else _NEG
    if is_pos and low:
        return _MIXED if _OR.search(after) else _LOW
    if is_pos:
        return _POS
    if neg:
        return _NEG
    if low:
        return _LOW
    return None


def _read(text: str, b: ProfileBiomarker, stop: Optional[re.Pattern]) -> dict[str, tuple[int, int]]:
    """First span per occurrence kind found in `text`."""
    k, wants_low = kind(b), "low" in b.status.lower()
    found: dict[str, tuple[int, int]] = {}
    spans = [m.span() for m in alias_pattern(aliases(b)).finditer(text)]
    for i, (s, e) in enumerate(spans):
        nxt = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        kind_ = _occurrence(text, s, e, nxt, k, wants_low, stop) or "mention"
        found.setdefault(kind_, (s, e))
    return found


def classify(text: str, b: ProfileBiomarker, others: Iterable[ProfileBiomarker] = ()) -> Status:
    """Status of biomarker `b` in `text` (see module docstring).

    `others` are the profile's other biomarkers; their names end a clause, so one
    biomarker's status word is never read as another's.
    """
    other_names = [a for o in others for a in aliases(o)]
    stop = alias_pattern(other_names) if other_names else None
    inclusion, exclusion = split_criteria(text)

    if exclusion:
        ex = _read(exclusion, b, stop)
        if _POS in ex:
            return Status(CONFLICTS, line_around(exclusion, *ex[_POS]))

    found = _read(inclusion, b, stop)
    if not found:
        if exclusion and _read(exclusion, b, stop):
            first = alias_pattern(aliases(b)).search(exclusion)
            return Status(MENTIONED, line_around(exclusion, *first.span()))
        return Status(ABSENT, "")
    if _POS in found and not ({_NEG, _LOW, _MIXED} & found.keys()):
        return Status(REQUIRED, line_around(inclusion, *found[_POS]))
    if _POS in found or _MIXED in found:
        return Status(MENTIONED, line_around(inclusion, *found.get(_MIXED, found.get(_POS))))
    if _NEG in found or _LOW in found:
        return Status(CONFLICTS, line_around(inclusion, *found.get(_NEG, found.get(_LOW))))
    return Status(MENTIONED, line_around(inclusion, *next(iter(found.values()))))
