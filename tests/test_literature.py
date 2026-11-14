"""Stage 1 smoke test (offline): queries from the profile, merging Keenable hits into
the curated cache, no snippet stored, and a failed refresh keeps real data."""

import json

from backend import config
from backend.pipeline import literature
from backend.pipeline.profile import load_profile
from backend.schemas import DrugTarget, Paper
from backend.store import read_rows, write_rows

SNIPPET = "SNIPPET-TEXT-THAT-MUST-NOT-BE-STORED"


class FakeKeenable:
    """Canned PubMed hits. IDs are deliberately not real PMIDs."""

    has_key = False

    def __init__(self):
        self.queries = []

    def search_pubmed(self, query, max_results=10):
        self.queries.append(query)
        return [
            {"paper_id": "TEST-1", "title": "already curated", "year": 2020, "url": "u1",
             "published_at": None, "snippet": SNIPPET},
            {"paper_id": "TEST-2", "title": "PIK3CA mutation in HER2-positive breast cancer", "year": 2024,
             "url": "u2", "published_at": "2024-01-01T00:00:00Z", "snippet": f"PTEN loss too. {SNIPPET}"},
            {"paper_id": "TEST-3", "title": "Alpelisib in HER2-negative, PIK3CA-mutated disease", "year": 2021,
             "url": "u3", "published_at": None, "snippet": SNIPPET},
            {"paper_id": "TEST-4", "title": "Unrelated cardiology paper", "year": 2019, "url": "u4",
             "published_at": None, "snippet": SNIPPET},
        ]


PUBMED = {  # what PubMed says about the fake PMIDs; the Keenable title and snippet are not trusted
    "TEST-2": {"title": "PIK3CA mutation in HER2-positive breast cancer", "year": 2024,
               "publication_types": ["Journal Article"], "abstract": "PTEN loss too."},
    "TEST-3": {"title": "Alpelisib for PIK3CA-mutated advanced breast cancer", "year": 2021,
               "publication_types": ["Review"], "abstract": "Approved for HR-positive, HER2-negative disease."},
    "TEST-4": {"title": "Unrelated cardiology paper", "year": 2019, "publication_types": [], "abstract": ""},
}


def fake_fetch(pmids):
    return {p: PUBMED[p] for p in pmids if p in PUBMED}


class BrokenKeenable(FakeKeenable):
    def search_pubmed(self, query, max_results=10):
        raise RuntimeError("Keenable down")


def test_queries_come_from_the_profile():
    drugs = [DrugTarget(drug="alpelisib", target_genes=["PIK3CA"], source="test"),
             DrugTarget(drug="trastuzumab", target_genes=["ERBB2"], source="test")]
    qs = literature.build_queries(load_profile(), drugs)
    assert qs[0] == "HER2 positive and PIK3CA mutated breast cancer"
    assert "alpelisib in HER2 positive breast cancer" in qs
    assert not any("trastuzumab" in q for q in qs)  # only drugs aimed at the non-primary biomarker


def test_literature_merge_and_fallbacks(tmp_path, monkeypatch):
    papers_path = tmp_path / "papers.json"
    monkeypatch.setattr(config, "PAPERS_PATH", papers_path)  # never touch the real cache
    monkeypatch.setattr(config, "KEENABLE_QUERY_LOG_PATH", tmp_path / "keenable_queries.json")
    monkeypatch.setattr(config, "GENE_CANDIDATES_PATH", tmp_path / "absent.json")

    # No cache at all: a clearly-mock file is written.
    mock = literature.run()
    assert mock and all(p.is_mock and p.paper_id.startswith("MOCK-PAPER-") for p in mock)

    # A curated cache exists: --refresh merges the hits behind it.
    curated = [Paper(paper_id="TEST-1", title="fixture", genes_mentioned=["ERBB2"], relation="ours", source="keenable")]
    write_rows(papers_path, curated)
    client = FakeKeenable()
    out = literature.run(refresh=True, client=client, fetch_records=fake_fetch)
    by_id = {p.paper_id: p for p in out}
    assert [p.paper_id for p in out] == ["TEST-1", "TEST-2", "TEST-3"]   # curated first; off-topic TEST-4 dropped
    assert by_id["TEST-1"].reviewed is True and by_id["TEST-1"].relation == "ours"
    assert by_id["TEST-2"].reviewed is False and by_id["TEST-2"].genes_mentioned == ["ERBB2", "PIK3CA"]
    assert by_id["TEST-3"].title == PUBMED["TEST-3"]["title"] and by_id["TEST-3"].publication_types == ["Review"]
    assert by_id["TEST-2"].found_by == client.queries                    # every query found it, each listed once
    assert by_id["TEST-2"].opposite_status == [] and by_id["TEST-3"].opposite_status == ["ERBB2"]  # from the abstract
    for path in (papers_path, tmp_path / "keenable_queries.json"):  # no snippet, no abstract text stored
        assert SNIPPET not in path.read_text() and "Approved for HR-positive" not in path.read_text()
    log = json.loads((tmp_path / "keenable_queries.json").read_text())
    assert log["queries"][0]["results"][0]["outcome"] == "already in papers.json"

    # Keenable fails: the cache is kept byte for byte.
    before = papers_path.read_bytes()
    assert [p.paper_id for p in literature.run(refresh=True, client=BrokenKeenable(), fetch_records=fake_fetch)] == [
        "TEST-1", "TEST-2", "TEST-3"]
    assert papers_path.read_bytes() == before
    assert read_rows(papers_path, Paper)[1].reviewed is False


def test_keenable_client_edge_cases(monkeypatch):
    from backend.clients import keenable

    assert keenable._retry_after("5", 2.0) == 5.0
    assert keenable._retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 2.0) == 0.0  # an HTTP date in the past
    assert keenable._retry_after("junk", 2.0) == 2.0
    client = keenable.KeenableClient(api_key=None)
    monkeypatch.setattr(client, "search", lambda *a, **k: {"results": [
        {"title": "A __PIK3CA__ study - PubMed", "url": "https://pubmed.ncbi.nlm.nih.gov/123/", "snippet": "s"},
        {"title": "no url", "url": None},
        {"title": "not pubmed", "url": "https://example.org/x"},
    ]})
    [hit] = client.search_pubmed("q")
    assert hit["paper_id"] == "123" and hit["title"] == "A PIK3CA study"

