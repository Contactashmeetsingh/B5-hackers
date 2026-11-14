"""Stage 5 smoke test (offline): mock fallback, cache-first, and the --refresh path
with the HTTP client replaced by a canned API v2 study."""

from backend import config
from backend.clients import clinicaltrials
from backend.pipeline import trials
from backend.schemas import Trial
from backend.store import read_rows

# Shape of one ClinicalTrials.gov API v2 study, trimmed to the fields we map.
# The ID is deliberately not a plausible NCT number.
CANNED_STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "TEST-NCT-1", "briefTitle": "Test study"},
        "statusModule": {"overallStatus": "RECRUITING"},
        "designModule": {"phases": ["PHASE1", "PHASE2"]},
        "conditionsModule": {"conditions": ["Breast Cancer"]},
        "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "trastuzumab"}]},
        "eligibilityModule": {"eligibilityCriteria": "Inclusion Criteria:\n* test"},
    }
}


def test_trials_stage(tmp_path, monkeypatch):
    path = tmp_path / "trials.json"
    monkeypatch.setattr(config, "TRIALS_PATH", path)

    # No cache, no --refresh: a clearly labelled mock snapshot is written.
    rows = trials.run()
    assert path.exists() and len(rows) == 6
    assert all(t.is_mock and t.nct_id.startswith("MOCK-NCT-") and t.url == "" for t in rows)
    assert [t.nct_id for t in read_rows(path, Trial)] == [t.nct_id for t in rows]

    # Cache first: a second run must not touch the network.
    def no_network(*a, **k):
        raise AssertionError("network called without --refresh")

    monkeypatch.setattr(clinicaltrials, "fetch_studies", no_network)
    assert [t.nct_id for t in trials.run()] == [t.nct_id for t in rows]

    # --refresh: the query comes from the biomarker record, and the API mapping fills every field.
    seen = {}

    def fake_fetch(cond, term, page_size, max_studies, statuses):
        seen.update(cond=cond, term=term)
        return [clinicaltrials.to_trial(CANNED_STUDY)]

    monkeypatch.setattr(clinicaltrials, "fetch_studies", fake_fetch)
    [t] = trials.run(refresh=True)
    assert seen["cond"] == "Breast Cancer" and '"HER2"' in seen["term"] and '"ERBB2"' in seen["term"]
    assert t.nct_id == "TEST-NCT-1" and t.phase == "Phase 1/Phase 2" and t.status == "RECRUITING"
    assert t.interventions == ["trastuzumab"] and t.url == "https://clinicaltrials.gov/study/TEST-NCT-1"
    assert t.source == clinicaltrials.SNAPSHOT_SOURCE and not t.is_mock
    assert read_rows(path, Trial)[0].nct_id == "TEST-NCT-1"
