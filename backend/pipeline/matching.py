"""Stage 4: match the profile to the hard-coded clinical trials and say why (Approach 1).

Reads  data/input/profile.json, data/input/drug_targets.json, data/input/gene_terms.json,
       data/cache/papers.json, data/cache/gene_candidates.json, data/cache/trials.json
Writes data/output/trial_matches.json  (list[TrialMatch])

There is NO score. Each trial gets:

1. biomarker_matches: for every profile biomarker, is it required, mentioned,
   conflicting or absent (backend/pipeline/biomarker_text.py reads the criteria, including
   any exclusion section; a conflict stated only in the title counts too), plus which of
   the trial's drugs target it (data/input/drug_targets.json).
2. drugs: drugs named in the title, interventions or inclusion criteria, with their targets
   (a drug named only under exclusions, e.g. "prior alpelisib", is not one the trial uses).
3. related_genes: genes our papers name alongside the biomarker (gene_candidates.json)
   that the trial involves: named by symbol, by a clinical word (data/input/gene_terms.json:
   "ER" -> ESR1, "HR" -> ESR1 + PGR), or as a target of one of its drugs.
4. a tier (TIERS below; the rank orders tiers, it is not a score). Inside a tier the
   dataset's own order is kept.
5. supporting_papers: papers that name one of the trial's drugs aimed at a non-primary gene,
   or a gene the trial involves other than the primary biomarker gene (almost every paper
   names HER2, so HER2 alone supports nothing in particular). Most specific first, then
   hand-reviewed, then newest. Papers that study the opposite status (e.g. HER2-negative
   disease) are context, not support: they go to opposite_status_papers.
6. a plain-language explanation built only from the facts above.

The gene_candidates rows are tagged mock because their in_targets_dataset field is a
stand-in. This stage reads only their gene and paper_ids (both real), so that file is
not listed in mock_inputs.

    python -m backend.pipeline.matching
"""

from __future__ import annotations

import argparse
from typing import Iterable

from backend import config
from backend.pipeline.biomarker_text import ABSENT, CONFLICTS, MENTIONED, REQUIRED, classify, kind, split_criteria
from backend.pipeline.profile import load_profile
from backend.pipeline.textmatch import alias_pattern, term_pattern
from backend.schemas import (
    MOCK,
    BiomarkerMatch,
    DrugHit,
    DrugTarget,
    GeneCandidate,
    GeneTerm,
    Paper,
    Profile,
    ProfileBiomarker,
    RelatedGene,
    SupportingPaper,
    Trial,
    TrialMatch,
)
from backend.store import read_rows, write_rows

TIERS = {
    "requires_all_biomarkers": 1,   # criteria require every profile biomarker
    "partial_plus_related": 2,      # requires some, and involves other profile or related genes
    "partial_only": 3,              # requires some, nothing else from our gene lists
    "mentions_only": 4,             # names profile biomarkers (or targets them) but requires none
    "conflicts": 5,                 # criteria (or title) ask for the opposite of the profile
    "not_matched": 6,               # no profile biomarker anywhere
}
DISCLAIMER = ("Research-paper evidence and the trial's stated criteria only, not a recommendation. "
              "Confirm eligibility and recruiting status on ClinicalTrials.gov.")


def _phrase(b: ProfileBiomarker) -> str:
    return f"{b.biomarker} {b.status}"


def _opposite_phrase(b: ProfileBiomarker) -> str:
    return f"{b.biomarker}-{'wild-type' if kind(b) == 'mutation' else 'negative'}"


def _join(items: Iterable[str], word: str = "and") -> str:
    items = list(dict.fromkeys(items))
    if len(items) <= 2:
        return f" {word} ".join(items)
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def _sentence(s: str) -> str:
    s = s.strip()
    return s if s.endswith((".", "!", "?")) else s + "."


def _others(profile: Profile, b: ProfileBiomarker) -> list[ProfileBiomarker]:
    return [o for o in profile.biomarkers if o is not b]


def _uses_text(trial: Trial) -> str:
    """What the trial uses and who it enrols: title, conditions, interventions, inclusion criteria."""
    inclusion, _ = split_criteria(trial.eligibility_text)
    return "\n".join([trial.title, *trial.conditions, *trial.interventions, inclusion])


# ---------------------------------------------------------------- facts per trial
def _drug_hits(trial: Trial, drugs: list[DrugTarget]) -> list[DrugHit]:
    """Drugs the trial uses. A name found only inside a longer drug name ("trastuzumab"
    inside "trastuzumab deruxtecan") is dropped."""
    inclusion, _ = split_criteria(trial.eligibility_text)
    text = "\n".join([trial.title, *trial.interventions, inclusion])
    found = []  # (span, drug, name)
    for d in drugs:
        for name in [d.drug, *d.aliases]:
            for m in term_pattern(name, force_exact_case=False).finditer(text):
                found.append((m.span(), d, name))
    keep: dict[str, DrugHit] = {}
    for (s, e), d, name in found:
        if any(s2 <= s and e <= e2 and (e2 - s2) > (e - s) for (s2, e2), _, _ in found):
            continue
        keep.setdefault(d.drug, DrugHit(drug=d.drug, matched_name=name, target_genes=d.target_genes, source=d.source))
    return list(keep.values())


