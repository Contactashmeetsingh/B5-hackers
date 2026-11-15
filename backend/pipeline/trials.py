"""Stage 3: the hard-coded clinical trial list (data/cache/trials.json), Approach 1.

The trial list for the PoC is the team's curated spreadsheet
clinical_trials/her2_candidate_marker_open_trials.xlsx (sheet "Open HER2 trials",
7 open HER2-positive trials). No live search in the demo.

  python -m backend.pipeline.trials             # use the cache; import the spreadsheet if there is none
  python -m backend.pipeline.trials --refresh   # re-import the spreadsheet (local file, no network)
  python -m backend.pipeline.trials --ctgov     # optional: a ClinicalTrials.gov snapshot instead (not used by the demo)

Spreadsheet column -> Trial field (columns are found by header name, not position):
  NCT ID -> nct_id, Trial -> title, Phase -> phase ("Phase 3"), Link -> url,
  What the trial requires -> eligibility_text (the only criteria text we have),
  Status (as of DATE) -> status (text before the first ";" or "("), status_detail (all of it), status_as_of,
  Sponsor -> sponsor, Marker(s) from your list -> curated_markers (the curator's note; matching does not use it).
The sheet has no conditions or interventions columns, so those stay empty and stage 4
finds drugs in the title. The Notes sheet's "Data caveat" row is attached to every
trial as status_caveat. A spreadsheet with no NCT IDs, or none that look like
NCT########, is an error: we never write half a trial list.

A mock list (MOCK-NCT-000n, source "mock") is written only when neither a cache nor
the spreadsheet exists.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx

from backend import config
from backend.clients import clinicaltrials
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import MOCK, Biomarker, Trial
from backend.store import read_rows, write_rows

SPREADSHEET_SOURCE = "curated spreadsheet"
NCT_ID = re.compile(r"^NCT\d{8}$")

# Snapshot settings live in backend/config.py.
CONDITION_TEMPLATE = config.TRIALS_CONDITION_TEMPLATE
SNAPSHOT_PAGE_SIZE = config.TRIALS_PAGE_SIZE
SNAPSHOT_MAX_STUDIES = config.TRIALS_MAX_STUDIES
SNAPSHOT_STATUSES = config.TRIALS_STATUSES


# ---------------------------------------------------------------- spreadsheet
_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_T = f"{{{_NS['m']}}}t"


def read_xlsx_sheet(path: Path, sheet_name: str) -> list[dict[str, str]]:
    """Rows of one worksheet as {header: value} dicts, using only the standard library.

    Handles shared strings and inline strings; formulas give their cached value.
    Blank rows are skipped. Raises KeyError if the sheet does not exist.
    """
    with zipfile.ZipFile(path) as z:
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        rid = next((s.get(f"{{{_NS['r']}}}id") for s in workbook.iterfind("m:sheets/m:sheet", _NS)
                    if s.get("name") == sheet_name), None)
        if rid is None:
            raise KeyError(f"{path.name} has no sheet named {sheet_name!r}")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        target = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(_T)) for si in sst.iterfind("m:si", _NS)]
        sheet = ET.fromstring(z.read(target))

    rows: list[dict[str, str]] = []
    for row in sheet.iterfind("m:sheetData/m:row", _NS):
        cells: dict[str, str] = {}
        for i, c in enumerate(row.iterfind("m:c", _NS)):
            ref = re.match(r"[A-Z]+", c.get("r", ""))  # "r" is optional in the spec: fall back to position
            col = ref.group() if ref else _column_letter(i)
            kind = c.get("t")
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(_T))
            elif kind == "s":
                value = shared[int(c.findtext("m:v", "0", _NS))]
            else:
                value = c.findtext("m:v", "", _NS)
            cells[col] = value.strip()
        if any(cells.values()):
            rows.append(cells)
    if not rows:
        return []
    header = rows[0]
    return [{header[col]: r.get(col, "") for col in header} for r in rows[1:]]


def _column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _column(row: dict[str, str], prefix: str) -> str:
    """Value of the first column whose header starts with `prefix` (case-insensitive)."""
    for header, value in row.items():
        if header.lower().startswith(prefix.lower()):
            return value
    return ""


def _status_as_of(row: dict[str, str]) -> str:
    for header in row:
        m = re.search(r"as of (\d{4}-\d{2}-\d{2})", header)
        if header.lower().startswith("status") and m:
            return m.group(1)
    return ""


def _data_caveat(path: Path) -> str:
    try:
        notes = read_xlsx_sheet(path, config.TRIALS_NOTES_SHEET)
    except KeyError:
        return ""
    return next((_column(n, "Detail") for n in notes if _column(n, "Category").lower() == "data caveat"), "")


def import_spreadsheet(path: Path) -> list[Trial]:
    rows = read_xlsx_sheet(path, config.TRIALS_SHEET)
    caveat = _data_caveat(path)
    trials, bad = [], []
    for row in rows:
        nct = _column(row, "NCT ID")
        if not NCT_ID.match(nct):
            bad.append(nct or "(empty)")
            continue
        phase = _column(row, "Phase")
        status_full = _column(row, "Status")
        trials.append(Trial(
            nct_id=nct,
            title=_column(row, "Trial"),
            phase=phase if not phase or phase.lower().startswith("phase") else f"Phase {phase}",
            status=re.split(r"[;(]", status_full)[0].strip(),
            url=_column(row, "Link"),
            conditions=[],
            interventions=[],
            eligibility_text=_column(row, "What the trial requires"),
            source=SPREADSHEET_SOURCE,
            sponsor=_column(row, "Sponsor"),
            curated_markers=_column(row, "Marker"),
            status_detail=status_full,
            status_as_of=_status_as_of(row),
            status_caveat=caveat,
        ))
    if bad:
        raise ValueError(f"{path.name}: rows without a valid NCT ID: {bad}")
    if not trials:
        raise ValueError(f"{path.name}: sheet {config.TRIALS_SHEET!r} has no trials")
    return trials


# ---------------------------------------------------------------- ClinicalTrials.gov (optional)
def build_query(bm: Biomarker) -> tuple[str, str]:
    """(query.cond, query.term) for the biomarker, e.g. ("Breast Cancer", '"HER2" OR "ERBB2" OR ...')."""
    terms: list[str] = []
    for t in [bm.biomarker, bm.gene, *bm.aliases]:
        if t.lower() not in {x.lower() for x in terms}:  # the API search is case-insensitive
            terms.append(t)
    return CONDITION_TEMPLATE.format(tissue=bm.tissue), " OR ".join(f'"{t}"' for t in terms)


def mock_trials(bm: Biomarker) -> list[Trial]:
    """A small, obviously fake snapshot shaped to exercise every branch of trial matching.

    IDs are "MOCK-NCT-000n" so they can never be mistaken for real NCT numbers, and
    no URL is given so the dashboard cannot link to a real study by accident.
    """
    b, cond = bm.biomarker, CONDITION_TEMPLATE.format(tissue=bm.tissue)
    tissue = bm.tissue.lower()
    excl = "Exclusion Criteria:\n* Illustrative mock exclusion criterion."

    def row(n: int, title: str, phase: str, interventions: list[str], inclusion: list[str]) -> Trial:
        incl = "\n".join(f"* {line}" for line in inclusion)
        return Trial(
            nct_id=f"MOCK-NCT-{n:04d}",
            title=f"[MOCK] {title}",
            phase=phase,
            status="RECRUITING",
            url="",
            conditions=[cond],
            interventions=interventions,
            eligibility_text=f"Illustrative mock criteria only.\nInclusion Criteria:\n{incl}\n{excl}",
            source=MOCK,
        )

    return [
        # biomarker required + a second targeted drug (alpelisib -> PIK3CA via drug_targets.json)
        row(1, f"Trastuzumab plus alpelisib in {b}-positive, PIK3CA-mutant {tissue} cancer", "Phase 2",
            ["trastuzumab", "alpelisib"],
            [f"{b}-positive disease (IHC 3+ or ISH amplified)", "PIK3CA mutation on tumour testing"]),
        # biomarker-low requirement, no extra genes
        row(2, f"Trastuzumab deruxtecan in {b}-low {tissue} cancer", "Phase 3",
            ["trastuzumab deruxtecan"],
            [f"{b}-low disease (IHC 1+, or IHC 2+ with negative ISH)"]),
        # endocrine therapy arm; ESR1 named in eligibility
        row(3, f"Endocrine therapy plus {b}-targeted antibody in ER-positive, {b}-positive {tissue} cancer",
            "Phase 2", ["fulvestrant", "trastuzumab"],
            [f"Estrogen receptor positive and {b}-positive disease", "ESR1 mutation status known"]),
        # extra genes named only in eligibility
        row(4, f"Dual antibody blockade with a tissue biomarker sub-study in {b}-amplified {tissue} cancer",
            "Phase 2", ["pertuzumab", "trastuzumab"],
            [f"{b} gene amplification by ISH", "Tumour tissue available for ERBB3 and GRB7 testing"]),
        # biomarker required, nothing else
        row(5, f"Tucatinib in previously treated {b}-positive metastatic {tissue} cancer", "Phase 2",
            ["tucatinib"],
            [f"{b}-positive disease by local testing"]),
        # biomarker only mentioned, not required; one extra gene
        row(6, f"Supervised exercise programme for people with {tissue} cancer", "N/A",
            ["Supervised exercise programme"],
            [f"Any hormone receptor or {b} status", "Optional archival tissue for PTEN testing"]),
    ]


def _ctgov_snapshot(bm: Biomarker, path: Path) -> list[Trial]:
    cond, term = build_query(bm)
    try:
        trials = clinicaltrials.fetch_studies(cond, term, SNAPSHOT_PAGE_SIZE, SNAPSHOT_MAX_STUDIES, SNAPSHOT_STATUSES)
        if not trials:
            raise clinicaltrials.ClinicalTrialsError(f"no studies for cond={cond!r} term={term!r}")
        return trials
    except (httpx.HTTPError, clinicaltrials.ClinicalTrialsError) as exc:
        # Never replace a trial list we already have with a mock (AGENTS.md section 6: keep going).
        print(f"[trials] ClinicalTrials.gov snapshot failed ({exc}); keeping the existing list")
        if path.exists():
            return read_rows(path, Trial)
        if config.TRIALS_SPREADSHEET_PATH.exists():
            return import_spreadsheet(config.TRIALS_SPREADSHEET_PATH)
        return mock_trials(bm)


def run(refresh: bool = False, ctgov: bool = False) -> list[Trial]:
    path = config.TRIALS_PATH
    if path.exists() and not (refresh or ctgov):
        return read_rows(path, Trial)

    bm = load_biomarker(config.BIOMARKER_PATH)
    if ctgov:
        trials = _ctgov_snapshot(bm, path)
    elif config.TRIALS_SPREADSHEET_PATH.exists():
        trials = import_spreadsheet(config.TRIALS_SPREADSHEET_PATH)
    elif path.exists():
        print(f"[trials] {config.TRIALS_SPREADSHEET_PATH.name} not found; keeping the existing cache")
        return read_rows(path, Trial)
    else:
        trials = mock_trials(bm)

    write_rows(path, trials)
    return trials


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 3: the hard-coded clinical trial list")
    ap.add_argument("--refresh", action="store_true", help="re-import the curated spreadsheet")
    ap.add_argument("--ctgov", action="store_true", help="take a ClinicalTrials.gov snapshot instead (not used by the demo)")
    args = ap.parse_args()
    rows = run(refresh=args.refresh, ctgov=args.ctgov)
    print(f"[trials] {len(rows)} trials ({sum(t.is_mock for t in rows)} mock) -> {config.TRIALS_PATH}")
