"""Stages 4 and 6: gene scores and trial rankings (AGENTS.md section 5).

  stage 4  run_gene_scores()      papers, gene_candidates, genomic_context -> gene_scores.json
  stage 6  run_trial_rankings()   gene_scores, gene_candidates, trials, drug_targets -> rankings.json

Both are pure functions of files already on disk: no network, no randomness.
Unlike the fetching stages they always recompute (refresh is accepted for the
common stage interface but changes nothing), because a cached score would only
ever be a stale score after an upstream stage changes.

Every weight is read from backend.config at call time, never written here.
All scores are clamped to [0, 1] and rounded to 4 decimals. Each derived score
is computed from the already-rounded inputs, so the numbers the dashboard shows
add up exactly (e.g. trial_score == W_DIRECT * directness + W_GENOMIC * genomic_match).
"""

from __future__ import annotations

import argparse
import re
from typing import Optional

from backend import config
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import (
    Biomarker,
    DrugTarget,
    GeneCandidate,
    GeneScore,
    GenomicContext,
    MatchedGene,
    Paper,
    Ranking,
    Trial,
)
from backend.store import read_rows, write_rows

# Directness heuristic constant lives in backend/config.py (see _biomarker_directness).
STATUS_WINDOW_CHARS = config.STATUS_WINDOW_CHARS


def _score(x: float) -> float:
    return round(min(1.0, max(0.0, x)), 4)


def _min_max(values: dict[str, float]) -> dict[str, float]:
    """Min-max normalise across the candidate set.

    Degenerate case (every value equal, including a single scored gene): all 0.0.
    That is what min-max gives when every gene is the minimum, and it is the
    conservative reading: a model output that does not vary across the set cannot
    tell genes apart, so it adds nothing to anyone's combined_score.
    """
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {g: 0.0 for g in values}
    return {g: (v - lo) / (hi - lo) for g, v in values.items()}


# ---------------------------------------------------------------- stage 4
def run_gene_scores(refresh: bool = False) -> list[GeneScore]:
    papers = {p.paper_id for p in read_rows(config.PAPERS_PATH, Paper)}
    candidates = read_rows(config.GENE_CANDIDATES_PATH, GeneCandidate)
    context = {c.gene: c for c in read_rows(config.GENOMIC_CONTEXT_PATH, GenomicContext)}

    # Only candidates count, and only those the model actually scored; the rest get 0.0 below.
    raw = {
        c.gene: context[c.gene].model_score
        for c in candidates
        if c.gene in context and context[c.gene].model_score is not None
    }
    unscored = sorted({c.gene for c in candidates} - raw.keys())
    if unscored:
        print(f"[scoring] note: no model_score for {len(unscored)} gene(s), using 0.0: {', '.join(unscored)}")
    model = _min_max(raw)

    rows = []
    for c in candidates:
        paper_ids = set(c.paper_ids)  # de-duplicated; a repeated id is still one paper
        unknown = paper_ids - papers
        if unknown:
            print(f"[scoring] warning: {c.gene} cites paper ids not in papers.json: {sorted(unknown)}")
        lit = _score(len(paper_ids) / config.LIT_SATURATION)
        mod = _score(model.get(c.gene, 0.0))
        rows.append(
            GeneScore(
                gene=c.gene,
                literature_score=lit,
                model_score=mod,
                combined_score=_score(config.W_LIT * lit + config.W_MODEL * mod),
            )
        )
    rows.sort(key=lambda r: (-r.combined_score, r.gene))
    write_rows(config.GENE_SCORES_PATH, rows)
    return rows


# ---------------------------------------------------------------- text matching
def _term_pattern(term: str, exact_case: Optional[bool] = None) -> re.Pattern:
    """Whole-term match: the term may not touch a letter or digit on either side.

    So "HER2-positive", "(ERBB2)" and "PIK3CA-mutant" match, but "ERBB2" does not
    match inside "ERBB20". Lookarounds instead of \\b so terms with "-" or "/" work.

    Case: gene symbols that are all letters and at most 4 long (SRC, JUN, ATM,
    TNF, PGR, EGFR, PTEN) must match exact case, because their lowercase forms are
    ordinary words or abbreviations ("Jun 2025", "atm"). Everything else, including
    any symbol with a digit (ERBB2 / ErbB2 / Her2), is case-insensitive.
    """
    if exact_case is None:
        exact_case = term.isalpha() and len(term) <= 4
    flags = 0 if exact_case else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", flags)


