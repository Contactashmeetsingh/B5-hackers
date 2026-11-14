"""Stage 2: candidate genes, built from the papers and confirmed against a targets dataset.

Reads:  the biomarker (stage 0), data/cache/papers.json, data/input/drug_targets.json
Writes: data/cache/gene_candidates.json  (list[GeneCandidate])

One row per gene mentioned in any paper, including the biomarker gene itself so
downstream stages can see it (stage 6 drops it from genomic_match). Genes that
appear only as a drug target are added too, with no papers.

The real Keenable gene targets dataset is not available yet (AGENTS.md open
question). Until it is, drug_targets.json stands in for it: in_targets_dataset
means "is a target gene of a drug in drug_targets.json", and every row carries
source="mock" plus a "targets_dataset" note so nobody mistakes it for the real thing.
The paper evidence on each row (paper_ids) is real; papers.json has its own source.

Cache first: an existing gene_candidates.json is returned as is. Use --refresh to
rebuild it after papers.json changes (and to try the Keenable dataset).

    python -m backend.pipeline.targets [--refresh]
"""

from __future__ import annotations

import argparse
import logging

from backend import config
from backend.clients.ensembl import lookup_genes
from backend.clients.keenable import KeenableClient
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import MOCK, Biomarker, DrugTarget, GeneCandidate, Paper
from backend.store import read_rows, write_rows

log = logging.getLogger(__name__)

STAND_IN_LABEL = "pending (drug_targets.json seed used as stand-in)"



def _targets_dataset(bm: Biomarker, drugs: list[DrugTarget], refresh: bool) -> tuple[set[str], str, str]:
    """Return (dataset genes, label for the targets_dataset field, row source)."""
    if refresh:
        try:
            genes = set(KeenableClient().fetch_gene_targets(bm.gene))
            return genes, "keenable", "keenable"
        except Exception as exc:  # undocumented today; fall back to the stand-in
            log.warning("stage 2: Keenable targets dataset unavailable (%s: %s); using stand-in",
                        type(exc).__name__, exc)
    return {g for d in drugs for g in d.target_genes}, STAND_IN_LABEL, MOCK


def _sanity_check(bm: Biomarker, genes: set[str]) -> None:
    # AGENTS.md section 9 sanity list, carried on the biomarker record (biomarker.json
    # "sanity_genes"). Only logged, never used to add or score genes.
    expected = bm.sanity_genes
    if not expected:
        return
    present = [g for g in expected if g in genes]
    missing = [g for g in expected if g not in genes]
    log.info("stage 2 sanity check: present %s; missing %s", present, missing)
    if not present:
        log.warning("stage 2 sanity check: none of the expected genes found; retrieval is probably broken")


def build(bm: Biomarker, papers: list[Paper], drugs: list[DrugTarget], refresh: bool = False) -> list[GeneCandidate]:
    dataset, label, source = _targets_dataset(bm, drugs, refresh)

    # gene -> paper_ids, in papers.json order. Symbols are kept as the papers spell them.
    paper_ids: dict[str, list[str]] = {bm.gene: []}
    # Papers may name the biomarker by an alias (HER2, ErbB2): fold those into bm.gene so
    # the biomarker never shows up as a second "extra" gene that every trial matches.
    aliases = {a.upper() for a in bm.aliases} | {bm.gene.upper(), bm.biomarker.upper()}
    for p in papers:
        symbols = (bm.gene if s.strip().upper() in aliases else s.strip() for s in p.genes_mentioned if s.strip())
        for g in dict.fromkeys(symbols):
            paper_ids.setdefault(g, []).append(p.paper_id)
    for g in sorted(dataset):  # genes reached only via the targets dataset get no papers
        paper_ids.setdefault(g, [])

    ensembl = lookup_genes(list(paper_ids))  # served from data/cache/ensembl_genes.json
    rows = []
    for g, ids in paper_ids.items():
        e = ensembl.get(g)
        extra = {"targets_dataset": label}
        if e is not None and e.approved_symbol and e.approved_symbol != g:
            extra["approved_symbol"] = e.approved_symbol  # e.g. SLC9A3R1 -> NHERF1
        if e is None:
            log.warning("stage 2: no Ensembl gene for %r; ensembl_id left empty", g)
        rows.append(GeneCandidate(
            gene=g,
            ensembl_id=e.ensembl_id if e else None,
            in_targets_dataset=g in dataset,
            paper_ids=ids,
            source=source,
            **extra,
        ))

    rows.sort(key=lambda r: (-len(r.paper_ids), r.gene))
    _sanity_check(bm, set(paper_ids))
    return rows


def run(refresh: bool = False) -> list[GeneCandidate]:
    path = config.GENE_CANDIDATES_PATH
    if path.exists() and not refresh:
        rows = read_rows(path, GeneCandidate)
        log.info("stage 2: loaded %d gene candidates from cache %s", len(rows), path)
        return rows

    bm = load_biomarker(config.BIOMARKER_PATH)
    papers = read_rows(config.PAPERS_PATH, Paper)
    drugs = read_rows(config.DRUG_TARGETS_PATH, DrugTarget)
    rows = build(bm, papers, drugs, refresh=refresh)
    write_rows(path, rows)
    log.info("stage 2: wrote %d gene candidates to %s", len(rows), path)
    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="rebuild from papers.json and try the Keenable dataset")
    args = ap.parse_args()
    out = run(refresh=args.refresh)
    print(f"{len(out)} gene candidates ({sum(r.is_mock for r in out)} mock)")
