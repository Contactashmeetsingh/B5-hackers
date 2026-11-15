"""Stage 1: research papers about the profile's biomarkers (Approach 1).

Reads:  data/input/profile.json, data/input/drug_targets.json,
        data/cache/gene_candidates.json (only as a gene vocabulary, if it exists)
Writes: data/cache/papers.json  (list[Paper])
        data/cache/keenable_queries.json  (side cache: each query and its hits, no snippets)

Cache first: a normal run loads and validates papers.json.

--refresh searches Keenable (PubMed pages only) with queries built from the profile,
then MERGES the hits into the existing papers:

* The curated papers already in the cache are kept exactly as they are and marked
  reviewed=true (they were checked by hand against PubMed; see keenable/).
* Every new hit is checked against PubMed (backend/clients/pubmed.py). Its title, year
  and publication types come from the PubMed record, not from the search page. Its
  genes_mentioned are the profile and candidate genes named in the PubMed title or
  abstract. The Keenable snippet is not used for anything: it can hold other page text.
* A new hit becomes a row with reviewed=false. Its relation is written by us and says it
  is an unreviewed search hit. Neither the snippet nor the abstract is ever stored
  (AGENTS.md: no copied abstracts).
* Hits PubMed does not know, and hits whose PubMed record names none of the profile's
  biomarkers, are dropped (logged with the reason).
* opposite_status lists profile genes the hit studies in the opposite state (e.g. ERBB2
  for a "HER2-negative" study), read with the same reader stage 4 uses on trial
  criteria: the title decides when it states a status; otherwise the abstract does.
  Stage 4 lists these papers separately.
* A PMID that is already in the cache keeps its existing row.

If Keenable or PubMed fails, the existing cache is kept untouched. A mock file is written only
when no cache exists at all, so the rest of the pipeline can still run.

    python -m backend.pipeline.literature [--refresh]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
from typing import Optional

from backend import config
from backend.clients import pubmed
from backend.clients.keenable import KeenableClient
from backend.pipeline.biomarker_text import ABSENT, CONFLICTS, MENTIONED, classify
from backend.pipeline.profile import load_profile
from backend.pipeline.textmatch import alias_pattern
from backend.schemas import MOCK, DrugTarget, GeneCandidate, Paper, Profile, ProfileBiomarker
from backend.store import read_rows, write_json, write_rows

log = logging.getLogger(__name__)

SOURCE = "keenable"
UNREVIEWED_RELATION = ("Keenable search hit, not yet reviewed by the team. "
                       "Its PubMed title or abstract names {genes}.")


# ---------------------------------------------------------------- queries
def _phrase(b: ProfileBiomarker) -> str:
    return f"{b.biomarker} {b.status}"  # "HER2 positive", "PIK3CA mutated"


def build_queries(profile: Profile, drugs: list[DrugTarget]) -> list[str]:
    """Plain-language queries (Keenable's index is semantic), all built from the profile.

    For HER2 + PIK3CA in breast cancer:
      HER2 positive and PIK3CA mutated breast cancer
      HER2 positive and PIK3CA mutated breast cancer clinical trial
      PIK3CA mutation and response to HER2-targeted therapy in breast cancer
      alpelisib in HER2 positive breast cancer       (one per drug that targets a non-primary biomarker gene)
      inavolisib in HER2 positive breast cancer
    """
    tissue = profile.tissue.lower()
    everything = " and ".join(_phrase(b) for b in profile.biomarkers)
    queries = [f"{everything} {tissue} cancer", f"{everything} {tissue} cancer clinical trial"]
    primary, others = profile.biomarkers[0], profile.biomarkers[1:]
    for b in others:
        queries.append(f"{b.gene} {b.alteration} and response to {primary.biomarker}-targeted therapy in {tissue} cancer")
        for d in drugs:
            if b.gene in d.target_genes:
                queries.append(f"{d.drug} in {_phrase(primary)} {tissue} cancer")
    return list(dict.fromkeys(queries))


# ---------------------------------------------------------------- gene spotting
def gene_vocabulary(profile: Profile, candidates: list[GeneCandidate]) -> dict[str, list[str]]:
    """gene -> spellings to look for. Profile genes use their aliases; candidate genes
    use their symbol (and current HGNC symbol when it differs)."""
    vocab: dict[str, list[str]] = {b.gene: [b.gene, b.biomarker, *b.aliases] for b in profile.biomarkers}
    for c in candidates:
        names = [c.gene] + ([c.approved_symbol] if getattr(c, "approved_symbol", None) else [])
        vocab.setdefault(c.gene, []).extend(names)
    return vocab


def genes_in(text: str, vocab: dict[str, list[str]]) -> list[str]:
    return [g for g, names in vocab.items() if alias_pattern(names).search(text)]


# ---------------------------------------------------------------- live search + merge
def opposite_status(title: str, abstract: str, profile: Profile) -> list[str]:
    """Profile genes the paper studies in the opposite state. The title decides when it
    states a status; a title that is silent or only names the gene defers to the abstract."""
    out = []
    for b in profile.biomarkers:
        others = [o for o in profile.biomarkers if o is not b]
        in_title = classify(title, b, others).requirement
        if in_title == CONFLICTS or (in_title in (ABSENT, MENTIONED) and abstract
                                     and classify(abstract, b, others).requirement == CONFLICTS):
            out.append(b.gene)
    return out


def _new_rows(profile: Profile, drugs: list[DrugTarget], vocab: dict[str, list[str]],
              known: set[str], client: KeenableClient, today: str,
              fetch_records=pubmed.fetch_records) -> tuple[list[Paper], dict]:
    profile_genes = {b.gene for b in profile.biomarkers}
    searched = [(q, client.search_pubmed(q, max_results=config.KEENABLE_MAX_RESULTS))
                for q in build_queries(profile, drugs)]
    unseen = [h["paper_id"] for _, hits in searched for h in hits if h["paper_id"] not in known]
    records = fetch_records(unseen) if unseen else {}

    new: dict[str, Paper] = {}
    query_log = []
    for q, hits in searched:
        entries = []
        for h in hits:
            pid, rec, genes = h["paper_id"], records.get(h["paper_id"]), []
            if pid in known:
                outcome = "already in papers.json"
            elif rec is None:
                outcome = "dropped: not found on PubMed"
            else:
                genes = genes_in(f"{rec['title']}\n{rec['abstract']}", vocab)
                if not profile_genes & set(genes):
                    outcome = "dropped: PubMed record names no profile biomarker"
                elif pid in new:
                    outcome = "merged (also found by another query)"
                    if q not in new[pid].found_by:
                        new[pid].found_by.append(q)
                else:
                    outcome = "merged"
                    new[pid] = Paper(
                        paper_id=pid, title=rec["title"], year=rec["year"], url=h["url"],
                        genes_mentioned=genes, relation=UNREVIEWED_RELATION.format(genes=", ".join(genes)),
                        source=SOURCE, reviewed=False, found_by=[q], retrieved=today,
                        opposite_status=opposite_status(rec["title"], rec["abstract"], profile),
                        publication_types=rec["publication_types"],
                    )
            # Provenance without page or abstract text.
            entries.append({"paper_id": pid, "search_title": h["title"], "url": h["url"],
                            "genes_in_pubmed_record": genes, "outcome": outcome})
        query_log.append({"query": q, "hits": len(hits), "results": entries})
    log_doc = {
        "retrieved": today,
        "endpoint": "/v1/search" if client.has_key else "/v1/search/public (keyless)",
        "site": config.KEENABLE_PUBMED_SITE,
        "max_results": config.KEENABLE_MAX_RESULTS,
        "checked_against": "PubMed efetch (title, year, publication types; abstract read for genes and status, not stored)",
        "queries": query_log,
    }
    return list(new.values()), log_doc


def merge(existing: list[Paper], new: list[Paper]) -> list[Paper]:
    """Curated rows first, untouched except that reviewed=None becomes True; then new hits."""
    out = []
    for p in existing:
        if p.reviewed is None and not p.is_mock:
            p = p.model_copy(update={"reviewed": True})
        out.append(p)
    seen = {p.paper_id for p in out}
    out += [p for p in new if p.paper_id not in seen]
    return out


def _mock_papers(profile: Profile) -> list[Paper]:
    """Obviously fake placeholder rows, one per profile biomarker gene."""
    first = profile.biomarkers[0].gene
    return [
        Paper(
            paper_id=f"MOCK-PAPER-{i:03d}",
            title=f"MOCK placeholder, not a real paper ({first} / {b.gene})",
            genes_mentioned=sorted({first, b.gene}),
            relation="MOCK: placeholder row. Run stage 1 with --refresh to fetch real Keenable results.",
            source=MOCK,
        )
        for i, b in enumerate(profile.biomarkers, start=1)
    ]


def run(refresh: bool = False, client: Optional[KeenableClient] = None, fetch_records=None) -> list[Paper]:
    path = config.PAPERS_PATH
    if path.exists() and not refresh:
        papers = read_rows(path, Paper)
        log.info("stage 1: loaded %d papers from cache %s", len(papers), path)
        return papers

    profile = load_profile()
    existing = read_rows(path, Paper) if path.exists() else []
    existing = [p for p in existing if not p.is_mock]  # real results replace a mock file

    if refresh:
        try:
            drugs = read_rows(config.DRUG_TARGETS_PATH, DrugTarget) if config.DRUG_TARGETS_PATH.exists() else []
            candidates = (read_rows(config.GENE_CANDIDATES_PATH, GeneCandidate)
                          if config.GENE_CANDIDATES_PATH.exists() else [])
            vocab = gene_vocabulary(profile, candidates)
            today = _dt.date.today().isoformat()
            new, query_log = _new_rows(profile, drugs, vocab, {p.paper_id for p in existing},
                                       client or KeenableClient(), today,
                                       fetch_records or pubmed.fetch_records)
            papers = merge(existing, new)
            if not papers:
                raise RuntimeError("Keenable returned no on-topic papers")
            write_rows(path, papers)
            write_json(config.KEENABLE_QUERY_LOG_PATH, query_log)
            log.info("stage 1: %d papers (%d curated kept, %d new Keenable hits merged) -> %s",
                     len(papers), len(existing), len(papers) - len(existing), path)
            return papers
        except Exception as exc:  # any live failure falls back; the demo must keep running
            log.warning("stage 1: Keenable refresh failed (%s: %s)", type(exc).__name__, exc)
            if path.exists():
                papers = read_rows(path, Paper)
                log.warning("stage 1: keeping the existing cache (%d papers), not overwriting it", len(papers))
                return papers

    papers = _mock_papers(profile)
    write_rows(path, papers)
    log.warning("stage 1: no cache found; wrote %d MOCK papers to %s", len(papers), path)
    return papers


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true", help="search Keenable and merge new hits into the cache")
    args = ap.parse_args()
    rows = run(refresh=args.refresh)
    print(f"{len(rows)} papers ({sum(r.is_mock for r in rows)} mock, "
          f"{sum(r.reviewed is True for r in rows)} reviewed, {sum(r.reviewed is False for r in rows)} unreviewed hits)")
