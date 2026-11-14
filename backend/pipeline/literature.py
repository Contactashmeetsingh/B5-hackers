"""Stage 1: papers linking the biomarker gene to other genes.

Reads:  the biomarker (stage 0)
Writes: data/cache/papers.json  (list[Paper])

Cache first. data/cache/papers.json holds real, PubMed-verified results (see
keenable/her2_interactors_literature.md), so a normal run just loads and validates it.

--refresh asks Keenable for fresh results. If that fails (today it always does:
the API is not documented yet), the existing cache is kept untouched. Real data
is never overwritten by mock data. A mock file is written only when no cache
exists at all, so the rest of the pipeline can still run.

    python -m backend.pipeline.literature [--refresh]
"""

from __future__ import annotations

import argparse
import logging

from backend import config
from backend.clients.keenable import KeenableClient
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import MOCK, Biomarker, DrugTarget, Paper
from backend.store import read_rows, write_rows

log = logging.getLogger(__name__)

# Search phrasings, filled from the biomarker record (never a literal gene name).
QUERY_TEMPLATES = [
    "{gene} {biomarker} {tissue} cancer interacting genes",
    "{biomarker} heterodimer signaling partners {tissue} cancer",
    "{gene} co-amplified genes {tissue} cancer",
]


def _queries(bm: Biomarker) -> list[str]:
    return [t.format(gene=bm.gene, biomarker=bm.biomarker, tissue=bm.tissue.lower())
            for t in QUERY_TEMPLATES]


def _fetch_live(bm: Biomarker) -> list[Paper]:
    """Ask Keenable; dedupe by paper_id across queries."""
    client = KeenableClient()
    papers: dict[str, Paper] = {}
    for q in _queries(bm):
        for hit in client.search_papers(q):
            p = Paper.model_validate(hit)
            papers.setdefault(p.paper_id, p)
    return list(papers.values())


def _mock_papers(bm: Biomarker) -> list[Paper]:
    """Obviously fake placeholder rows: one per known drug-target gene.

    Genes come from data/input/drug_targets.json plus the biomarker gene, so the
    mock does not invent any gene relationships beyond what the seed file states.
    """
    genes = [bm.gene]
    if config.DRUG_TARGETS_PATH.exists():
        for d in read_rows(config.DRUG_TARGETS_PATH, DrugTarget):
            genes += [g for g in d.target_genes if g not in genes]
    return [
        Paper(
            paper_id=f"MOCK-PAPER-{i:03d}",
            title=f"MOCK placeholder, not a real paper ({bm.gene} / {g})",
            year=None,
            url="",
            genes_mentioned=sorted({bm.gene, g}),
            relation="MOCK: placeholder row. Run stage 1 with real Keenable results to replace it.",
            source=MOCK,
        )
        for i, g in enumerate(genes, start=1)
    ]


def run(refresh: bool = False) -> list[Paper]:
    path = config.PAPERS_PATH
    if path.exists() and not refresh:
        papers = read_rows(path, Paper)
        log.info("stage 1: loaded %d papers from cache %s", len(papers), path)
        return papers

    bm = load_biomarker(config.BIOMARKER_PATH)

    if refresh:
        try:
            papers = _fetch_live(bm)
            if not papers:
                raise RuntimeError("Keenable returned no papers")
            write_rows(path, papers)
            log.info("stage 1: wrote %d live papers to %s", len(papers), path)
            return papers
        except Exception as exc:  # any live failure falls back; the demo must keep running
            log.warning("stage 1: Keenable refresh failed (%s: %s)", type(exc).__name__, exc)
            if path.exists():
                papers = read_rows(path, Paper)
                log.warning("stage 1: keeping the existing cache (%d papers), not overwriting it", len(papers))
                return papers

    papers = _mock_papers(bm)
    write_rows(path, papers)
    log.warning("stage 1: no cache found; wrote %d MOCK papers to %s", len(papers), path)
    return papers


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="ask Keenable instead of using the cache")
    args = ap.parse_args()
    rows = run(refresh=args.refresh)
    print(f"{len(rows)} papers ({sum(r.is_mock for r in rows)} mock)")
