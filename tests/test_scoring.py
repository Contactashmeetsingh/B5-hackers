"""Stages 4 and 6 smoke test (offline) on a tiny hand-computed fixture.

Weights are pinned here so the expected numbers stay valid when the team tunes
backend/config.py. Fixture IDs are deliberately not plausible PMIDs or NCT numbers.
"""

import pytest

from backend import config
from backend.pipeline import scoring
from backend.schemas import Trial
from backend.store import write_json

KC, MOCK, GI = "keenable", "mock", "genomic_intelligence"


def _setup(tmp_path, monkeypatch):
    for name, value in dict(LIT_SATURATION=5, W_LIT=0.5, W_MODEL=0.5, W_DIRECT=0.4, W_GENOMIC=0.6,
                            TOP_N_MATCHED=3, DIRECTNESS_REQUIRED=1.0, DIRECTNESS_MENTIONED=0.5,
                            DIRECTNESS_ABSENT=0.0).items():
        monkeypatch.setattr(config, name, value)

    files = {
        "BIOMARKER_PATH": {
            "tissue": "Breast", "biomarker": "HER2", "gene": "ERBB2", "measurement": "IHC",
            "source_field": "test", "coverage": "test", "aliases": ["HER2", "ERBB2", "HER2/neu"],
            "model_context": {"expression_target": "t", "expression_reference": "r", "chromatin_cell_types": []},
        },
        "DRUG_TARGETS_PATH": [
            {"drug": "trastuzumab", "aliases": ["Herceptin"], "target_genes": ["ERBB2"], "source": "test"},
            {"drug": "alpelisib", "aliases": ["Piqray"], "target_genes": ["PIK3CA"], "source": "test"},
            {"drug": "testmab", "aliases": [], "target_genes": ["NOTCAND"], "source": "test"},  # not a candidate
        ],
        "PAPERS_PATH": [{"paper_id": f"TEST-P{i}", "title": "t", "source": MOCK} for i in range(1, 7)],
        "GENE_CANDIDATES_PATH": [
            {"gene": "ERBB2", "paper_ids": [f"TEST-P{i}" for i in range(1, 7)], "source": KC},  # 6 -> lit 1.0
            {"gene": "PIK3CA", "paper_ids": [f"TEST-P{i}" for i in range(1, 6)], "source": KC},  # 5 -> 1.0
            {"gene": "ERBB3", "paper_ids": ["TEST-P1", "TEST-P2", "TEST-P3"], "source": KC},    # 0.6
            {"gene": "GRB7", "paper_ids": ["TEST-P1"], "source": MOCK},                         # 0.2
            {"gene": "ESR1", "paper_ids": ["TEST-P1", "TEST-P2", "TEST-P2"], "source": KC},     # dup -> 0.4
            {"gene": "JUN", "paper_ids": ["TEST-P1"], "source": KC},                            # 0.2
            {"gene": "PTEN", "paper_ids": [], "source": KC},                                    # 0.0
        ],
        # Raw model scores over candidates: min 0.2, max 1.0. ERBB3 unscored, JUN/PTEN absent,
        # NOTCAND is not a candidate and must not move the min.
        "GENOMIC_CONTEXT_PATH": [
            {"gene": "ERBB2", "model_score": 1.0, "source": GI},
            {"gene": "PIK3CA", "model_score": 0.8, "source": MOCK},
            {"gene": "GRB7", "model_score": 0.6, "source": GI},
            {"gene": "ESR1", "model_score": 0.2, "source": GI},
            {"gene": "ERBB3", "model_score": None, "source": GI},
            {"gene": "NOTCAND", "model_score": 0.0, "source": GI},
        ],
        "TRIALS_PATH": [
            {"nct_id": "TEST-NCT-1", "title": "Herceptin plus Piqray", "conditions": ["Breast Cancer"],
             "interventions": ["Herceptin", "Piqray", "testmab"],
             "eligibility_text": "Inclusion Criteria:\n* HER2-positive (IHC 3+)\n* ESR1, ERBB3 and GRB7 tested\n"
                                 "Exclusion Criteria:\n* none",
             "source": "clinicaltrials.gov snapshot"},
            {"nct_id": "TEST-NCT-2", "title": "Breast study", "source": MOCK,
             "eligibility_text": "Inclusion Criteria:\n* Any HER2 status\n* ESR1 status known"},
            {"nct_id": "TEST-NCT-3", "title": "Exercise study", "source": MOCK,
             "eligibility_text": "Inclusion Criteria:\n* Enrolment opens Jun 2025"},  # "Jun" is not JUN
            {"nct_id": "TEST-NCT-5", "title": "Registry", "source": MOCK,
             "eligibility_text": "Inclusion Criteria:\n* HER2 status recorded"},
            {"nct_id": "TEST-NCT-4", "title": "Endocrine study", "source": MOCK,
             # Second line is NCT07137871-style: a stray "HER2 overexpression" must not flip the trial.
             "eligibility_text": "Inclusion Criteria:\n* HR-positive, HER2-negative disease\n"
                                 "* HER2 negative: IHC 0 or 1+. If HER2 overexpression is equivocal by IHC...\n"
                                 "Exclusion Criteria:\n* HER2-positive disease"},
        ],
    }
    for attr, payload in files.items():
        path = tmp_path / f"{attr.lower()}.json"
        write_json(path, payload)
        monkeypatch.setattr(config, attr, path)
    monkeypatch.setattr(config, "GENE_SCORES_PATH", tmp_path / "gene_scores.json")
    monkeypatch.setattr(config, "RANKINGS_PATH", tmp_path / "rankings.json")