def _related_genes(trial: Trial, profile: Profile, candidates: list[GeneCandidate],
                   terms: list[GeneTerm], drug_hits: list[DrugHit]) -> list[RelatedGene]:
    profile_genes = {b.gene for b in profile.biomarkers}
    text = _uses_text(trial)
    by_gene = {c.gene: c for c in candidates if c.gene not in profile_genes}
    how: dict[str, list[str]] = {}
    for g, c in by_gene.items():
        if alias_pattern([g] + ([c.approved_symbol] if c.approved_symbol else [])).search(text):
            how.setdefault(g, []).append(f"{g} named in the trial text")
    seen_notes: set[tuple[str, str]] = set()  # "HR" and "hormone receptor" say the same thing: keep one
    for t in terms:
        if term_pattern(t.term).search(text):
            for g in t.genes:
                if g in by_gene and (g, t.note) not in seen_notes:
                    seen_notes.add((g, t.note))
                    how.setdefault(g, []).append(f'"{t.term}" ({t.note}) named in the trial text')
    for d in drug_hits:
        for g in d.target_genes:
            if g in by_gene:
                how.setdefault(g, []).append(f"target of {d.matched_name}")
    return [RelatedGene(gene=g, how=list(dict.fromkeys(h)), paper_ids=by_gene[g].paper_ids) for g, h in how.items()]


def _biomarker_matches(trial: Trial, profile: Profile, drug_hits: list[DrugHit]) -> list[BiomarkerMatch]:
    title_etc = "\n".join([trial.title, *trial.conditions, *trial.interventions])
    out = []
    for b in profile.biomarkers:
        status = classify(trial.eligibility_text, b, _others(profile, b))
        if status.requirement == ABSENT:  # not in the criteria: the title may still name it
            in_title = classify(title_etc, b, _others(profile, b))
            if in_title.requirement == CONFLICTS:
                status = in_title          # "HER2-low" in the title is a conflict, not a mention
            elif in_title.requirement != ABSENT:
                status = in_title._replace(requirement=MENTIONED)
        out.append(BiomarkerMatch(
            biomarker=b.biomarker, gene=b.gene, status=b.status,
            requirement=status.requirement, evidence_text=status.evidence,
            via_drugs=[d.matched_name for d in drug_hits if b.gene in d.target_genes],
        ))
    return out


def _tier(matches: list[BiomarkerMatch], related: list[RelatedGene], profile: Profile) -> tuple[str, str]:
    names = {b.gene: _phrase(b) for b in profile.biomarkers}
    required = [m.gene for m in matches if m.requirement == REQUIRED]
    involved_other = [m.gene for m in matches if m.requirement != REQUIRED
                      and (m.requirement == MENTIONED or m.via_drugs)]
    if any(m.requirement == CONFLICTS for m in matches):
        bad = [names[m.gene] for m in matches if m.requirement == CONFLICTS]
        return "conflicts", f"Criteria conflict with {_join(bad)}"
    if required and len(required) == len(matches):
        return "requires_all_biomarkers", f"Requires {_join(names[g] for g in required)}"
    if required and (involved_other or related):
        return "partial_plus_related", f"Requires {_join(names[g] for g in required)}, plus related genes"
    if required:
        return "partial_only", f"Requires {_join(names[g] for g in required)} only"
    if any(m.requirement == MENTIONED or m.via_drugs for m in matches):
        return "mentions_only", "Mentions the profile's biomarkers but does not require them"
    return "not_matched", "No profile biomarker found"


# ---------------------------------------------------------------- papers
def _paper_genes(p: Paper, profile: Profile) -> set[str]:
    """genes_mentioned with profile aliases folded in (HER2 -> ERBB2)."""
    alias_to_gene = {a.upper(): b.gene for b in profile.biomarkers for a in [b.gene, b.biomarker, *b.aliases]}
    return {alias_to_gene.get(g.strip().upper(), g.strip()) for g in p.genes_mentioned if g.strip()}


def _opposite_status(p: Paper, profile: Profile) -> list[str]:
    """Profile genes the paper studies in the opposite state: stage 1's flag (PubMed title +
    abstract) or, for papers without it, the title read the same way."""
    flagged = set(p.opposite_status)
    flagged |= {b.gene for b in profile.biomarkers
                if classify(p.title, b, _others(profile, b)).requirement == CONFLICTS}
    return [b.gene for b in profile.biomarkers if b.gene in flagged]