def _found(term: str, text: str) -> bool:
    return bool(_term_pattern(term).search(text))


def _alias_pattern(aliases: list[str]) -> re.Pattern:
    """One pattern for all biomarker aliases, longest first, so "HER2/neu-negative"
    is read as the alias "HER2/neu" (then negated), not as "HER2" followed by "/neu..."."""
    alts = []
    for a in sorted(set(aliases), key=len, reverse=True):
        alts.append(re.escape(a) if a.isalpha() and len(a) <= 4 else f"(?i:{re.escape(a)})")
    return re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(alts)})(?![A-Za-z0-9])")


# Words that make an alias occurrence a statement of required biomarker status:
# "HER2-positive", "HER2 overexpression", "HER2 amplified", "HER2 IHC 3+", "HER2-low".
# IHC/ISH (and FISH/CISH/SISH) are case-sensitive so "finish" or "English" never count.
_STATUS_WORDS = re.compile(
    r"(?i:positiv|over-?express|amplif|\b(?:ultra-?)?low\b)|IHC|ISH\b|\b[0-3]\+"
)
# Right after the alias: "HER2-negative", "HER2 negative", "HER2 neg", or a bare minus as in "ER+/HER2-".
_NEGATED = re.compile(r"\s*-?\s*neg(?:ative)?\b|-(?![A-Za-z0-9])", re.IGNORECASE)
# Right after the alias, the positive shorthand: "HER2+", "ER+/HER2+", "HR-/HER2+".
_POSITIVE_SIGN = re.compile(r"\+(?![0-9])")
# Between the alias and its status word (or anywhere in the window if there is none).
# A "neg" cue makes the occurrence a negation: "HER2 not overexpressed", "HER2 non-amplified",
# "HER2 status negative by IHC", "HER2 expression is negative". A hedge ("equivocal",
# "ineligible") only stops the occurrence from counting as a requirement.
_CUE = re.compile(r"(?i:(?P<neg>\bnot\b|\bnon-?(?=amplif|over|positiv)|negativ)|equivocal|ineligib)")
_EXCLUSION_HEADING = re.compile(r"exclusion criteria", re.IGNORECASE)


def _biomarker_directness(trial: Trial, aliases: list[str]) -> float:
    """1.0 if eligibility requires biomarker status, 0.5 if it is only mentioned, else 0.

    Only the inclusion part of the eligibility text counts (everything before
    "Exclusion Criteria"). Each alias occurrence there is classed as:
      negated  - "HER2-negative", "HER2-", "HER2 not overexpressed", "HER2 status negative"
      positive - "HER2+", or a status word on the same line within STATUS_WINDOW_CHARS
                 ("HER2-positive", "HER2 overexpression", "HER2 IHC 3+", "HER2-low")
    The decision is per trial, not per occurrence: one stray positive-looking line
    in a HER2-negative trial ("If HER2 overexpression is equivocal...") must not
    flip it. So it is required if some occurrence is positive and none is negated.
    A trial that requires HER2-negative disease is about HER2 only in the sense of
    excluding it, so it counts as mentioned. Exception: HER2-low / ultralow is
    required even next to "HER2-negative", because HER2-low is defined as a subset
    of HER2-negative and those trials do select on HER2 status.
    Known misses: phrasing with the status word first ("positive for HER2") falls
    back to mentioned.
    """
    pattern = _alias_pattern(aliases)
    inclusion = _EXCLUSION_HEADING.split(trial.eligibility_text, maxsplit=1)[0]
    positive = negated = low = False
    for m in pattern.finditer(inclusion):
        at = m.end()
        if _NEGATED.match(inclusion, at):
            negated = True
            continue
        if _POSITIVE_SIGN.match(inclusion, at):
            positive = True
            continue
        line_end = inclusion.find("\n", at)
        stop = min(at + STATUS_WINDOW_CHARS, line_end if line_end != -1 else len(inclusion))
        status = _STATUS_WORDS.search(inclusion, at, stop)
        # End at the status word's end, not its start, so "non-(?=amplif)" can see "amplified".
        cue = _CUE.search(inclusion, at, status.end() if status else stop)
        if cue:
            negated = negated or cue.group("neg") is not None
        elif status:
            positive = True
            low = low or "low" in status.group().lower()
    if low or (positive and not negated):
        return config.DIRECTNESS_REQUIRED

    everything = "\n".join([trial.title, *trial.conditions, *trial.interventions, trial.eligibility_text])
    if pattern.search(everything):
        return config.DIRECTNESS_MENTIONED
    return config.DIRECTNESS_ABSENT