def test_scoring(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    # ---- stage 4: lit = min(1, n/5); model = min-max over scored candidates; combined = 0.5/0.5
    genes = scoring.run_gene_scores()
    by = {g.gene: g for g in genes}
    assert [g.gene for g in genes] == ["ERBB2", "PIK3CA", "GRB7", "ERBB3", "ESR1", "JUN", "PTEN"]
    assert (by["PIK3CA"].literature_score, by["PIK3CA"].model_score, by["PIK3CA"].combined_score) == (1.0, 0.75, 0.875)
    assert (by["GRB7"].literature_score, by["GRB7"].model_score, by["GRB7"].combined_score) == (0.2, 0.5, 0.35)
    assert (by["ESR1"].literature_score, by["ESR1"].model_score) == (0.4, 0.0)  # duplicate id counted once
    assert by["ERBB3"].model_score == 0.0 and by["JUN"].model_score == 0.0      # unscored / missing -> 0
    assert by["ERBB2"].combined_score == 1.0
    assert scoring._min_max({"A": 0.4, "B": 0.4}) == {"A": 0.0, "B": 0.0}       # degenerate case
    assert config.GENE_SCORES_PATH.exists()

    # ---- stage 6
    ranked = scoring.run_trial_rankings()
    assert [r.nct_id for r in ranked] == ["TEST-NCT-1", "TEST-NCT-2", "TEST-NCT-4", "TEST-NCT-5", "TEST-NCT-3"]
    assert [r.rank for r in ranked] == [1, 2, 3, 4, 5]
    r1, r2, r4, r5, r3 = ranked

    # Required + drug-reached PIK3CA. ERBB2 excluded; top 3 of PIK3CA .875, GRB7 .35, ERBB3 .3 (ESR1 .2 dropped).
    assert [m.gene for m in r1.matched_genes] == ["ERBB2", "PIK3CA", "GRB7", "ERBB3", "ESR1"]  # NOTCAND dropped
    assert r1.biomarker_directness == 1.0
    assert r1.genomic_match == pytest.approx(0.5083)
    assert r1.trial_score == pytest.approx(0.705)  # 0.4 * 1.0 + 0.6 * 0.5083
    assert r1.matched_genes[1].paper_ids == [f"TEST-P{i}" for i in range(1, 6)]
    assert r1.mock_inputs == ["gene_candidates", "genomic_context"] and r1.source == "clinicaltrials.gov snapshot"

    # Mentioned only; ESR1 alone -> genomic_match 0.2.
    assert (r2.biomarker_directness, r2.genomic_match, r2.trial_score) == (0.5, 0.2, 0.32)
    assert r2.mock_inputs == ["trials"]

    # HER2-negative requirement and an exclusion-only "HER2-positive" are mentions, not requirements.
    assert (r4.biomarker_directness, r4.genomic_match, r4.trial_score) == (0.5, 0.0, 0.2)
    assert r5.trial_score == r4.trial_score  # tie broken by nct_id

    # Nothing matched: "Jun 2025" does not match the exact-case symbol JUN.
    assert (r3.biomarker_directness, r3.genomic_match, r3.trial_score, r3.matched_genes) == (0.0, 0.0, 0.0, [])
    assert config.RANKINGS_PATH.exists()

    # Directness phrasing seen in live eligibility text: "+" shorthand is positive,
    # negations between alias and status word are not, HER2-low is required.
    def directness(inclusion):
        t = Trial(nct_id="TEST-NCT-X", title="t", eligibility_text=f"Inclusion Criteria:\n{inclusion}", source=MOCK)
        return scoring._biomarker_directness(t, ["HER2", "ERBB2", "HER2/neu"])

    assert directness("* HER2+ disease") == directness("* HR-/HER2+ early breast cancer") == 1.0
    assert directness("* HER2 not overexpressed") == directness("* HER2 non-amplified by ISH") == 0.5
    assert directness("* HER2-low (IHC 1+ or 2+/ISH-)\n* HER2-negative per ASCO/CAP") == 1.0
