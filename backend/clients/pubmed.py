"""Thin wrapper for PubMed (NCBI E-utilities efetch), used by stage 1 to check Keenable hits.

Keenable finds papers; PubMed is the record. For each new PMID we read the PubMed title,
publication year, publication types and abstract. The abstract is used only to spot gene
names and biomarker status (e.g. "HER2-negative") and is never stored or returned to
the API (AGENTS.md: no copied abstracts).

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25499/ . No key needed: NCBI allows 3
requests per second without one. We send only PMIDs, in batches, with a generic tool name.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Iterable, Optional

import httpx

from backend import config

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedError(RuntimeError):
    pass


def _text(el: Optional[ET.Element]) -> str:
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def _year(article: ET.Element) -> Optional[int]:
    pub = article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate")
    if pub is None:
        return None
    raw = pub.findtext("Year") or pub.findtext("MedlineDate") or ""
    return int(raw[:4]) if raw[:4].isdigit() else None


def parse_efetch(xml: bytes) -> dict[str, dict]:
    """PMID -> {title, year, publication_types, abstract} from an efetch XML reply."""
    out: dict[str, dict] = {}
    for art in ET.fromstring(xml).iterfind("PubmedArticle"):
        pmid = art.findtext("./MedlineCitation/PMID")
        if not pmid:
            continue
        a = art.find("./MedlineCitation/Article")
        out[pmid] = {
            "title": _text(a.find("ArticleTitle")) if a is not None else "",
            "year": _year(art),
            "publication_types": [_text(p) for p in art.iterfind(".//PublicationTypeList/PublicationType")],
            "abstract": " ".join(_text(t) for t in art.iterfind(".//Abstract/AbstractText")),
        }
    return out


def fetch_records(pmids: Iterable[str]) -> dict[str, dict]:
    """PubMed records for the given PMIDs. A PMID PubMed does not know is simply absent."""
    ids = [p for p in dict.fromkeys(pmids) if p.isdigit()]
    out: dict[str, dict] = {}
    for i in range(0, len(ids), config.PUBMED_BATCH):
        batch = ids[i:i + config.PUBMED_BATCH]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml", "tool": config.PUBMED_TOOL}
        for attempt in range(config.PUBMED_MAX_RETRIES + 1):
            try:
                r = httpx.get(EFETCH, params=params, timeout=config.PUBMED_TIMEOUT_S)
                if r.status_code == 200:
                    out.update(parse_efetch(r.content))
                    break
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise PubMedError(f"efetch HTTP {r.status_code}")
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == config.PUBMED_MAX_RETRIES:
                    raise PubMedError(f"efetch network error: {type(exc).__name__}") from exc
            if attempt == config.PUBMED_MAX_RETRIES:
                raise PubMedError("efetch retries exhausted")
            time.sleep(1.0 + attempt)
        time.sleep(config.PUBMED_PAUSE_S)  # stay under 3 requests per second
    return out
