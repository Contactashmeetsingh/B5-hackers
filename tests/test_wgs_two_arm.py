"""Smoke test for the two-arm HER2+ patient genome workflow (offline)."""
import csv

import openpyxl

from workflows.wgs_two_arm import run


def test_two_arm_default_and_pik3ca(tmp_path):
    run.main(["--out-dir", str(tmp_path)])
    arm1 = list(csv.DictReader((tmp_path / "trial_ops.csv").open()))
    assert len(arm1) == 10 and all(r["her2_match"] == "yes" for r in arm1)
    wb = openpyxl.load_workbook(tmp_path / "her2_candidate_marker_patient_trials.xlsx")
    assert {"Arm 2 trial matches", "Prioritized genes", "Notes"} <= set(wb.sheetnames)
    genes = {r[0]: r for r in wb["Prioritized genes"].iter_rows(min_row=2, values_only=True)}
    assert "PIK3CA" in genes and "ERBB2" not in genes
    # ESR1/PGR have lab evidence but are GI low tier -> fail the rule
    hdr = [c.value for c in wb["Prioritized genes"][1]]
    assert genes["ESR1"][hdr.index("passes_rule")] == "no"

    run.main(["--out-dir", str(tmp_path), "--mutated-genes", "PIK3CA", "TP53"])
    ws = openpyxl.load_workbook(tmp_path / "her2_candidate_marker_patient_trials.xlsx")["Arm 2 trial matches"]
    hdr = [c.value for c in ws[1]]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert rows and all(r[hdr.index("Matched candidate gene(s)")] == "PIK3CA" for r in rows)
    assert all(r[hdr.index("Match level")].startswith("Better match (confirmed") for r in rows)
