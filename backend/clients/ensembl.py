"""Thin Ensembl REST wrapper: gene symbol -> Ensembl ID, GRCh38 coordinates, canonical TSS.

Coordinates are always fetched, never typed from memory (AGENTS.md section 6).
Results are cached in data/cache/ensembl_genes.json; the network is only used
for symbols missing from the cache, or for every symbol with refresh=True.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Optional

import httpx

from backend import config
from backend.store import read_json, write_json


@dataclass
class EnsemblGene:
    symbol: str
    ensembl_id: str
    chrom: str          # "17" (no "chr" prefix, Ensembl style)
    start: int          # 1-based, inclusive (gene body)
    end: int            # 1-based, inclusive
    strand: int         # 1 or -1
    canonical_transcript: Optional[str]
    tss: int            # 1-based genomic position of the canonical transcript's first base
    assembly: str
    biotype: str = ""
    approved_symbol: str = ""  # current HGNC symbol (differs when papers use an old one)
    # Canonical transcript exons as [start, end] (1-based, inclusive), in transcription
    # order. None in cache entries written before this field existed.
    canonical_exons: Optional[list[list[int]]] = None

    @property
    def region(self) -> str:
        return f"chr{self.chrom}:{self.start}-{self.end}"


class EnsemblError(RuntimeError):
    """Ensembl could not be reached or kept failing (transient; not cached)."""


class EnsemblNotFound(EnsemblError):
    """Ensembl answered: no such human gene (cached, so we do not re-ask)."""


def _load_cache() -> dict[str, dict]:
    if config.ENSEMBL_CACHE_PATH.exists():
        return read_json(config.ENSEMBL_CACHE_PATH)
    return {}


def _get(client: httpx.Client, url: str, params: dict) -> Optional[httpx.Response]:
    """GET with Ensembl's rate-limit etiquette. Returns None on 400/404."""
    for attempt in range(4):
        r = client.get(url, params=params, headers={"Content-Type": "application/json"})
        if r.status_code == 429 or r.status_code >= 500:  # rate limit or transient outage
            time.sleep(min(float(r.headers.get("Retry-After", 2 ** attempt)), 30))
            continue
        if r.status_code in (400, 404):
            return None
        r.raise_for_status()
        return r
    raise EnsemblError(f"Ensembl kept failing (rate limit / 5xx) for {url}")


def _fetch(symbol: str, client: httpx.Client) -> EnsemblGene:
    base = config.ENSEMBL_REST_URL
    r = _get(client, f"{base}/lookup/symbol/homo_sapiens/{symbol}", {"expand": 1})
    if r is None:
        # Papers often use a previous HGNC symbol (e.g. SLC9A3R1, now NHERF1).
        # The xrefs endpoint resolves synonyms to the current Ensembl gene ID.
        x = _get(client, f"{base}/xrefs/symbol/homo_sapiens/{symbol}", {"object_type": "gene"})
        ids = [e["id"] for e in (x.json() if x is not None else []) if str(e.get("id", "")).startswith("ENSG")]
        if not ids:
            raise EnsemblNotFound(f"Ensembl has no human gene for symbol {symbol!r}")
        r = _get(client, f"{base}/lookup/id/{ids[0]}", {"expand": 1})
        if r is None:
            raise EnsemblNotFound(f"Ensembl could not look up {ids[0]} (from {symbol!r})")
    d = r.json()
    canon = next((t for t in d.get("Transcript", []) if t.get("is_canonical")), None)
    strand = int(d["strand"])
    exons = None
    if canon is not None:
        tss = int(canon["start"]) if strand == 1 else int(canon["end"])
        canon_id = canon["id"]
        exons = sorted(([int(e["start"]), int(e["end"])] for e in canon.get("Exon", [])),
                       key=lambda e: e[0], reverse=(strand == -1))
    else:  # fall back to the gene body's 5' end
        tss = int(d["start"]) if strand == 1 else int(d["end"])
        canon_id = None
    return EnsemblGene(
        symbol=symbol,
        ensembl_id=d["id"],
        chrom=str(d["seq_region_name"]),
        start=int(d["start"]),
        end=int(d["end"]),
        strand=strand,
        canonical_transcript=canon_id,
        tss=tss,
        assembly=d.get("assembly_name", config.GI_ASSEMBLY),
        biotype=d.get("biotype", ""),
        approved_symbol=d.get("display_name", symbol),
        canonical_exons=exons,
    )


def lookup_genes(symbols: list[str], refresh: bool = False, need_exons: bool = False) -> dict[str, EnsemblGene]:
    """Resolve symbols to EnsemblGene. Unknown symbols are left out of the result.

    need_exons=True re-fetches cached entries that predate the canonical_exons field.
    """
    cache = _load_cache()
    missing = [
        s for s in symbols
        if refresh or s not in cache or (need_exons and cache[s] and cache[s].get("canonical_exons") is None)
    ]
    if missing:
        with httpx.Client(timeout=config.ENSEMBL_TIMEOUT_S) as client:
            for s in missing:
                try:
                    cache[s] = asdict(_fetch(s, client))
                except EnsemblNotFound:
                    cache[s] = None  # remember a definite miss so we do not re-ask every run
                except (EnsemblError, httpx.HTTPError):
                    pass  # transient: leave uncached so the next run retries
                time.sleep(0.07)  # Ensembl asks for <= 15 requests/second
        write_json(config.ENSEMBL_CACHE_PATH, dict(sorted(cache.items())))
    return {s: EnsemblGene(**cache[s]) for s in symbols if cache.get(s)}


def lookup_gene(symbol: str, refresh: bool = False) -> Optional[EnsemblGene]:
    return lookup_genes([symbol], refresh=refresh).get(symbol)


def genes_in_region(chrom: str, start: int, end: int) -> list[dict]:
    """Known genes overlapping chrom:start-end (1-based, inclusive), from Ensembl.

    Each row: {symbol, ensembl_id, start, end, strand, five_prime, biotype}, where
    five_prime is the gene body's 5' end (start on +, end on -), a proxy for its TSS.
    Not cached: used once per amplicon scan, which is itself cached.
    """
    url = f"{config.ENSEMBL_REST_URL}/overlap/region/homo_sapiens/{chrom}:{start}-{end}"
    with httpx.Client(timeout=config.ENSEMBL_TIMEOUT_S) as client:
        r = _get(client, url, {"feature": "gene"})
    rows = []
    for g in (r.json() if r is not None else []):
        strand = int(g["strand"])
        rows.append({
            "symbol": g.get("external_name") or g["id"],
            "ensembl_id": g["id"],
            "start": int(g["start"]),
            "end": int(g["end"]),
            "strand": strand,
            "five_prime": int(g["start"]) if strand == 1 else int(g["end"]),
            "biotype": g.get("biotype", ""),
        })
    return rows
