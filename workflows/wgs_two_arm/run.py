"""Two-arm workflow: HER2+ patient genome -> clinical trials.

Arm 1  Match the patient's HER2+ status to every HER2+ trial in the trial database.
       Output: data/output/trial_ops.csv

Arm 2  Find genes that (a) have lab evidence with HER2 in the Keenable literature AND
       (b) are GI high or middle tier in the DNA-context ranking. Check which of them
       are mutated in the patient's genome, then go back to the trial database and pick
       the trials whose extra marker is one of those genes: a better match than HER2 alone.
       Output: data/output/her2_candidate_marker_patient_trials.xlsx

Inputs (all in the repo, offline):
  data/input/patient_genome.json                          patient: HER2 status + genome
  clinical_trials/her2_candidate_marker_open_trials.xlsx  trial database (10 HER2+ trials)
  keenable/her2_interactors_experimental.md               Keenable lab-evidence papers
  genomic_intelligence/her2_genes_dna_context_ranking.csv GI DNA-context tiers

There is no score. Trials are grouped and ordered by simple rules, explained in each row.

    python -m workflows.wgs_two_arm.run
    python -m workflows.wgs_two_arm.run --mutated-genes PIK3CA TP53 GATA3 MAP3K1 CDH1   # demo override
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[2]
PATIENT = ROOT / "data/input/patient_genome.json"
TRIALS_XLSX = ROOT / "clinical_trials/her2_candidate_marker_open_trials.xlsx"
KEENABLE_MD = ROOT / "keenable/her2_interactors_experimental.md"
GI_CSV = ROOT / "genomic_intelligence/her2_genes_dna_context_ranking.csv"
OUT_DIR = ROOT / "data/output"
ARM1_CSV = OUT_DIR / "trial_ops.csv"
ARM2_XLSX = OUT_DIR / "her2_candidate_marker_patient_trials.xlsx"

BIOMARKER_GENE = "ERBB2"
GI_TIERS_ALLOWED = ("high", "middle")          # arm 2 rule, part (b)
HER2_POSITIVE = re.compile(r"HER2[\s-]*(positiv|\+)|HER2 positivity|HER2\+|triple-positive|IHC 3\+", re.I)
# Markers whose trial requirement is a protein / hormone-receptor status, not a DNA mutation.
STATUS_MARKERS = {"ESR1": "ER status (IHC on the pathology report)", "PGR": "PR status (IHC on the pathology report)"}
PHASE_ORDER = {"3": 0, "3b": 0, "2/3": 1, "2": 2, "1b/2": 3, "1/2": 3, "1": 4}


# ---------- inputs ----------

def load_patient(path: Path, override: list[str] | None) -> dict:
    p = json.loads(path.read_text())
    if p.get("her2_status") != "positive":
        raise SystemExit("This workflow is for HER2-positive patients (her2_status must be 'positive').")
    g = p["genome"]
    if g.get("format") == "vcf":
        raise SystemExit("VCF input is not implemented yet; use genome.format = 'gene_names'.")
    genes = override if override is not None else g.get("mutated_genes", [])
    p["mutated_genes"] = sorted({x.strip().upper() for x in genes if x.strip()})
    p["input_source"] = "command-line override" if override is not None else str(path.relative_to(ROOT))
    return p


def load_trials(path: Path) -> list[dict]:
    ws = openpyxl.load_workbook(path, data_only=True)["Open HER2 trials"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if r and r[0]]


def load_keenable(path: Path) -> dict[str, dict]:
    """Per gene: lab-evidence papers (PMIDs) and evidence type, from the experimental-filter file."""
    text = path.read_text()
    papers = text.split("## Papers")[1].split("## Strongest")[0]
    strongest = text.split("## Strongest evidence per gene")[1].split("##")[0]
    out: dict[str, dict] = defaultdict(lambda: {"pmids": [], "evidence": "functional"})
    for line in papers.splitlines():
        m = re.match(r"\| (`[^|]*`) \|[^|]*\|[^|]*\|[^|]*\| \[(\d+)\]", line)
        if m:
            for g in re.findall(r"`([A-Z0-9]+)`", m.group(1)):
                out[g]["pmids"].append(m.group(2))
    for line in strongest.splitlines():
        if line.startswith("| **Physical"):
            for g in re.findall(r"`([A-Z0-9]+)`", line):
                out[g]["evidence"] = "physical + functional"
    return dict(out)


def load_gi(path: Path) -> dict[str, dict]:
    return {r["gene"]: r for r in csv.DictReader(path.open())}


def trial_marker_genes(trial: dict, known: set[str]) -> list[str]:
    text = str(trial.get("Marker(s) from your list") or "")
    return [g for g in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", text) if g in known and g != BIOMARKER_GENE]


# ---------- arm 1 ----------

def arm1(patient: dict, trials: list[dict], known: set[str]) -> list[dict]:
    rows = []
    for t in trials:
        req = str(t.get("What the trial requires") or "")
        her2_ok = bool(HER2_POSITIVE.search(req) or HER2_POSITIVE.search(str(t.get("Trial") or "")))
        markers = trial_marker_genes(t, known)
        extra = []
        for g in dict.fromkeys(markers):
            if g in STATUS_MARKERS:
                extra.append(f"{g}: {STATUS_MARKERS[g]} - not in genome data")
            elif g in patient["mutated_genes"]:
                extra.append(f"{g}: mutated in patient genome")
            else:
                extra.append(f"{g} mutation: not reported in patient genome")
        rows.append({
            "nct_id": t["NCT ID"], "trial": t["Trial"], "sponsor": t["Sponsor"], "phase": t["Phase"],
            "status": t["Status (as of 2026-11-14)"], "link": t["Link"],
            "her2_match": "yes" if her2_ok else "no",
            "trial_requires": req,
            "extra_markers": "; ".join(dict.fromkeys(markers)) or "none",
            "patient_extra_marker_status": " | ".join(extra) or "no extra marker",
            "arm1_result": ("HER2+ match; extra requirement(s) still to check" if her2_ok and markers
                            else "HER2+ match" if her2_ok else "no HER2 requirement found"),
        })
    rows.sort(key=lambda r: (r["her2_match"] != "yes", PHASE_ORDER.get(str(r["phase"]), 9), r["nct_id"]))
    return rows


# ---------- arm 2 ----------

def prioritize_genes(patient: dict, keen: dict, gi: dict) -> list[dict]:
    genes = sorted((set(keen) | set(gi)) - {BIOMARKER_GENE})
    out = []
    for g in genes:
        k, r = keen.get(g), gi.get(g)
        has_lab = bool(k and k["pmids"])
        tier = r["tier"] if r else "not scored"
        passes = has_lab and tier in GI_TIERS_ALLOWED
        mutated = g in patient["mutated_genes"]
        out.append({
            "gene": g,
            "patient_mutated": "yes" if mutated else "not reported",
            "keenable_lab_evidence": "yes" if has_lab else "no",
            "keenable_evidence_type": k["evidence"] if has_lab else "",
            "keenable_n_papers": len(k["pmids"]) if has_lab else 0,
            "keenable_pmids": ", ".join(k["pmids"]) if has_lab else "",
            "gi_tier": tier,
            "gi_rank": int(r["rank"]) if r else None,
            "gi_dna_context_score": round(float(r["dna_context_score"]), 3) if r else None,
            "passes_rule": "yes" if passes else "no",
            "priority": ("1: prioritized and mutated in patient" if passes and mutated
                         else "2: prioritized, check patient genome" if passes
                         else "-: fails rule"),
            "why": (f"lab evidence ({k['evidence']}, {len(k['pmids'])} paper(s)) + GI {tier}" if passes
                    else "no Keenable lab evidence" if not has_lab
                    else f"GI tier is {tier} (rule needs high or middle)"),
        })
    order = {"1": 0, "2": 1, "-": 2}
    out.sort(key=lambda x: (order[x["priority"][0]], x["gi_rank"] or 99))
    return out


def arm2(patient: dict, trials: list[dict], genes: list[dict], arm1_rows: list[dict], known: set[str]) -> list[dict]:
    pri = {g["gene"]: g for g in genes if g["passes_rule"] == "yes"}
    a1 = {r["nct_id"]: i for i, r in enumerate(arm1_rows, 1)}
    rows = []
    for t in trials:
        hits = [g for g in dict.fromkeys(trial_marker_genes(t, known)) if g in pri]
        if not hits:
            continue
        confirmed = [g for g in hits if pri[g]["patient_mutated"] == "yes"]
        why = []
        for g in hits:
            p = pri[g]
            why.append(f"{g}: Keenable {p['keenable_evidence_type']} evidence (PMID {p['keenable_pmids']}); "
                       f"GI {p['gi_tier']} tier, rank {p['gi_rank']}; "
                       + ("mutated in this patient." if g in confirmed else "patient mutation status not reported - test it."))
        rows.append({
            **{k: t[k] for k in ("NCT ID", "Trial", "Sponsor", "Phase", "Marker(s) from your list",
                                 "What the trial requires", "Status (as of 2026-11-14)", "Link")},
            "Matched candidate gene(s)": ", ".join(hits),
            "Patient genome status": ("mutated: " + ", ".join(confirmed)) if confirmed else "not reported (check genome)",
            "Match level": "Better match (confirmed in patient)" if confirmed else "Candidate better match (pending genome check)",
            "Arm 1 position": a1.get(t["NCT ID"]),
            "Why this is a better match than HER2 alone": " ".join(why),
        })
    rows.sort(key=lambda r: (r["Match level"].startswith("Candidate"), PHASE_ORDER.get(str(r["Phase"]), 9), r["NCT ID"]))
    for i, r in enumerate(rows, 1):
        r["Arm 2 rank"] = i
    return rows


# ---------- outputs ----------

def write_arm1(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm1_rank", *rows[0].keys()])
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"arm1_rank": i, **r})


def _sheet(wb, title: str, rows: list[dict], cols: list[str] | None = None) -> None:
    ws = wb.create_sheet(title)
    cols = cols or (list(rows[0].keys()) if rows else ["(none)"])
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append([r.get(c) for c in cols])
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(60, max(12, len(c) + 2))
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


def write_arm2(trial_rows, gene_rows, patient, path: Path) -> None:
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    cols = ["Arm 2 rank", "NCT ID", "Trial", "Sponsor", "Phase", "Matched candidate gene(s)", "Patient genome status",
            "Match level", "Why this is a better match than HER2 alone", "Marker(s) from your list",
            "What the trial requires", "Status (as of 2026-11-14)", "Arm 1 position", "Link"]
    _sheet(wb, "Arm 2 trial matches", trial_rows, cols)
    _sheet(wb, "Prioritized genes", gene_rows)
    notes = [
        {"Item": "Patient", "Detail": f"{patient['patient_id']} (synthetic demo: {patient.get('synthetic')}); HER2 {patient['her2_status']}; "
                                      f"genome genes given: {', '.join(patient['mutated_genes']) or 'none'} (source: {patient['input_source']})."},
        {"Item": "Arm 2 rule", "Detail": "A gene is prioritized if it has lab evidence with HER2 in keenable/her2_interactors_experimental.md "
                                         "AND is GI high or middle tier in genomic_intelligence/her2_genes_dna_context_ranking.csv. ERBB2 itself is excluded."},
        {"Item": "Better match", "Detail": "A trial is a better match when one of its extra markers is a prioritized gene. "
                                           "'Confirmed' = that gene is mutated in the patient's genome input; 'candidate' = not reported yet, so test it."},
        {"Item": "Excluded by the GI rule", "Detail": "ESR1 and PGR have Keenable lab evidence but are GI low tier, so they do not pass. They are also protein "
                                                      "status markers (ER/PR by IHC), which a genome cannot show; arm 1 lists them as 'not in genome data'."},
        {"Item": "Limits", "Detail": "GI scores are DNA-context predictions from the reference genome, not HER2-specific and not patient data. "
                                     "Trial statuses come from the trials spreadsheet; confirm on ClinicalTrials.gov. Research prototype, not medical advice."},
    ]
    _sheet(wb, "Notes", notes)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patient", type=Path, default=PATIENT)
    ap.add_argument("--mutated-genes", nargs="*", help="override the genome's mutated genes (demo)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)

    patient = load_patient(a.patient, a.mutated_genes)
    trials = load_trials(TRIALS_XLSX)
    keen, gi = load_keenable(KEENABLE_MD), load_gi(GI_CSV)
    known = set(keen) | set(gi)

    a1 = arm1(patient, trials, known)
    genes = prioritize_genes(patient, keen, gi)
    a2 = arm2(patient, trials, genes, a1, known)

    write_arm1(a1, a.out_dir / ARM1_CSV.name)
    write_arm2(a2, genes, patient, a.out_dir / ARM2_XLSX.name)

    pri = [g["gene"] for g in genes if g["passes_rule"] == "yes"]
    print(f"Patient {patient['patient_id']}: HER2 {patient['her2_status']}; genome genes: {', '.join(patient['mutated_genes']) or 'none'}")
    print(f"Arm 1: {sum(r['her2_match'] == 'yes' for r in a1)}/{len(a1)} trials match on HER2 -> {a.out_dir / ARM1_CSV.name}")
    print(f"Arm 2: {len(pri)} prioritized genes ({', '.join(pri)}); "
          f"mutated in patient: {', '.join(g['gene'] for g in genes if g['priority'].startswith('1')) or 'none'}")
    print(f"Arm 2: {len(a2)} better-matched trials -> {a.out_dir / ARM2_XLSX.name}")
    for r in a2:
        print(f"  {r['Arm 2 rank']}. {r['NCT ID']} [{r['Match level']}] genes={r['Matched candidate gene(s)']} (arm 1 position {r['Arm 1 position']})")


if __name__ == "__main__":
    main()
