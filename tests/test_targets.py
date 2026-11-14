"""Stage 2 smoke test (offline): candidates from fixture papers plus drug-target-only genes."""

import json

from backend import config
from backend.clients.ensembl import EnsemblGene
from backend.pipeline import targets
from backend.schemas import GeneCandidate
from backend.store import read_rows


def _fake_lookup(symbols, refresh=False):
    # Stand-in for Ensembl so the test never hits the network or the real cache.
    approved = {"SLC9A3R1": "NHERF1"}
    return {s: EnsemblGene(symbol=s, ensembl_id=f"ENSG-TEST-{s}", chrom="1", start=1, end=2,
                           strand=1, canonical_transcript=None, tss=1, assembly="GRCh38",
                           approved_symbol=approved.get(s, s))
            for s in symbols}


def test_targets_builds_candidates(tmp_path, monkeypatch):
    papers = [
        {"paper_id": "P1", "title": "t1", "genes_mentioned": ["ERBB2", "ERBB3"], "source": "keenable"},
        {"paper_id": "P2", "title": "t2", "genes_mentioned": ["ERBB2", "ERBB3", "SLC9A3R1"], "source": "keenable"},
    ]
    drugs = [{"drug": "drugA", "target_genes": ["ERBB2"], "source": "test"},
             {"drug": "drugB", "target_genes": ["PIK3CA"], "source": "test"}]
    (tmp_path / "papers.json").write_text(json.dumps(papers))
    (tmp_path / "drug_targets.json").write_text(json.dumps(drugs))
    monkeypatch.setattr(config, "PAPERS_PATH", tmp_path / "papers.json")
    monkeypatch.setattr(config, "DRUG_TARGETS_PATH", tmp_path / "drug_targets.json")
    monkeypatch.setattr(config, "GENE_CANDIDATES_PATH", tmp_path / "gene_candidates.json")
    monkeypatch.setattr(targets, "lookup_genes", _fake_lookup)

    rows = targets.run()
    by_gene = {r.gene: r for r in rows}

    assert [r.gene for r in rows] == ["ERBB2", "ERBB3", "SLC9A3R1", "PIK3CA"]  # papers desc, then gene
    assert by_gene["ERBB2"].paper_ids == ["P1", "P2"]           # biomarker gene is kept
    assert by_gene["PIK3CA"].paper_ids == []                    # reached only via drug_targets.json
    assert by_gene["PIK3CA"].in_targets_dataset and not by_gene["ERBB3"].in_targets_dataset
    assert by_gene["SLC9A3R1"].approved_symbol == "NHERF1"
    assert all(r.is_mock and r.targets_dataset == targets.STAND_IN_LABEL for r in rows)
    assert len(read_rows(tmp_path / "gene_candidates.json", GeneCandidate)) == 4
