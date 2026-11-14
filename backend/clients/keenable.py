"""Thin wrapper for Keenable web search (stage 1, Approach 1).

Docs: https://docs.keenable.ai (llms.txt, api-reference/search.md). Base URL
https://api.keenable.ai.

* No key (the default): POST /v1/search/public, with an X-Keenable-Title header
  naming the calling app (generic name below, never anything personal). Limited
  to 1,000 requests per hour per IP; no credits are charged.
* With KEENABLE_API_KEY in .env: POST /v1/search with an X-API-Key header.

Keenable is a web search engine. It returns ranked pages (title, url, snippet,
published_at), not structured gene mentions and not a gene targets dataset, so
gene parsing happens in the pipeline (backend/pipeline/literature.py).

Keenable logs keyless queries. Only send generic biomedical queries built from the
profile (e.g. "HER2 positive and PIK3CA mutated breast cancer"), never personal data.

Errors: 429 waits for Retry-After and retries; 5xx and timeouts retry with backoff;
402 (out of credits) and every other 4xx raise KeenableError at once.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

import httpx

from backend import config  # importing config also loads .env

PUBMED_URL = re.compile(r"^https?://(?:www\.)?pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?(?:[?#].*)?$")
TITLE_SUFFIX = re.compile(r"\s+[-|]\s+PubMed\s*$", re.IGNORECASE)


class KeenableError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"[{status}] {message}")
        self.status = status


class KeenableClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = config.KEENABLE_BASE_URL,
        timeout_s: float = config.KEENABLE_TIMEOUT_S,
        max_retries: int = config.KEENABLE_MAX_RETRIES,
    ):
        # Read from the environment (.env). Never print or log the key.
        self._api_key = api_key or config.KEENABLE_API_KEY
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_retries = max_retries

    @property
    def has_key(self) -> bool:
        return self._api_key is not None

    def __repr__(self) -> str:  # keep the key out of tracebacks and logs
        return f"KeenableClient(has_key={self.has_key})"

    # ------------------------------------------------------------ raw search
    def search(self, query: str, *, site: Optional[str] = None, max_results: int = 10,
               mode: Optional[str] = None) -> dict[str, Any]:
        """One search call. Returns Keenable's JSON: {query, mode, results: [...]}."""
        body: dict[str, Any] = {"query": query, "max_results": max_results}
        if site:
            body["site"] = site
        if mode:
            body["mode"] = mode
        if self.has_key:
            url, headers = f"{self._base_url}/v1/search", {"X-API-Key": self._api_key}
        else:
            url, headers = f"{self._base_url}/v1/search/public", {"X-Keenable-Title": config.KEENABLE_APP_TITLE}

        delay = 2.0
        for attempt in range(self._max_retries + 1):
            last = attempt == self._max_retries
            try:
                r = httpx.post(url, json=body, headers=headers, timeout=self._timeout_s)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if last:
                    raise KeenableError(0, f"network error: {type(exc).__name__}") from exc
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 and not last:
                time.sleep(min(float(r.headers.get("Retry-After", delay) or delay), config.KEENABLE_BACKOFF_CAP_S))
                continue
            if r.status_code >= 500 and not last:
                time.sleep(delay)
                delay *= 2
                continue
            # 402 = out of credits (do not retry), other 4xx = our request is wrong.
            raise KeenableError(r.status_code, r.text[:300])
        raise KeenableError(0, "retries exhausted")  # pragma: no cover

    # ------------------------------------------------------------ papers
    def search_pubmed(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search PubMed pages only. Returns one dict per PubMed hit:
        {paper_id (PMID), title, year, url, published_at, snippet}.

        The snippet is page text (usually part of the abstract). Callers may read it
        to spot gene names but must not store or display it (AGENTS.md rule 7).
        """
        raw = self.search(query, site=config.KEENABLE_PUBMED_SITE, max_results=max_results)
        hits = []
        for res in raw.get("results", []):
            m = PUBMED_URL.match(res.get("url", "").strip())
            if not m:
                continue
            published = res.get("published_at") or ""
            year = int(published[:4]) if published[:4].isdigit() else None
            hits.append({
                "paper_id": m.group(1),
                "title": TITLE_SUFFIX.sub("", (res.get("title") or "").strip()),
                "year": year,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{m.group(1)}/",
                "published_at": published or None,
                "snippet": res.get("snippet") or "",
            })
        return hits

    def fetch_gene_targets(self, gene: str) -> list[str]:
        """Keenable is a web search engine and has no gene targets dataset.

        Kept so stage 2 can still try it and fall back to its stand-in
        (drug_targets.json). See AGENTS.md open questions.
        """
        raise NotImplementedError("Keenable has no gene targets dataset (it is a web search engine)")
