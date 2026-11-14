"""Stage 7 API: serves the stage output files to the dashboard.

Run:  uvicorn backend.app.main:app --reload     (docs at http://localhost:8000/docs)

Read-only. Every request re-reads the JSON contract files through backend.store
(they are small), so re-running a stage shows up on the next page refresh with
no server restart. A missing file is a 503 that names the stage to run, never a
500: during the hackathon some stages will not have run yet, and the UI should
be able to say which.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend import config
from backend.pipeline.biomarker import load_biomarker
from backend.schemas import (
    MOCK,
    Biomarker,
    GeneCandidate,
    GeneScore,
    GenomicContext,
    Paper,
    Ranking,
    Trial,
)
from backend.store import read_rows

DISCLAIMER = "Research prototype. Not medical advice."

# Contract name -> (config attribute holding the path, row model, stage that writes it,
# command that builds it). Paths are looked up on `config` at request time, not import
# time, so tests can monkeypatch them.
CONTRACTS: dict[str, tuple[str, type[BaseModel], str, str]] = {
    "papers": ("PAPERS_PATH", Paper, "stage 1 (literature)", "python -m backend.pipeline.literature"),
    "gene_candidates": ("GENE_CANDIDATES_PATH", GeneCandidate, "stage 2 (gene targets)", "python -m backend.pipeline.targets"),
    "genomic_context": ("GENOMIC_CONTEXT_PATH", GenomicContext, "stage 3 (genomic context)", "python -m backend.pipeline.genomic"),
    "gene_scores": ("GENE_SCORES_PATH", GeneScore, "stage 4 (gene scoring)", "python -m backend.pipeline.scoring"),
    "trials": ("TRIALS_PATH", Trial, "stage 5 (trials)", "python -m backend.pipeline.trials"),
    "rankings": ("RANKINGS_PATH", Ranking, "stage 6 (trial scoring)", "python -m backend.pipeline.scoring"),
}
# Contracts whose rows carry a `source` field, checked by /api/meta for mocks.
SOURCED = ("papers", "gene_candidates", "genomic_context", "trials")

app = FastAPI(title="B5 trial ranking API", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- file access
def _rel(path) -> str:
    return str(path.relative_to(config.ROOT)) if path.is_relative_to(config.ROOT) else str(path)


def _missing(what: str, path, stage: str, run: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "message": f"{path.name} is missing. Run {stage}: `{run}` "
            "(or `python -m backend.pipeline.run` for every stage).",
            "contract": what,
            "file": _rel(path),
            "stage": stage,
            "run": run,
        },
    )


def _malformed(what: str, path, exc: ValueError) -> HTTPException:
    """500 for a file that exists but is not valid JSON or does not fit its schema.

    Raised as an HTTPException (not left uncaught) so the reply is JSON and still
    passes through CORSMiddleware; an uncaught error is a bare-text 500 with no CORS
    header, which the browser reports as a network error instead of an ApiError.
    """
    message = str(exc)
    if path.name not in message:  # a bare JSONDecodeError or ValidationError has no file name
        message = f"{path.name}: {message}"
    return HTTPException(status_code=500, detail={"message": message, "contract": what, "file": _rel(path)})


def _load(name: str) -> list:
    """Read one contract file. Missing -> 503 naming the stage; malformed -> 500 naming the file."""
    attr, model, stage, run = CONTRACTS[name]
    path = getattr(config, attr)
    try:
        return read_rows(path, model)
    except FileNotFoundError:
        raise _missing(name, path, stage, run)
    except ValueError as exc:  # schema mismatch, or JSONDecodeError (a ValueError subclass)
        raise _malformed(name, path, exc)


def _load_if_present(name: str) -> list:
    """Like _load, but an absent file is just empty (used where absence is not an error)."""
    attr, *_ = CONTRACTS[name]
    return _load(name) if getattr(config, attr).exists() else []


# ---------------------------------------------------------------- API-only views
class GeneDetail(BaseModel):
    """Everything the evidence drawer shows for one gene, joined from four files."""

    gene: str
    score: Optional[GeneScore] = None              # gene_scores.json row
    candidate: Optional[GeneCandidate] = None      # gene_candidates.json row
    genomic_context: Optional[GenomicContext] = None  # genomic_context.json row, incl. model_output
    papers: list[Paper] = Field(default_factory=list)  # the papers behind literature_score
    mock_inputs: list[str] = Field(default_factory=list)  # which of the above are mocks


class Meta(BaseModel):
    has_mock_data: bool
    mock_inputs: list[str]
    disclaimer: str
    # Exposed so the UI can explain each score in one sentence without copying weights.
    weights: dict[str, int | float]


# ---------------------------------------------------------------- endpoints
@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness plus which contract files exist (never 503, so it works on a fresh clone)."""
    files = {"biomarker": config.BIOMARKER_PATH.exists()}
    files.update({name: getattr(config, attr).exists() for name, (attr, *_) in CONTRACTS.items()})
    return {"status": "ok", "files": files}


