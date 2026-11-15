"""Thin ClinicalTrials.gov API v2 wrapper: search studies, map each one to a Trial row.

Used once to take the stage 5 snapshot (AGENTS.md section 6); the demo itself
never calls it. Only backend/pipeline/trials.py imports this, and only with --refresh.

API docs: https://clinicaltrials.gov/data-api/api
"""

from __future__ import annotations

import html
import re
import time
from typing import Optional

import httpx

from backend.schemas import Trial

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_PAGE_URL = "https://clinicaltrials.gov/study/{nct_id}"
SNAPSHOT_SOURCE = "clinicaltrials.gov snapshot"
TIMEOUT_S = 30.0
MAX_RETRIES = 4
MAX_PAGE_SIZE = 1000  # API maximum


class ClinicalTrialsError(RuntimeError):
    pass


def _get(client: httpx.Client, params: dict) -> dict:
    """GET one page of studies, backing off on rate limits and server errors."""
    for attempt in range(MAX_RETRIES):
        r = client.get(STUDIES_URL, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(2 ** attempt, 10))
            continue
        if r.status_code >= 400:
            raise ClinicalTrialsError(f"ClinicalTrials.gov returned {r.status_code}: {r.text[:200]}")
        return r.json()
    raise ClinicalTrialsError(f"ClinicalTrials.gov kept failing after {MAX_RETRIES} attempts")


def _format_phase(phases: list[str]) -> str:
    # API enum values: EARLY_PHASE1, PHASE1 .. PHASE4, NA. Shown as "Phase 1/Phase 2".
    pretty = {"NA": "N/A", "EARLY_PHASE1": "Early Phase 1"}
    return "/".join(pretty.get(p, p.replace("PHASE", "Phase ")) for p in phases)


_MD_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>&^~|=])")


def _plain(text: str) -> str:
    """The API returns eligibility as backslash-escaped Markdown with HTML entities
    ('HER2\\-negative', 'ratio \\&lt;2'). Unescape so stored text is readable and the
    stage 6 regexes see a plain '-'."""
    return html.unescape(_MD_ESCAPE.sub(r"\1", text or ""))


def to_trial(study: dict) -> Trial:
    """Map one API v2 study object to the Trial contract row."""
    ps = study.get("protocolSection", {})
    nct_id = ps["identificationModule"]["nctId"]
    interventions = ps.get("armsInterventionsModule", {}).get("interventions", [])
    return Trial(
        nct_id=nct_id,
        title=ps["identificationModule"].get("briefTitle", ""),
        phase=_format_phase(ps.get("designModule", {}).get("phases", [])),
        status=ps.get("statusModule", {}).get("overallStatus", ""),
        url=STUDY_PAGE_URL.format(nct_id=nct_id),
        conditions=ps.get("conditionsModule", {}).get("conditions", []),
        interventions=[i["name"] for i in interventions if i.get("name")],
        eligibility_text=_plain(ps.get("eligibilityModule", {}).get("eligibilityCriteria", "")),
        source=SNAPSHOT_SOURCE,
    )


def fetch_studies(
    query_cond: str,
    query_term: str,
    page_size: int = 100,
    max_studies: int = 200,
    overall_status: Optional[list[str]] = None,
) -> list[Trial]:
    """Search studies (query.cond + query.term), following nextPageToken up to max_studies.

    overall_status, if given, filters by recruitment status (e.g. ["RECRUITING"]).
    """
    params: dict = {
        "query.cond": query_cond,
        "query.term": query_term,
        "pageSize": min(page_size, max_studies, MAX_PAGE_SIZE),
        "format": "json",
    }
    if overall_status:
        params["filter.overallStatus"] = ",".join(overall_status)

    trials: list[Trial] = []
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=True) as client:
        while len(trials) < max_studies:
            page = _get(client, params)
            trials.extend(to_trial(s) for s in page.get("studies", []))
            token = page.get("nextPageToken")
            if not token:
                break
            params["pageToken"] = token
    return trials[:max_studies]
