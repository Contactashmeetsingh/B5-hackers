#!/usr/bin/env python3
"""
Extract structured eligibility from ClinicalTrials.gov criteria text using Claude.

Input : trial_ops.jsonl   (from pull_trial_ops.py)
Output: extracted.jsonl   (one structured record per study; resumable)

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python extract_criteria.py                       # all studies, default model
    python extract_criteria.py --limit 50            # test on a small sample first
    python extract_criteria.py --model claude-sonnet-5-5 --workers 4
"""
import argparse, hashlib, json, os, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic

DEFAULT_MODEL = "claude-haiku-5-5"  # cheap first pass; use sonnet for harder/oncology-dense text

SYSTEM = """You convert clinical trial eligibility text into structured data for patient-trial matching.

Rules:
- Extract ONLY what the text states. Never infer or use outside knowledge about the drug or trial.
- If a dimension is not addressed, use "unspecified" (or an empty list). Do not guess.
- Distinguish carefully: a biomarker that is REQUIRED vs one that is EXCLUDED vs merely mentioned.
  Example: "no prior EGFR TKI" is an exclusion on prior therapy, not an EGFR mutation requirement.
- Preserve numeric thresholds and units exactly (e.g. "ANC >= 1.5 x 10^9/L", "washout 21 days").
- Break the criteria into atomic items in `atomic_criteria`; each item must be one checkable condition.
- Add anything ambiguous or too vague to verify (e.g. "adequate organ function") to `ambiguities`."""

TOOL = {
    "name": "record_eligibility",
    "description": "Record the structured eligibility criteria for one trial.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cancer_types": {"type": "array", "items": {"type": "string"},
                             "description": "Cancer types/histologies explicitly eligible, e.g. NSCLC adenocarcinoma"},
            "stage_setting": {"type": "array", "items": {"type": "string", "enum": [
                "early_stage_resectable", "locally_advanced", "metastatic_or_recurrent", "unspecified"]}},
            "performance_status": {"type": "object", "properties": {
                "scale": {"type": "string", "enum": ["ECOG", "Karnofsky", "Lansky", "WHO", "unspecified"]},
                "max_allowed": {"type": ["number", "null"]},
                "text": {"type": "string"}}, "required": ["scale"]},
            "line_of_therapy": {"type": "string", "enum": [
                "treatment_naive", "first_line", "second_line_or_later", "after_progression_on_specified",
                "adjuvant", "neoadjuvant", "any", "unspecified"]},
            "required_prior_therapy": {"type": "array", "items": {"type": "string"}},
            "excluded_prior_therapy": {"type": "array", "items": {"type": "string"}},
            "biomarkers": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"},
                "requirement": {"type": "string", "enum": ["required_positive", "required_negative", "excluded", "either_allowed"]},
                "detail": {"type": "string", "description": "variant, cutoff, assay, e.g. 'exon 19 del or L858R', 'PD-L1 TPS >= 50%'"}},
                "required": ["name", "requirement"]}},
            "specimens": {"type": "array", "items": {"type": "object", "properties": {
                "type": {"type": "string"},
                "requirement": {"type": "string", "enum": ["mandatory", "optional", "unspecified"]},
                "detail": {"type": "string"}}, "required": ["type", "requirement"]}},
            "measurable_disease_required": {"type": "string", "enum": ["yes", "no", "unspecified"]},
            "brain_metastases": {"type": "string", "enum": [
                "not_allowed", "allowed_if_treated_and_stable", "allowed", "unspecified"]},
            "lab_thresholds": {"type": "array", "items": {"type": "object", "properties": {
                "test": {"type": "string"}, "criterion": {"type": "string"}}, "required": ["test", "criterion"]}},
            "comorbidity_exclusions": {"type": "array", "items": {"type": "string"}},
            "medication_exclusions": {"type": "array", "items": {"type": "string"}},
            "pregnancy_contraception_required": {"type": "string", "enum": ["yes", "no", "unspecified"]},
            "life_expectancy_min": {"type": "string"},
            "atomic_criteria": {"type": "array", "items": {"type": "object", "properties": {
                "text": {"type": "string"},
                "type": {"type": "string", "enum": ["inclusion", "exclusion"]},
                "category": {"type": "string", "enum": [
                    "diagnosis", "stage", "biomarker", "prior_therapy", "performance_status", "lab",
                    "comorbidity", "medication", "disease_status", "demographic", "procedure_specimen", "other"]}},
                "required": ["text", "type", "category"]}},
            "ambiguities": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["cancer_types", "stage_setting", "performance_status", "line_of_therapy",
                     "biomarkers", "atomic_criteria", "ambiguities"],
    },
}

write_lock = threading.Lock()


def crit_hash(rec):
    return hashlib.sha256(rec["eligibility_raw"].encode()).hexdigest()[:16]


def extract_one(client, model, rec):
    user = (f"Trial: {rec['nct_id']}\nTitle: {rec.get('official_title') or rec['title']}\n"
            f"Conditions: {'; '.join(rec.get('therapeutic_area', []))}\n"
            f"Phase: {'; '.join(rec.get('phase', []))}\n"
            f"Stated age: {rec.get('age_min','')} to {rec.get('age_max','')}; sex: {rec.get('sex','')}\n\n"
            f"ELIGIBILITY CRITERIA TEXT:\n{rec['eligibility_raw']}")
    resp = client.messages.create(
        model=model, max_tokens=4000, system=SYSTEM,
        tools=[TOOL], tool_choice={"type": "tool", "name": "record_eligibility"},
        messages=[{"role": "user", "content": user}],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    return {"nct_id": rec["nct_id"], "criteria_hash": crit_hash(rec), "model": model,
            "extracted": block.input,
            "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default="trial_ops.jsonl")
    ap.add_argument("--out", default="extracted.jsonl")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()

    # Resume: skip studies already extracted with identical criteria text
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            for line in f:
                d = json.loads(line); done.add((d["nct_id"], d["criteria_hash"]))

    todo = []
    with open(a.inp) as f:
        for line in f:
            r = json.loads(line)
            if r.get("eligibility_raw", "").strip() and (r["nct_id"], crit_hash(r)) not in done:
                todo.append(r)
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} studies to extract ({len(done)} already done)")

    client = anthropic.Anthropic(max_retries=5)
    n_ok = n_err = tin = tout = 0
    with open(a.out, "a", encoding="utf-8") as out, ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(extract_one, client, a.model, r): r["nct_id"] for r in todo}
        for fut in as_completed(futs):
            try:
                res = fut.result()
                with write_lock:
                    out.write(json.dumps(res) + "\n"); out.flush()
                n_ok += 1; tin += res["usage"]["in"]; tout += res["usage"]["out"]
            except Exception as e:
                n_err += 1; print(f"  ! {futs[fut]}: {e}")
            if (n_ok + n_err) % 50 == 0:
                print(f"  {n_ok + n_err}/{len(todo)} done ({n_err} errors)")
    print(f"Finished: {n_ok} ok, {n_err} errors. Tokens in={tin:,} out={tout:,}")


if __name__ == "__main__":
    main()