@app.get("/api/meta", response_model=Meta)
def meta() -> Meta:
    """Global mock flag for the UI banner. Looks only at files that exist."""
    mocks: set[str] = set()
    for row in _load_if_present("rankings"):
        mocks.update(row.mock_inputs)
        if row.source == MOCK:  # Ranking.source is the trial's own source
            mocks.add("trials")
    for name in SOURCED:
        if any(row.is_mock for row in _load_if_present(name)):
            mocks.add(name)
    return Meta(
        has_mock_data=bool(mocks),
        mock_inputs=sorted(mocks),
        disclaimer=DISCLAIMER,
        weights={
            "W_LIT": config.W_LIT,
            "W_MODEL": config.W_MODEL,
            "W_DIRECT": config.W_DIRECT,
            "W_GENOMIC": config.W_GENOMIC,
            "LIT_SATURATION": config.LIT_SATURATION,
            "TOP_N_MATCHED": config.TOP_N_MATCHED,
        },
    )


@app.get("/api/biomarker", response_model=Biomarker)
def biomarker() -> Biomarker:
    path = config.BIOMARKER_PATH
    if not path.exists():
        raise _missing("biomarker", path, "stage 0 (input)", "restore data/input/biomarker.json")
    try:
        return load_biomarker(path)  # pass the path: load_biomarker's default is bound at import
    except ValueError as exc:  # pydantic.ValidationError and JSONDecodeError are both ValueErrors
        raise _malformed("biomarker", path, exc)


@app.get("/api/rankings", response_model=list[Ranking])
def rankings() -> list[Ranking]:
    """The ranked trial list, exactly as stage 6 wrote it (plain array, per the contract)."""
    return sorted(_load("rankings"), key=lambda r: r.rank)


@app.get("/api/genes", response_model=list[GeneScore])
def genes() -> list[GeneScore]:
    """Per-gene scores, highest combined_score first."""
    return sorted(_load("gene_scores"), key=lambda g: g.combined_score, reverse=True)


@app.get("/api/genes/{gene}", response_model=GeneDetail)
def gene_detail(gene: str) -> GeneDetail:
    """Joined view for the evidence drawer. Gene symbols are matched case-insensitively."""
    symbol = gene.upper()
    # Load everything first so a missing file is a 503 even for an unknown gene.
    scores, candidates, contexts, papers = (
        _load(n) for n in ("gene_scores", "gene_candidates", "genomic_context", "papers")
    )
    score = next((r for r in scores if r.gene.upper() == symbol), None)
    candidate = next((r for r in candidates if r.gene.upper() == symbol), None)
    context = next((r for r in contexts if r.gene.upper() == symbol), None)
    if not (score or candidate or context):
        raise HTTPException(status_code=404, detail={"message": f"{gene} is not a candidate gene"})

    # Show the papers that literature_score counted (the candidate's paper_ids). A gene
    # with no candidate row (e.g. reached only through drug_targets.json) falls back to
    # papers that mention it.
    if candidate:
        wanted = set(candidate.paper_ids)
        gene_papers = [p for p in papers if p.paper_id in wanted]
    else:
        gene_papers = [p for p in papers if symbol in (g.upper() for g in p.genes_mentioned)]

    mock_inputs = [n for n, row in (("gene_candidates", candidate), ("genomic_context", context)) if row and row.is_mock]
    if any(p.is_mock for p in gene_papers):
        mock_inputs.append("papers")

    return GeneDetail(
        gene=symbol,
        score=score,
        candidate=candidate,
        genomic_context=context,
        papers=gene_papers,
        mock_inputs=mock_inputs,
    )


@app.get("/api/papers", response_model=list[Paper])
def papers() -> list[Paper]:
    return _load("papers")
