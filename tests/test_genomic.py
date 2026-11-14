"""Genomic Intelligence stage smoke test (offline): strand-aware windows and splice junctions, 7-task scoring,
cache-first run with a mock row for an unscored gene, and GI error parsing."""

import json

import pytest

from backend import config
from backend.clients.genomic_intelligence import GIError, _parse_tool_error
from backend.pipeline import genomic
from backend.schemas import GeneCandidate, GenomicContext
from backend.store import read_rows, write_rows


def _digest(gene, target, reference, promoter, chromatin_calls, enhancer=1.0, splice=1.0, annotation=0.9, composite=2.0):
    """A minimal stand-in for data/cache/genomic_raw/<GENE>.json (synthetic test values)."""
    rid = {"request_id": None}
    return {
        "gene": gene, "retrieved": "test", "server": {}, "demo_key": True,
        "models": {t: f"m-{t}" for t in genomic.MODEL_TASKS},
        "locus": {"ensembl_id": f"ENSG-{gene}", "chrom": "17", "strand": 1, "tss": 1000,
                  "tss_source": "test", "tss_matches_ensembl": True, "expression_window": "17:1-2000"},
        "expression": {"target": {"description": "t", "log_tpm": target, "tpm": 0, "scored_window": None, **rid},
                       "reference": {"description": "r", "log_tpm": reference, "tpm": 0, "scored_window": None, **rid}},
        "composite": {"description": "t", "genes_found": 1, "found_at_tss": composite is not None,
                      "log_tpm": composite, "distance_to_canonical_tss_bp": 0, **rid},
        "promoter": {"max_probability": promoter, "upstream_window_probability": promoter, "windows": [], **rid},
        "chromatin": {"threshold": 0.5, "windows": 10, "labels_called_all_cell_types": 100,
                      "on_tissue_cell_types": ["MCF-7"], "on_tissue_labels_called": chromatin_calls,
                      "on_tissue_by_feature": {}, "on_tissue_calls": [], **rid},
        "enhancer": {"dev_score_max": enhancer, "hk_score_max": enhancer, "dev_score_mean": 0, "hk_score_mean": 0,
                     "windows": 9, **rid},
        "splice": {"junctions_in_window": 4, "junctions_recovered": int(4 * splice), "recall": splice,
                   "sites_called": 4, "precision": 1.0, "recovered": [], **rid},
        "annotation": {"transcripts_found": 1, "found_at_tss": annotation > 0, "confidence": annotation,
                       "transcript_type": "mRNA", "transcript_type_score": 0.9, "distance_to_canonical_tss_bp": 0, **rid},
    }


def test_genomic_stage(tmp_path, monkeypatch):
    # 1. Windows and splice junctions: gene-sense, TSS at offset 1,000 (or 0 downstream), both strands.
    assert genomic.tss_window("17", 39700064, 1, 1000) == ("17:39699064-39701063", 1)
    assert genomic.tss_window("1", 58784047, -1, 1000) == ("1:58783048-58785047", -1)
    assert genomic.downstream_window("17", 1000, 1, 100) == ("17:1000-1099", 1)
    assert genomic.downstream_window("17", 1000, -1, 100) == ("17:901-1000", -1)
    # plus strand: exons [1000-1010] [1050-1060] -> donor at 1010, acceptor at 1050
    assert genomic.splice_junctions([[1000, 1010], [1050, 1060]], 1, 1000, 100) == [
        {"type": "donor", "offset": 10}, {"type": "acceptor", "offset": 50}]
    # minus strand (transcription order): [990-1000] then [940-950] -> donor at 990, acceptor at 950
    assert genomic.splice_junctions([[990, 1000], [940, 950]], -1, 1000, 100) == [
        {"type": "donor", "offset": 10}, {"type": "acceptor", "offset": 50}]

    # 2. Scoring: A is best on every task, C worst; C has no composite readout (task skipped).
    digests = {
        "A": _digest("A", 5.0, 1.0, promoter=1.0, chromatin_calls=40, enhancer=2.0, splice=1.0, annotation=1.0, composite=5.0),
        "B": _digest("B", 3.0, 2.0, promoter=0.5, chromatin_calls=20, enhancer=1.0, splice=0.5, annotation=0.5, composite=3.0),
        "C": _digest("C", 1.0, 3.0, promoter=0.0, chromatin_calls=0, enhancer=0.0, splice=0.0, annotation=0.0, composite=None),
    }
    s = genomic.score_digests(digests)
    assert s["A"]["model_score"] == 1.0 and s["C"]["model_score"] == 0.0
    assert s["C"]["task_scores"]["composite"] is None and "composite" not in s["C"]["tasks_used"]
    # B: expression .5*(3-1)/4 + .5*(1-(-2))/6 = .5; composite (3-3)/(5-3) = 0 (only A, B have it);
    # promoter .5; chromatin .5; enhancer .5; splice .5; annotation .5 -> mean of 7 = 3/7
    assert s["B"]["task_scores"]["expression"] == 0.5 and s["B"]["task_scores"]["composite"] == 0.0
    assert s["B"]["model_score"] == round(3 / 7, 4)

    # 3. run(): offline, cache-first. ERBB2 has a cached digest, GHOST does not -> mock row, no score.
    monkeypatch.setattr(config, "GENE_CANDIDATES_PATH", tmp_path / "gene_candidates.json")
    monkeypatch.setattr(config, "GENOMIC_CONTEXT_PATH", tmp_path / "genomic_context.json")
    monkeypatch.setattr(config, "GI_RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(genomic, "lookup_genes", lambda genes, **kw: {})  # no Ensembl in tests
    write_rows(config.GENE_CANDIDATES_PATH, [
        GeneCandidate(gene="ERBB2", source="mock"), GeneCandidate(gene="GHOST", source="mock"),
    ])
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "ERBB2.json").write_text(json.dumps(_digest("ERBB2", 3.0, 2.0, 0.9, 20)))

    rows = genomic.run(offline=True, verbose=False)
    by_gene = {r.gene: r for r in rows}
    assert by_gene["ERBB2"].source == "genomic_intelligence"
    assert 0.0 <= by_gene["ERBB2"].model_score <= 1.0
    assert by_gene["GHOST"].is_mock and by_gene["GHOST"].model_score is None
    assert read_rows(config.GENOMIC_CONTEXT_PATH, GenomicContext)  # written file honours the contract

    # 4. GI tool errors are discriminated on error.code, not the message.
    code, _ = _parse_tool_error('Error executing tool predict_promoter: {"error":{"code":"unknown_ref","message":"x"}}')
    assert code == "unknown_ref"
    assert GIError("rate_limited", "slow down").retryable and not GIError("invalid_input", "bad").retryable


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
