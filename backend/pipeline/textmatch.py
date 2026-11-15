"""Whole-term text matching shared by the literature (stage 1) and trial matching (stage 4) stages.

Kept from the old scoring module because the rules are subtle and were tested there:

* A term may not touch a letter or digit on either side, so "HER2-positive",
  "(ERBB2)" and "PIK3CA-mutant" match but "ERBB2" does not match inside "ERBB20".
  Lookarounds are used instead of \\b so terms with "-" or "/" work.
* Short all-letter terms (at most 4 letters: SRC, JUN, ATM, TNF, PGR, EGFR, PTEN,
  ER, PR, HR) match exact case only, because their lowercase forms are ordinary
  words ("Jun 2025", "atm", "per"). Everything else, including any symbol with a
  digit (ERBB2 / ErbB2 / Her2, PIK3CA / pik3ca), is case-insensitive.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


def exact_case(term: str) -> bool:
    return term.isalpha() and len(term) <= 4


def term_pattern(term: str, force_exact_case: Optional[bool] = None) -> re.Pattern:
    exact = exact_case(term) if force_exact_case is None else force_exact_case
    flags = 0 if exact else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", flags)


def alias_pattern(aliases: Iterable[str]) -> re.Pattern:
    """One pattern for several spellings of the same thing, longest first, so
    "HER2/neu-negative" is read as the alias "HER2/neu" (then negated), not as
    "HER2" followed by "/neu..."."""
    alts = []
    for a in sorted({a for a in aliases if a}, key=len, reverse=True):
        alts.append(re.escape(a) if exact_case(a) else f"(?i:{re.escape(a)})")
    return re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(alts)})(?![A-Za-z0-9])")


def found(term: str, text: str) -> bool:
    return bool(term_pattern(term).search(text))


def line_around(text: str, start: int, end: int, max_chars: int = 200) -> str:
    """The line of `text` that holds [start, end), clipped to about max_chars around the match."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    if line_end - line_start > max_chars:
        half = max_chars // 2
        line_start = max(line_start, start - half)
        line_end = min(line_end, end + half)
    return text[line_start:line_end].strip(" *-\t")
