"""Stage 4 smoke test (offline): status reading, every tier, drugs, related genes,
supporting papers and the explanation. All fixtures are fake (TEST- ids)."""

import pytest

from backend import config
from backend.pipeline import matching
from backend.pipeline.biomarker_text import classify
from backend.pipeline.profile import load_profile
from backend.schemas import DrugTarget, GeneCandidate, GeneTerm, Paper, Trial, TrialMatch
from backend.store import read_rows, write_rows

PROFILE = load_profile()
HER2, PIK3CA = PROFILE.biomarkers


@pytest.mark.parametrize("text, her2, pik3ca", [
    ("Central testing must document HER2-positivity and a PIK3CA-mutated tumor", "required", "required"),
    ("HR+/HER2+ with centrally confirmed ER, PR, HER2 status and a tumor PIK3CA mutation", "required", "required"),
    ("Hormone receptor positive, HER2 positive, anatomic stage IIA-IIIC", "required", "absent"),
    ("HER2-low disease (IHC 1+, or IHC 2+ with negative ISH)", "conflicts", "absent"),
    ("ER+/HER2- breast cancer with a PIK3CA H1047R mutation", "conflicts", "required"),
    ("No PIK3CA mutation on tumour testing; HER2 not overexpressed", "conflicts", "conflicts"),
    ("PIK3CA wild-type tumours", "absent", "conflicts"),
    ("PIK3CA mutation status known; any HER2 status", "mentioned", "mentioned"),
    ("HER2-positive or HER2-negative cohorts", "mentioned", "absent"),
    ("human epidermal growth factor receptor-2-negative advanced breast cancer", "conflicts", "absent"),
])
def test_classify(text, her2, pik3ca):
    assert (classify(text, HER2).requirement, classify(text, PIK3CA).requirement) == (her2, pik3ca)


def _trial(n, title, criteria):
    return Trial(nct_id=f"TEST-NCT-{n}", title=title, eligibility_text=criteria, source="test")


def test_matching(tmp_path, monkeypatch):
    trials = [
        _trial(1, "drugX + Phesgo in HER2+ disease", "HER2-positive (IHC 3+); ER/PR positivity"),
        _trial(2, "alpelisib + trastuzumab", "HER2-positive disease and a PIK3CA-mutated tumor"),
        _trial(3, "Trastuzumab deruxtecan in HER2-low disease", "HER2-low (IHC 1+ or 2+/ISH-)"),
        _trial(4, "Exercise study", "Any adult with breast cancer"),
        _trial(5, "Tucatinib", "HER2 positive by local testing"),
        _trial(6, "Inavolisib study", "Any HER2 status"),
    ]
    papers = [
        Paper(paper_id="TEST-P1", title="HER2 biology", genes_mentioned=["ERBB2"], source="keenable", reviewed=True),
        Paper(paper_id="TEST-P2", title="PIK3CA mutations in HER2-positive breast cancer", year=2016,
              genes_mentioned=["ERBB2", "PIK3CA"], relation="ours", source="keenable", reviewed=True),
        Paper(paper_id="TEST-P3", title="Alpelisib for HER2-negative disease", year=2020,
              genes_mentioned=["ERBB2", "PIK3CA"], source="keenable", reviewed=False),
        Paper(paper_id="TEST-P4", title="Estrogen receptor and HER2 crosstalk", year=2023,
              genes_mentioned=["ERBB2", "ESR1"], relation="ours too", source="keenable", reviewed=True),
    ]
    candidates = [GeneCandidate(gene=g, paper_ids=ids, source="mock")
                  for g, ids in (("ERBB2", ["TEST-P1"]), ("PIK3CA", ["TEST-P2"]), ("ESR1", ["TEST-P4"]), ("PGR", []))]
    drugs = [DrugTarget(drug="trastuzumab", target_genes=["ERBB2"], source="t"),
             DrugTarget(drug="trastuzumab deruxtecan", aliases=["T-DXd"], target_genes=["ERBB2"], source="t"),
             DrugTarget(drug="pertuzumab, trastuzumab and hyaluronidase", aliases=["Phesgo"], target_genes=["ERBB2"], source="t"),
             DrugTarget(drug="tucatinib", target_genes=["ERBB2"], source="t"),
             DrugTarget(drug="alpelisib", target_genes=["PIK3CA"], source="t"),
             DrugTarget(drug="inavolisib", target_genes=["PIK3CA"], source="t")]
    terms = [GeneTerm(term="ER", genes=["ESR1"], note="estrogen receptor", source="t"),
             GeneTerm(term="PR", genes=["PGR"], note="progesterone receptor", source="t"),
             GeneTerm(term="estrogen receptor", genes=["ESR1"], note="estrogen receptor", source="t")]
    for attr, rows in (("TRIALS_PATH", trials), ("PAPERS_PATH", papers), ("GENE_CANDIDATES_PATH", candidates),
                       ("DRUG_TARGETS_PATH", drugs), ("GENE_TERMS_PATH", terms)):
        monkeypatch.setattr(config, attr, tmp_path / f"{attr}.json")
        write_rows(tmp_path / f"{attr}.json", rows)
    monkeypatch.setattr(config, "TRIAL_MATCHES_PATH", tmp_path / "trial_matches.json")

    out = matching.run()
    by = {m.nct_id: m for m in out}
    assert [m.tier_rank for m in out] == sorted(m.tier_rank for m in out)
    assert read_rows(tmp_path / "trial_matches.json", TrialMatch)[0].nct_id == out[0].nct_id

    t2 = by["TEST-NCT-2"]
    assert t2.tier == "requires_all_biomarkers" and t2.tier_label == "Requires HER2 positive and PIK3CA mutated"
    assert {d.drug for d in t2.drugs} == {"alpelisib", "trastuzumab"}
    pik = next(m for m in t2.biomarker_matches if m.gene == "PIK3CA")
    assert pik.requirement == "required" and pik.via_drugs == ["alpelisib"] and "PIK3CA-mutated" in pik.evidence_text
    ids = [p.paper_id for p in t2.supporting_papers]
    assert ids == ["TEST-P2", "TEST-P3"]                              # opposite-status paper last
    assert "TEST-P1" not in ids                                       # HER2 alone supports nothing in particular
    p3 = next(p for p in t2.supporting_papers if p.paper_id == "TEST-P3")
    assert any("HER2-negative" in w for w in p3.why)
    assert "PMID TEST-P2" in t2.explanation and "not a recommendation" in t2.explanation

    t1 = by["TEST-NCT-1"]
    assert t1.tier == "partial_plus_related" and [g.gene for g in t1.related_genes] == ["ESR1", "PGR"]
    assert t1.unchecked_criteria == ["ESR1", "PGR"] and "ESR1 or PGR status" in t1.explanation
    assert [d.matched_name for d in t1.drugs] == ["Phesgo"]

    t3 = by["TEST-NCT-3"]
    assert t3.tier == "conflicts" and [d.drug for d in t3.drugs] == ["trastuzumab deruxtecan"]  # no bare "trastuzumab"
    assert by["TEST-NCT-4"].tier == "not_matched"
    assert by["TEST-NCT-5"].tier == "partial_only" and by["TEST-NCT-5"].tier_label == "Requires HER2 positive only"
    assert by["TEST-NCT-6"].tier == "mentions_only"
    assert all(m.mock_inputs == [] for m in out)  # gene_candidates' stand-in field is never read here
