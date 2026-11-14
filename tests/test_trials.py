"""Stage 3 smoke test (offline): the curated spreadsheet import, cache-first, mock
fallback, and the optional ClinicalTrials.gov path with a canned API v2 study."""

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


def test_spreadsheet_import(tmp_path, monkeypatch):
    path = tmp_path / "trials.json"
    monkeypatch.setattr(config, "TRIALS_PATH", path)  # the committed spreadsheet is only read

    def no_network(*a, **k):
        raise AssertionError("network called")

    monkeypatch.setattr(clinicaltrials, "fetch_studies", no_network)

    rows = trials.run()  # no cache: import the spreadsheet
    assert len(rows) == 7 and not any(t.is_mock for t in rows)
    assert all(t.nct_id.startswith("NCT") and len(t.nct_id) == 11 for t in rows)
    assert all(t.source == trials.SPREADSHEET_SOURCE and t.url.endswith(t.nct_id) for t in rows)
    first = rows[0]
    assert first.nct_id == "NCT05894239" and first.phase == "Phase 3" and first.status == "Recruiting"
    assert "PIK3CA-mutated" in first.eligibility_text and first.sponsor == "Hoffmann-La Roche"
    assert first.status_as_of == "2026-11-14" and "Confirm each status" in first.status_caveat
    assert all(";" not in t.status and "(" not in t.status for t in rows)
    assert [t.nct_id for t in read_rows(path, Trial)] == [t.nct_id for t in rows]
    assert [t.nct_id for t in trials.run()] == [t.nct_id for t in rows]  # cache first


def test_mock_and_ctgov_fallbacks(tmp_path, monkeypatch):
    path = tmp_path / "trials.json"
    monkeypatch.setattr(config, "TRIALS_PATH", path)
    monkeypatch.setattr(config, "TRIALS_SPREADSHEET_PATH", tmp_path / "missing.xlsx")

    # Neither cache nor spreadsheet: a clearly labelled mock list.
    rows = trials.run()
    assert len(rows) == 6 and all(t.is_mock and t.nct_id.startswith("MOCK-NCT-") and t.url == "" for t in rows)

    # --ctgov: the query comes from the biomarker record, and the API mapping fills every field.
    seen = {}

    def fake_fetch(cond, term, page_size, max_studies, statuses):
        seen.update(cond=cond, term=term)
        return [clinicaltrials.to_trial(CANNED_STUDY)]

    monkeypatch.setattr(clinicaltrials, "fetch_studies", fake_fetch)
    [t] = trials.run(ctgov=True)
    assert seen["cond"] == "Breast Cancer" and '"HER2"' in seen["term"] and '"ERBB2"' in seen["term"]
    assert t.nct_id == "TEST-NCT-1" and t.phase == "Phase 1/Phase 2" and t.interventions == ["trastuzumab"]
    assert t.source == clinicaltrials.SNAPSHOT_SOURCE and not t.is_mock
