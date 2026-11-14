#!/usr/bin/env python3
"""
Pull lung, breast, colon and stomach cancer studies from ClinicalTrials.gov (API v2)
into a trial-operations schema, one JSON record per study (JSONL) plus a flat CSV.

Usage:
    python pull_trial_ops.py                # open studies only
    python pull_trial_ops.py --all          # every status
    python pull_trial_ops.py --interventional
"""
import argparse, csv, json, re, time, urllib.parse, urllib.request

API = "https://clinicaltrials.gov/api/v2/studies"
OPEN = "RECRUITING|ENROLLING_BY_INVITATION|AVAILABLE"
CANCERS = {
    # "lung": "lung cancer OR non-small cell lung cancer OR small cell lung cancer",
    "breast": "breast cancer",
    # "colon": "colon cancer OR colorectal cancer",
    # "stomach": "stomach cancer OR gastric cancer OR gastroesophageal junction cancer",
}
# Module names: restricts the response to the sections we need
MODULES = ("IdentificationModule|StatusModule|ConditionsModule|DesignModule|"
           "ArmsInterventionsModule|EligibilityModule|ContactsLocationsModule|"
           "DocumentSection")

# ---- Heuristic tagging for fields the registry has no structured slot for ----
BIOMARKERS = {
    "EGFR": r"\bEGFR\b", "ALK": r"\bALK\b", "ROS1": r"\bROS1\b", "KRAS": r"\bKRAS\b",
    "BRAF": r"\bBRAF\b", "MET": r"\bMET\b", "RET": r"\bRET\b", "NTRK": r"\bNTRK\b",
    "HER2": r"\bHER2\b|\bERBB2\b", "ER/PR": r"\bhormone receptor\b|\bER[- ]positive\b|\bPR[- ]positive\b|\bHR[+-]",
    "TNBC": r"triple[- ]negative", "BRCA": r"\bBRCA\s?[12]?\b", "PIK3CA": r"\bPIK3CA\b",
    "PD-L1": r"\bPD-?L1\b", "MSI/dMMR": r"\bMSI-?H\b|\bdMMR\b|microsatellite", "CLDN18.2": r"\bCLDN ?18\.?2\b|claudin ?18",
    "TMB": r"\bTMB\b|tumou?r mutational burden", "ctDNA": r"\bctDNA\b|circulating tumou?r DNA",
    "ESR1": r"\bESR1\b", "TNBC": r"\bTNBC\b", "BRCA": r"\bBRCA\b", "PIK3CA": r"\bPIK3CA\b"
}
SPECIMENS = {
    "archival_tissue": r"archival|archived|formalin|\bFFPE\b|paraffin",
    "fresh_biopsy": r"fresh (tumou?r )?(biopsy|tissue)|new(ly obtained)? biopsy|baseline biopsy|mandatory biopsy",
    "tumor_tissue": r"tumou?r (tissue|sample|specimen)",
    "blood": r"\bblood (sample|draw)|plasma|\bliquid biopsy\b",
    "bone_marrow": r"bone marrow",
}


def tag(text, patterns):
    return sorted(k for k, p in patterns.items() if re.search(p, text or "", re.I))


def split_criteria(text):
    """Return (inclusion_list, exclusion_list) from the free-text eligibility blob."""
    text = text or ""
    inc_m = re.search(r"inclusion criteria\s*:?", text, re.I)
    exc_m = re.search(r"exclusion criteria\s*:?", text, re.I)
    if inc_m and exc_m and inc_m.start() < exc_m.start():
        inc, exc = text[inc_m.end():exc_m.start()], text[exc_m.end():]
    elif inc_m and not exc_m:
        inc, exc = text[inc_m.end():], ""
    elif exc_m and not inc_m:
        inc, exc = "", text[exc_m.end():]
    else:
        inc, exc = text, ""  # unstructured: leave in inclusion for manual review

    def bullets(block):
        # Split on bullet markers / numbered items at line starts
        parts = re.split(r"\n\s*(?:[*\-•]|\d+[.)])\s+", "\n" + block.strip())
        return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    return bullets(inc), bullets(exc)


def doc_links(ps, nct):
    docs = ps.get("documentSection", {}).get("largeDocumentModule", {}).get("largeDocs", [])
    return [{"type": d.get("typeAbbrev", ""), "label": d.get("label", ""),
             "url": f"https://cdn.clinicaltrials.gov/large-docs/{nct[-2:]}/{nct}/{d['filename']}"}
            for d in docs if d.get("filename")]


