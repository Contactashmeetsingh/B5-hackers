"""Stage 1 smoke test (offline): mock only when no cache, and a failed refresh keeps real data."""

from backend import config
from backend.pipeline import literature
from backend.schemas import Paper
from backend.store import read_rows, write_rows


def test_literature_mock_then_refresh_keeps_cache(tmp_path, monkeypatch):
    papers_path = tmp_path / "papers.json"
    monkeypatch.setattr(config, "PAPERS_PATH", papers_path)  # never touch the real cache

    # No cache at all: a clearly-mock file is written.
    mock = literature.run()
    assert mock and all(p.is_mock and p.paper_id.startswith("MOCK-PAPER-") for p in mock)
    assert papers_path.exists()

    # A "real" cache exists: --refresh fails (Keenable not documented) and must not overwrite it.
    real = [Paper(paper_id="TEST-1", title="fixture", genes_mentioned=["ERBB2"], source="keenable")]
    write_rows(papers_path, real)
    before = papers_path.read_bytes()
    out = literature.run(refresh=True)
    assert [p.paper_id for p in out] == ["TEST-1"]
    assert papers_path.read_bytes() == before
    assert read_rows(papers_path, Paper)[0].source == "keenable"