def _paper_lists(papers: list[Paper], profile: Profile, matches: list[BiomarkerMatch],
                 related: list[RelatedGene], drug_hits: list[DrugHit],
                 terms: list[GeneTerm]) -> tuple[list[SupportingPaper], list[SupportingPaper]]:
    """(supporting, opposite_status) papers for one trial, each most specific first:
    title names a trial drug, title names an involved gene, hand-reviewed, newest."""
    primary = profile.biomarkers[0]
    names = {b.gene: b.biomarker for b in profile.biomarkers}
    by_gene = {b.gene: b for b in profile.biomarkers}
    involved = [m.gene for m in matches if m.gene != primary.gene
                and (m.requirement in (REQUIRED, MENTIONED) or m.via_drugs)]
    involved += [r.gene for r in related]
    # Only drugs aimed at a gene other than the primary biomarker add specific evidence:
    # nearly every HER2 paper names trastuzumab, but a paper naming alpelisib is about PIK3CA.
    drug_names = {d.drug: [d.drug, d.matched_name] for d in drug_hits if set(d.target_genes) - {primary.gene}}
    # How each involved gene can be spelled in a title: profile aliases, symbol, long clinical terms
    # ("estrogen receptor"; short ones like "ER" are too ambiguous in paper titles).
    spellings = {b.gene: [b.gene, b.biomarker, *b.aliases] for b in profile.biomarkers}
    for g in involved:
        spellings.setdefault(g, [g]).extend(t.term for t in terms if g in t.genes and len(t.term) > 4)

    support, opposite_list = [], []
    for i, p in enumerate(papers):
        genes = _paper_genes(p, profile)
        opposite = _opposite_status(p, profile)
        why = [f"title names {drug}" for drug, n in drug_names.items() if alias_pattern(n).search(p.title)]
        for g in involved:
            if g not in genes:
                continue
            label = names.get(g, g)
            with_primary = primary.gene in genes and primary.gene not in opposite
            if p.reviewed:
                why.append(f"links {label} to {primary.biomarker}" if with_primary else f"mentions {label}")
            else:
                why.append(f"PubMed record names {label}" + (f" and {primary.biomarker}" if with_primary else ""))
        if not why:
            continue
        why += [f"studies {_opposite_phrase(by_gene[g])} disease, not the profile's status" for g in opposite]
        title_focus = any(alias_pattern(spellings[g]).search(p.title) for g in involved if g in genes)
        rank = (not any(w.startswith("title names") for w in why), not title_focus, p.reviewed is not True,
                -(p.year or 0), i)
        sp = SupportingPaper(paper_id=p.paper_id, title=p.title, year=p.year, url=p.url, relation=p.relation,
                             source=p.source, reviewed=p.reviewed, why=list(dict.fromkeys(why)),
                             publication_types=p.publication_types)
        (opposite_list if opposite else support).append((rank, sp))
    support.sort(key=lambda x: x[0])
    opposite_list.sort(key=lambda x: x[0])
    return [sp for _, sp in support], [sp for _, sp in opposite_list]


# ---------------------------------------------------------------- explanation
def _explain(tier: str, matches: list[BiomarkerMatch], drug_hits: list[DrugHit], related: list[RelatedGene],
             unchecked: list[str], support: list[SupportingPaper], opposite: list[SupportingPaper],
             profile: Profile) -> str:
    names = {b.gene: _phrase(b) for b in profile.biomarkers}
    by_gene = {b.gene: b for b in profile.biomarkers}
    by_req: dict[str, list[BiomarkerMatch]] = {}
    for m in matches:
        by_req.setdefault(m.requirement, []).append(m)
    s = []
    if CONFLICTS in by_req:
        c = by_req[CONFLICTS]
        quotes = "; ".join(f'"{e}"' for e in dict.fromkeys(m.evidence_text for m in c))
        s.append(f"Its text conflicts with the profile ({_join(names[m.gene] for m in c)}): {quotes}. "
                 "It is listed for completeness and is unlikely to fit.")
    if REQUIRED in by_req:
        r = by_req[REQUIRED]
        quotes = "; ".join(f'"{e}"' for e in dict.fromkeys(m.evidence_text for m in r))
        s.append(f"Its criteria require {_join(names[m.gene] for m in r)}: {quotes}.")
    for m in by_req.get(MENTIONED, []):
        s.append(f"It mentions {m.biomarker} but does not require {names[m.gene]}.")
    absent = [m for m in by_req.get(ABSENT, []) if not m.via_drugs]
    if absent and tier != "not_matched":
        s.append(f"It does not select on {_join(names[m.gene] for m in absent)}.")
    if drug_hits:
        s.append(f"Drugs named: {_join(f'{d.matched_name} (targets {_join(d.target_genes)})' for d in drug_hits)}.")
    if related:
        s.append(f"It also involves {_join(r.gene for r in related)}, which our papers name alongside "
                 f"{profile.biomarkers[0].biomarker}.")
    if unchecked:
        s.append(f"The profile does not record {_join(unchecked, 'or')} status, so check those criteria.")
    if support:
        n_rev = sum(p.reviewed is True for p in support)
        p = next((x for x in support if x.reviewed), support[0])  # cite a hand-checked paper when there is one
        year = f" ({p.year})" if p.year else ""
        if p.reviewed and p.relation:
            what = p.relation
        elif p.reviewed:
            what = f'"{p.title}"'
        else:
            what = f'"{p.title}" (unreviewed search hit)'
        s.append(f"{len(support)} supporting paper(s), {n_rev} checked by hand; "
                 f"for example PMID {p.paper_id}{year}: {_sentence(what)}")
    else:
        s.append("No paper in our set adds evidence beyond the biomarker itself.")
    if opposite:
        genes = {g for g in by_gene if any(_opposite_phrase(by_gene[g]) in w for p in opposite for w in p.why)}
        s.append(f"{len(opposite)} more paper(s) on these genes or drugs study "
                 f"{_join(_opposite_phrase(by_gene[g]) for g in by_gene if g in genes)} disease and are listed separately.")
    s.append(DISCLAIMER)
    return " ".join(_sentence(x) for x in s)