def flatten(study):
    ps = study.get("protocolSection", {})
    ident, status = ps.get("identificationModule", {}), ps.get("statusModule", {})
    design, cond = ps.get("designModule", {}), ps.get("conditionsModule", {})
    arms, elig = ps.get("armsInterventionsModule", {}), ps.get("eligibilityModule", {})
    nct = ident.get("nctId", "")
    crit = elig.get("eligibilityCriteria", "")
    inc, exc = split_criteria(crit)
    docs = doc_links(study, nct) if "documentSection" in study else doc_links(ps, nct)
    protocol_docs = [d for d in docs if d["type"].lower() in ("prot", "prot_sap", "prot_icf")]
    return {
        "nct_id": nct,
        "title": ident.get("briefTitle", ""),
        "official_title": ident.get("officialTitle", ""),
        "therapeutic_area": cond.get("conditions", []),
        "keywords": cond.get("keywords", []),
        "interventions": [{"name": i.get("name"), "type": i.get("type")}
                          for i in arms.get("interventions", [])],
        "phase": design.get("phases", []),
        "recruitment_status": status.get("overallStatus", ""),
        "age_min": elig.get("minimumAge", ""),
        "age_max": elig.get("maximumAge", ""),
        "age_groups": elig.get("stdAges", []),
        "sex": elig.get("sex", ""),
        "healthy_volunteers": elig.get("healthyVolunteers"),
        "inclusion_criteria": inc,
        "exclusion_criteria": exc,
        "eligibility_raw": crit,
        "locations": [{"facility": l.get("facility"), "city": l.get("city"),
                       "state": l.get("state"), "country": l.get("country"),
                       "status": l.get("status")}
                      for l in ps.get("contactsLocationsModule", {}).get("locations", [])],
        # Not structured in the registry: heuristic tags from text, verify before use
        "biomarker_requirements": tag(crit + " " + ident.get("officialTitle", "")
                                      + " ".join(cond.get("keywords", [])), BIOMARKERS),
        "specimen_requirements": tag(crit, SPECIMENS),
        # Visit schedule is only in an uploaded protocol document, when one exists
        "visit_schedule": None,
        "protocol_documents": protocol_docs,
        "url": f"https://clinicaltrials.gov/study/{nct}",
    }


def fetch(params):
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "trial-ops-pull"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def pull(key, term, all_status, interventional):
    p = {"query.cond": term, "pageSize": 500, "countTotal": "true", "fields": MODULES}
    if not all_status:
        p["filter.overallStatus"] = OPEN
    if interventional:
        p["query.term"] = "AREA[StudyType]INTERVENTIONAL"
    rows, token, first = [], None, True
    while True:
        if token:
            p["pageToken"] = token
        d = fetch(p)
        if first:
            print(f"[{key}] {d.get('totalCount')} studies matched"); first = False
        for s in d.get("studies", []):
            r = flatten(s); r["cancer_group"] = [key]; rows.append(r)
        token = d.get("nextPageToken")
        if not token:
            return rows
        time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--interventional", action="store_true")
    ap.add_argument("--out", default="trial_ops")
    ap.add_argument("--cancers", nargs="+", choices=list(CANCERS), default=list(CANCERS),
                    help="which cancer groups to pull, e.g. --cancers breast")
    a = ap.parse_args()

    merged = {}
    for k, t in ((k, CANCERS[k]) for k in a.cancers):
        for r in pull(k, t, a.all, a.interventional):
            if r["nct_id"] in merged:
                merged[r["nct_id"]]["cancer_group"].append(k)
            else:
                merged[r["nct_id"]] = r

    with open(a.out + ".jsonl", "w", encoding="utf-8") as f:
        for r in merged.values():
            f.write(json.dumps(r) + "\n")

    j = lambda v: "; ".join(map(str, v)) if isinstance(v, list) else v
    flat_cols = ["nct_id", "cancer_group", "title", "therapeutic_area", "phase", "recruitment_status",
                 "age_min", "age_max", "sex", "biomarker_requirements", "specimen_requirements", "url"]
    with open(a.out + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(flat_cols + ["n_locations", "countries", "n_inclusion", "n_exclusion", "has_protocol_doc"])
        for r in merged.values():
            w.writerow([j(r[c]) for c in flat_cols] + [
                len(r["locations"]), "; ".join(sorted({l["country"] for l in r["locations"] if l["country"]})),
                len(r["inclusion_criteria"]), len(r["exclusion_criteria"]), bool(r["protocol_documents"])])
    print(f"Wrote {len(merged)} studies to {a.out}.jsonl and {a.out}.csv")


if __name__ == "__main__":
    main()