def _matched_genes(trial: Trial, genes: list[str], bm: Biomarker, drugs: list[DrugTarget]) -> set[str]:
    """Scored genes named in the trial text, plus genes reached through a named drug."""
    everything = "\n".join([trial.title, *trial.conditions, *trial.interventions, trial.eligibility_text])
    found = {g for g in genes if _found(g, everything)}
    if _alias_pattern([bm.biomarker, bm.gene, *bm.aliases]).search(everything):
        found.add(bm.gene)  # "HER2" in the text is a mention of ERBB2

    # Drugs are looked up in title, interventions and eligibility (not conditions).
    # Drug names are long or hyphenated, so they always match case-insensitively.
    drug_text = "\n".join([trial.title, *trial.interventions, trial.eligibility_text])
    for d in drugs:
        if any(_term_pattern(name, exact_case=False).search(drug_text) for name in [d.drug, *d.aliases]):
            found.update(d.target_genes)

    # Keep only genes Way 1 actually scored (plus the biomarker gene for its chip).
    # A drug target outside the candidate set has no combined_score to contribute.
    return found & (set(genes) | {bm.gene})


# ---------------------------------------------------------------- stage 6
def run_trial_rankings(refresh: bool = False) -> list[Ranking]:
    bm = load_biomarker(config.BIOMARKER_PATH)
    scores = {s.gene: s for s in read_rows(config.GENE_SCORES_PATH, GeneScore)}
    candidates = {c.gene: c for c in read_rows(config.GENE_CANDIDATES_PATH, GeneCandidate)}
    context = {c.gene: c for c in read_rows(config.GENOMIC_CONTEXT_PATH, GenomicContext)}
    trials = read_rows(config.TRIALS_PATH, Trial)
    drugs = read_rows(config.DRUG_TARGETS_PATH, DrugTarget)
    aliases = list(dict.fromkeys([bm.biomarker, bm.gene, *bm.aliases]))

    def combined(gene: str) -> float:
        return scores[gene].combined_score if gene in scores else 0.0

    rows = []
    for t in trials:
        hits = _matched_genes(t, list(scores), bm, drugs)
        # Sorted by combined_score (ties by name). The biomarker gene stays in the
        # list for the dashboard chip, but never counts toward genomic_match:
        # every trial in the snapshot is about it, so it would flatten the ranking.
        ordered = sorted(hits, key=lambda g: (-combined(g), g))
        extras = [combined(g) for g in ordered if g != bm.gene][: config.TOP_N_MATCHED]
        genomic_match = _score(sum(extras) / len(extras)) if extras else 0.0
        directness = _score(_biomarker_directness(t, aliases))

        mock_inputs = []
        if t.is_mock:
            mock_inputs.append("trials")
        if any(g in candidates and candidates[g].is_mock for g in hits):
            mock_inputs.append("gene_candidates")
        if any(g in context and context[g].is_mock for g in hits):
            mock_inputs.append("genomic_context")

        rows.append(
            Ranking(
                rank=0,  # assigned after sorting
                nct_id=t.nct_id,
                title=t.title,
                phase=t.phase,
                status=t.status,
                url=t.url,
                trial_score=_score(config.W_DIRECT * directness + config.W_GENOMIC * genomic_match),
                biomarker_directness=directness,
                genomic_match=genomic_match,
                matched_genes=[
                    MatchedGene(
                        gene=g,
                        combined_score=combined(g),
                        paper_ids=candidates[g].paper_ids if g in candidates else [],
                    )
                    for g in ordered
                ],
                source=t.source,
                mock_inputs=mock_inputs,
            )
        )

    rows.sort(key=lambda r: (-r.trial_score, r.nct_id))
    for i, r in enumerate(rows, start=1):
        r.rank = i
    write_rows(config.RANKINGS_PATH, rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stages 4 and 6: gene scores, then trial rankings")
    ap.add_argument("--refresh", action="store_true", help="accepted for symmetry; scoring always recomputes")
    args = ap.parse_args()
    genes = run_gene_scores(refresh=args.refresh)
    print(f"[scoring] {len(genes)} gene scores -> {config.GENE_SCORES_PATH}")
    ranked = run_trial_rankings(refresh=args.refresh)
    n_mock = sum(bool(r.mock_inputs) for r in ranked)
    print(f"[scoring] {len(ranked)} ranked trials ({n_mock} with mock inputs) -> {config.RANKINGS_PATH}")
