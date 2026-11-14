"""Stage 7 smoke test: every endpoint answers with the right shape, offline.

All contract paths point at tmp_path fixtures, so the real data/cache files are
never read or written (only data/input/biomarker.json is read, never written).
The fixture rows are deliberately fake: source "mock", MOCK- ids, a made-up gene.
"""

from fastapi.testclient import TestClient

from backend import config
from backend.app.main import app
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import GeneCandidate, GenomicContext, Paper, Trial, TrialMatch
from backend.store import write_rows


def test_api_smoke(tmp_path, monkeypatch):
    fixtures = {
        "PAPERS_PATH": [Paper(paper_id="MOCK-PMID-0001", title="Mock paper", genes_mentioned=["MOCKGENE"], source="mock")],
        "GENE_CANDIDATES_PATH": [GeneCandidate(gene="MOCKGENE", paper_ids=["MOCK-PMID-0001"], source="mock")],
        "GENOMIC_CONTEXT_PATH": [
            GenomicContext(gene="MOCKGENE", model_task="mock", model_output={"expression": 0.5}, model_score=0.5, source="mock")
        ],
        "TRIALS_PATH": [Trial(nct_id="MOCK-NCT-0001", title="Mock trial", source="mock")],
        "TRIAL_MATCHES_PATH": [
            TrialMatch(nct_id="MOCK-NCT-0002", title="Second", tier="partial_only", tier_rank=3, tier_label="x",
                       source="mock", mock_inputs=["trials"]),
            TrialMatch(nct_id="MOCK-NCT-0001", title="Mock trial", tier="requires_all_biomarkers", tier_rank=1,
                       tier_label="Requires HER2 positive and PIK3CA mutated", source="mock", mock_inputs=["trials"]),
        ],
    }
    for attr, rows in fixtures.items():
        path = tmp_path / f"{attr.lower()}.json"
        write_rows(path, rows)
        monkeypatch.setattr(config, attr, path)

    client = TestClient(app)

    health = client.get("/api/health").json()
    assert health["status"] == "ok" and all(health["files"].values())

    assert client.get("/api/biomarker").json()["gene"] == load_biomarker(config.BIOMARKER_PATH).gene

    profile = client.get("/api/profile").json()
    assert [b["gene"] for b in profile["biomarkers"]] == ["ERBB2", "PIK3CA"]

    trials = client.get("/api/trials", headers={"Origin": "http://localhost:3000"})
    assert trials.status_code == 200
    assert trials.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert trials.json()[0]["nct_id"] == "MOCK-NCT-0001"  # plain array, per the contract

    matches = client.get("/api/trial-matches").json()
    assert [m["nct_id"] for m in matches] == ["MOCK-NCT-0001", "MOCK-NCT-0002"]  # by tier_rank
    assert matches[0]["mock_inputs"] == ["trials"]

    assert client.get("/api/genes").json()[0]["gene"] == "MOCKGENE"
    assert client.get("/api/rankings").status_code == 404  # the scoring system is gone
    assert client.get("/api/papers").json()[0]["paper_id"] == "MOCK-PMID-0001"

    detail = client.get("/api/genes/mockgene")  # case-insensitive
    assert detail.status_code == 200
    detail = detail.json()
    assert "score" not in detail
    assert detail["candidate"]["paper_ids"] == ["MOCK-PMID-0001"]
    assert detail["genomic_context"]["model_output"] == {"expression": 0.5}
    assert [p["paper_id"] for p in detail["papers"]] == ["MOCK-PMID-0001"]
    assert set(detail["mock_inputs"]) == {"gene_candidates", "genomic_context", "papers"}
    assert client.get("/api/genes/NOT_A_GENE").status_code == 404

    meta = client.get("/api/meta").json()
    assert meta["has_mock_data"] is True
    assert {"trials", "genomic_context", "papers", "gene_candidates"} <= set(meta["mock_inputs"])
    assert meta["disclaimer"] == "Research prototype. Not medical advice."

    # A stage that has not run yet is a 503 that names the command to run, not a 500.
    monkeypatch.setattr(config, "TRIALS_PATH", tmp_path / "absent" / "trials.json")
    missing = client.get("/api/trials")
    assert missing.status_code == 503
    assert "backend.pipeline.trials" in missing.json()["detail"]["run"]
    assert client.get("/api/health").json()["files"]["trials"] is False

    # A malformed file (bad JSON, or a schema mismatch) is a JSON 500 naming the file, CORS intact.
    bad_json, bad_schema = tmp_path / "bad.json", tmp_path / "bad_biomarker.json"
    bad_json.write_text("{not json")
    bad_schema.write_text('{"tissue": "x"}')
    monkeypatch.setattr(config, "PAPERS_PATH", bad_json)
    monkeypatch.setattr(config, "BIOMARKER_PATH", bad_schema)
    for endpoint, path in (("/api/papers", bad_json), ("/api/biomarker", bad_schema)):
        broken = client.get(endpoint, headers={"Origin": "http://localhost:3000"})
        assert broken.status_code == 500
        assert broken.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert path.name in broken.json()["detail"]["message"] and broken.json()["detail"]["file"] == str(path)
