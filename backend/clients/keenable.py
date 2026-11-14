"""Thin wrapper for Keenable (lane A, stages 1 and 2).

Status: placeholder. The literature cache in data/cache/papers.json was built by
hand with Keenable web search (app.keenable.ai)
and verified against PubMed. The API's docs URL, auth method and response
format are still an open question (AGENTS.md section 12), so this client does
not guess any endpoint. Every call raises NotImplementedError, and the pipeline
stages fall back to their caches when that happens.

When the docs arrive, fill in the two methods below. They are the only place
that should know the Keenable request and response format: they return rows
already shaped like our contracts, so pipeline code never touches raw responses.
"""

from __future__ import annotations

from typing import Optional

from backend import config  # importing config also loads .env

NOT_DOCUMENTED = "Keenable API not documented yet; see AGENTS.md open questions"


class KeenableClient:
    def __init__(self, api_key: Optional[str] = None):
        # Read from the environment (.env). Never print or log the key.
        self._api_key = api_key or config.KEENABLE_API_KEY

    @property
    def has_key(self) -> bool:
        return self._api_key is not None

    def __repr__(self) -> str:  # keep the key out of tracebacks and logs
        return f"KeenableClient(has_key={self.has_key})"

    def search_papers(self, query: str) -> list[dict]:
        """Stage 1: search for papers.

        Contract once implemented: a list of dicts shaped like papers.json rows
        (paper_id, title, year, url, genes_mentioned, relation, source="keenable").
        Open question: whether Keenable returns structured gene mentions or raw
        text that we must parse here.
        """
        raise NotImplementedError(NOT_DOCUMENTED)

    def fetch_gene_targets(self, gene: str) -> list[str]:
        """Stage 2: gene symbols from the Keenable gene targets dataset for `gene`.

        Open question: which dataset this is and its license.
        """
        raise NotImplementedError(NOT_DOCUMENTED)
