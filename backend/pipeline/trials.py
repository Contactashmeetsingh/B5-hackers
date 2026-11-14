"""Stage 5: the clinical trial snapshot (data/cache/trials.json).

Cache first. The demo reads the committed snapshot and never calls the network.
  python -m backend.pipeline.trials             # use cache; write a MOCK snapshot if none exists
  python -m backend.pipeline.trials --refresh   # take a real ClinicalTrials.gov snapshot

The search query is built from the biomarker record (tissue, biomarker, gene,
aliases), so a new biomarker row needs no code change here.
"""

from __future__ import annotations

import argparse

import httpx

from backend import config
from backend.clients import clinicaltrials
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import MOCK, Biomarker, Trial
from backend.store import read_rows, write_rows

# Snapshot settings live in backend/config.py (team decision; see lanes/C-trials-scoring/README.md).
CONDITION_TEMPLATE = config.TRIALS_CONDITION_TEMPLATE
SNAPSHOT_PAGE_SIZE = config.TRIALS_PAGE_SIZE
SNAPSHOT_MAX_STUDIES = config.TRIALS_MAX_STUDIES
SNAPSHOT_STATUSES = config.TRIALS_STATUSES


def build_query(bm: Biomarker) -> tuple[str, str]:
    """(query.cond, query.term) for the biomarker, e.g. ("Breast Cancer", '"HER2" OR "ERBB2" OR ...')."""
    terms: list[str] = []
    for t in [bm.biomarker, bm.gene, *bm.aliases]:
        if t.lower() not in {x.lower() for x in terms}:  # the API search is case-insensitive
            terms.append(t)
    return CONDITION_TEMPLATE.format(tissue=bm.tissue), " OR ".join(f'"{t}"' for t in terms)


def mock_trials(bm: Biomarker) -> list[Trial]:
    """A small, obviously fake snapshot shaped to exercise every branch of stage 6 scoring.

    IDs are "MOCK-NCT-000n" so they can never be mistaken for real NCT numbers, and
    no URL is given so the dashboard cannot link to a real study by accident.
    """
    b, cond = bm.biomarker, CONDITION_TEMPLATE.format(tissue=bm.tissue)
    tissue = bm.tissue.lower()
    excl = "Exclusion Criteria:\n* Illustrative mock exclusion criterion."

    def row(n: int, title: str, phase: str, interventions: list[str], inclusion: list[str]) -> Trial:
        incl = "\n".join(f"* {line}" for line in inclusion)
        return Trial(
            nct_id=f"MOCK-NCT-{n:04d}",
            title=f"[MOCK] {title}",
            phase=phase,
            status="RECRUITING",
            url="",
            conditions=[cond],
            interventions=interventions,
            eligibility_text=f"Illustrative mock criteria only.\nInclusion Criteria:\n{incl}\n{excl}",
            source=MOCK,
        )

    return [
        # biomarker required + a second targeted drug (alpelisib -> PIK3CA via drug_targets.json)
        row(1, f"Trastuzumab plus alpelisib in {b}-positive, PIK3CA-mutant {tissue} cancer", "Phase 2",
            ["trastuzumab", "alpelisib"],
            [f"{b}-positive disease (IHC 3+ or ISH amplified)", "PIK3CA mutation on tumour testing"]),
        # biomarker-low requirement, no extra genes
        row(2, f"Trastuzumab deruxtecan in {b}-low {tissue} cancer", "Phase 3",
            ["trastuzumab deruxtecan"],
            [f"{b}-low disease (IHC 1+, or IHC 2+ with negative ISH)"]),
        # endocrine therapy arm; ESR1 named in eligibility
        row(3, f"Endocrine therapy plus {b}-targeted antibody in ER-positive, {b}-positive {tissue} cancer",
            "Phase 2", ["fulvestrant", "trastuzumab"],
            [f"Estrogen receptor positive and {b}-positive disease", "ESR1 mutation status known"]),
        # extra genes named only in eligibility
        row(4, f"Dual antibody blockade with a tissue biomarker sub-study in {b}-amplified {tissue} cancer",
            "Phase 2", ["pertuzumab", "trastuzumab"],
            [f"{b} gene amplification by ISH", "Tumour tissue available for ERBB3 and GRB7 testing"]),
        # biomarker required, nothing else
        row(5, f"Tucatinib in previously treated {b}-positive metastatic {tissue} cancer", "Phase 2",
            ["tucatinib"],
            [f"{b}-positive disease by local testing"]),
        # biomarker only mentioned, not required; one extra gene
        row(6, f"Supervised exercise programme for people with {tissue} cancer", "N/A",
            ["Supervised exercise programme"],
            [f"Any hormone receptor or {b} status", "Optional archival tissue for PTEN testing"]),
    ]


def run(refresh: bool = False) -> list[Trial]:
    path = config.TRIALS_PATH
    if path.exists() and not refresh:
        return read_rows(path, Trial)

    bm = load_biomarker(config.BIOMARKER_PATH)
    if refresh:
        cond, term = build_query(bm)
        try:
            trials = clinicaltrials.fetch_studies(
                cond, term, SNAPSHOT_PAGE_SIZE, SNAPSHOT_MAX_STUDIES, SNAPSHOT_STATUSES
            )
            if not trials:
                raise clinicaltrials.ClinicalTrialsError(f"no studies for cond={cond!r} term={term!r}")
        except (httpx.HTTPError, clinicaltrials.ClinicalTrialsError) as exc:
            # Never replace a snapshot we already have with a mock (AGENTS.md section 6: keep going).
            print(f"[trials] snapshot failed ({exc}); keeping the existing cache or falling back to mock")
            if path.exists():
                return read_rows(path, Trial)
            trials = mock_trials(bm)
    else:
        trials = mock_trials(bm)

    write_rows(path, trials)
    return trials


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 5: clinical trial snapshot")
    ap.add_argument("--refresh", action="store_true", help="take a new ClinicalTrials.gov snapshot")
    args = ap.parse_args()
    rows = run(refresh=args.refresh)
    print(f"[trials] {len(rows)} trials ({sum(t.is_mock for t in rows)} mock) -> {config.TRIALS_PATH}")
