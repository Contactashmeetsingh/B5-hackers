> **Architecture v1 notes (historical).** On 2026-11-14 the project moved to architecture v2: two approaches (papers → trial matching, DNA model → Pan-Cancer Atlas) and **no scoring system**. Stage numbers, `scoring.py`, `gene_scores.json` and `rankings.json` mentioned below no longer exist. `AGENTS.md` is the source of truth and `HUMAN.md` tracks progress.

> **Parked (2026-11-14):** we are building proofs of concept, not a working app, so the web page below is on hold. The API is done and tested, and stays.

# Lane D: Dashboard (stage 7)

**Owner:** TBD

**Scope:** serve the pipeline's JSON files over a small read-only API, and render them as one page: a biomarker card, the ranked trials, and an evidence drawer per trial. This lane computes no scores and writes no contract file; it only shows what lanes A to C wrote. Spec: `AGENTS.md` sections 4, 7 and 8. If this file and `AGENTS.md` disagree, `AGENTS.md` wins.

## Files this lane owns

| File | What it does |
|---|---|
| `backend/app/main.py` | FastAPI app (`uvicorn backend.app.main:app`). Re-reads the contract files through `backend.store` on every request. CORS allows `http://localhost:3000`. |
| `frontend/` | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. Not scaffolded yet: see [`frontend/README.md`](../../frontend/README.md) for the commands and the page spec. |
| `frontend/lib/types.ts` | TypeScript mirror of `backend/schemas.py` and the API views |
| `frontend/lib/api.ts` | One typed fetch helper per endpoint; base URL from `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`) |
| `tests/test_api.py` | One offline smoke test: every endpoint on `tmp_path` fixtures, plus the 503 path |

## Endpoints

All are `GET`. A contract file that does not exist yet returns **503** with `detail.message`, `detail.file`, `detail.stage` and `detail.run` (the command that builds it), never a 500. A file that exists but is not valid JSON or does not match its schema returns a JSON **500** with `detail.message` (which names the file), `detail.contract` and `detail.file`. This also covers `data/input/biomarker.json`.

| Endpoint | Returns | Built from |
|---|---|---|
| `/api/health` | `{status, files: {name: exists}}`. Never 503. | file existence only |
| `/api/meta` | `{has_mock_data, mock_inputs, disclaimer, weights}` | `rankings[].mock_inputs` and `source` on papers, gene_candidates, genomic_context and trials; weights from `backend/config.py` |
| `/api/biomarker` | `Biomarker` | `data/input/biomarker.json` |
| `/api/rankings` | `Ranking[]`, a plain array sorted by `rank` | `data/output/rankings.json` |
| `/api/genes` | `GeneScore[]`, sorted by `combined_score` (highest first) | `data/cache/gene_scores.json` |
| `/api/genes/{gene}` | `GeneDetail`: `{gene, score, candidate, genomic_context, papers, mock_inputs}`. Case-insensitive; 404 for an unknown gene. | gene_scores, gene_candidates, genomic_context (including `model_output`), papers |
| `/api/papers` | `Paper[]` | `data/cache/papers.json` |

`GeneDetail.papers` holds the candidate's `paper_ids` (the papers that `literature_score` counted). A gene with no candidate row falls back to papers whose `genes_mentioned` includes it. Interactive docs: `http://localhost:8000/docs`.

## What it reads from other lanes

| From | File | Used for |
|---|---|---|
| A (literature) | `papers.json`, `gene_candidates.json` | drawer papers, and the candidate's paper list |
| B (genomic) | `genomic_context.json` | drawer: `region`, `model_task`, `model_score` and the `model_output` components. Lane B owns the shape of `model_output`: [`lanes/B-genomic/README.md`](../B-genomic/README.md) |
| C (trials and scoring) | `rankings.json`, `gene_scores.json`, `trials.json` | the ranked list, per-gene scores, and mock detection |

Every row with `source: "mock"`, and every ranking with a non-empty `mock_inputs`, must carry a visible "mock data" tag in the UI.

## Status

Done
- [x] FastAPI app with all endpoints, 503 for missing stages, and CORS
- [x] `/api/meta` mock flag and disclaimer
- [x] TypeScript types and fetch helpers
- [x] Smoke test

To do
- [ ] Scaffold the Next.js app (commands in `frontend/README.md`)
- [ ] Biomarker card header
- [ ] Ranked list: rank, title, phase, status, score bar, gene chips, trial link
- [ ] Evidence drawer: score breakdown, per-gene literature, model and combined scores, Genomic Intelligence components, papers with links
- [ ] Visible "mock data" tag on rows and in the drawer, plus the global banner
- [ ] Footer disclaimer
- [ ] 503 state: show "run stage X" instead of a broken page

## How to run

```bash
# API, from the repo root
.venv/bin/uvicorn backend.app.main:app --reload     # http://localhost:8000/docs
.venv/bin/python -m pytest tests/test_api.py -q

# UI, once it is scaffolded
cd frontend && npm run dev                          # http://localhost:3000
```

The API shows whatever is on disk. To fill in the 503s, run the missing stages (`python -m backend.pipeline.run` builds them all) and refresh the page. No restart is needed.