# ---------------------------------------------------------------- stage
def match_trial(trial: Trial, profile: Profile, papers: list[Paper], candidates: list[GeneCandidate],
                drugs: list[DrugTarget], terms: list[GeneTerm]) -> TrialMatch:
    drug_hits = _drug_hits(trial, drugs)
    matches = _biomarker_matches(trial, profile, drug_hits)
    related = _related_genes(trial, profile, candidates, terms, drug_hits)
    tier, label = _tier(matches, related, profile)
    unchecked = [r.gene for r in related if any("named in the trial text" in h for h in r.how)]
    support, opposite = _paper_lists(papers, profile, matches, related, drug_hits, terms)
    cap = config.MAX_SUPPORTING_PAPERS
    shown = support[:cap] + opposite[:cap]
    mock_inputs = (["trials"] if trial.is_mock else []) + (["papers"] if any(p.source == MOCK for p in shown) else [])
    return TrialMatch(
        nct_id=trial.nct_id, title=trial.title, phase=trial.phase, status=trial.status, url=trial.url,
        tier=tier, tier_rank=TIERS[tier], tier_label=label,
        biomarker_matches=matches, drugs=drug_hits, related_genes=related, unchecked_criteria=unchecked,
        supporting_papers=support[:cap], supporting_papers_total=len(support),
        supporting_papers_reviewed=sum(p.reviewed is True for p in support),
        opposite_status_papers=opposite[:cap], opposite_status_papers_total=len(opposite),
        explanation=_explain(tier, matches, drug_hits, related, unchecked, support, opposite, profile),
        eligibility_text=trial.eligibility_text, sponsor=trial.sponsor, status_detail=trial.status_detail,
        status_as_of=trial.status_as_of, status_caveat=trial.status_caveat,
        source=trial.source, mock_inputs=mock_inputs,
    )


def run(refresh: bool = False) -> list[TrialMatch]:
    """Always recomputes (local, deterministic); `refresh` is accepted for symmetry."""
    profile = load_profile()
    papers = read_rows(config.PAPERS_PATH, Paper)
    candidates = read_rows(config.GENE_CANDIDATES_PATH, GeneCandidate)
    trials = read_rows(config.TRIALS_PATH, Trial)
    drugs = read_rows(config.DRUG_TARGETS_PATH, DrugTarget)
    terms = read_rows(config.GENE_TERMS_PATH, GeneTerm) if config.GENE_TERMS_PATH.exists() else []
    rows = [match_trial(t, profile, papers, candidates, drugs, terms) for t in trials]
    rows.sort(key=lambda r: r.tier_rank)  # stable: dataset order inside a tier
    write_rows(config.TRIAL_MATCHES_PATH, rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 4: match the profile to the trial list (no scores)")
    ap.add_argument("--refresh", action="store_true", help="accepted for symmetry; matching always recomputes")
    args = ap.parse_args()
    out = run(refresh=args.refresh)
    for r in out:
        print(f"[{r.tier_rank}] {r.nct_id}  {r.tier_label}  | related: {[g.gene for g in r.related_genes]} "
              f"| drugs: {[d.matched_name for d in r.drugs]} | papers: {r.supporting_papers_total} "
              f"(+{r.opposite_status_papers_total} opposite status)")
    print(f"[matching] {len(out)} trials -> {config.TRIAL_MATCHES_PATH}")
