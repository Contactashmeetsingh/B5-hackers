# AGENTS.md

Ground truth for every coding agent working in this repo. Read this file fully before writing code. If something here conflicts with a teammate's chat message, this file wins until it is edited. `README.md` (formerly `HUMAN.md`) is the same plan drawn for people.

## 1. Mission

Build a hackathon proof of concept that takes one cancer biomarker and returns a ranked list of clinical trials, with the evidence behind each rank visible in a dashboard.

The demo must run end to end for one biomarker. Breadth, polish, and scale are out of scope.

This is a research demo. It is not medical advice and must say so in the UI.

## 2. The input (fixed for the PoC)

One biomarker record, stored at `data/input/biomarker.json`:

| Field | Value |
|---|---|
| tissue | Breast |
| biomarker | HER2 |
| gene | ERBB2 |
| measurement | HER2 receptor (IHC score ± ISH) |
| source_field | `labels.diagnosis.Biomarkers` |
| coverage | 1,290 / 1,290 cases |
| aliases | HER2, ERBB2, HER-2, HER2/neu, ErbB-2, ErbB2 (used to spot the biomarker in trial text) |
| sanity_genes | the section 9 sanity list (logged by stage 2, never scored) |
| model_context | conditioning for the Genomic Intelligence models: `expression_target` ("HER2-positive breast cancer cell line"), `expression_reference` ("liver tissue"), `chromatin_cell_types` (HMEC, MCF-7, T-47D) |

Do not generalize to other biomarkers yet. Do keep the biomarker as a parameter (never a string literal buried in pipeline code) so more rows can be added later.

## 3. System overview

Two paths that meet at the scoring step.

**Way 1: evidence and genomic scoring (what matters biologically)**

1. **Literature retrieval.** Use Keenable to find research papers connecting HER2/ERBB2 to other genes. Output: candidate genes, each with supporting papers.
2. **Gene targets dataset.** Use Keenable to find a gene targets dataset. Use it to confirm and extend the candidate gene list.
3. **Genomic context.** For each candidate gene, fetch its genomic region and run it through the Genomic Intelligence model. Store two things per gene: the genomic context returned by the model, and a model likelihood score.
4. **Combined gene score.** Merge the literature evidence and the model score into one score per gene.

**Way 2: trials (what a user can act on)**

5. **Trial retrieval.** Hard-coded: a cached snapshot of clinical trials for ERBB2/HER2 breast cancer. No live search needed in the demo.
6. **Trial likelihood scoring.** Score each trial against the genomic context from Way 1. A trial is rarely about the biomarker alone; it usually adds other targets, drugs, or eligibility genes. The score measures how well those additions line up with the genes Way 1 scored highly.

**Output**

7. **Dashboard.** A ranked list of trials. Each row shows its score, the genes that drove it, and the papers behind those genes.

## 4. Stage contracts

Every stage reads JSON, writes JSON, and can be run alone. Stages talk only through these files. If you change a schema, update this section in the same commit.

| # | Stage | Module | Reads | Writes |
|---|---|---|---|---|
| 0 | Input | `backend/pipeline/biomarker.py` | `data/input/biomarker.json` | (in memory) |
| 1 | Literature | `backend/pipeline/literature.py` | biomarker | `data/cache/papers.json` |
| 2 | Gene targets | `backend/pipeline/targets.py` | biomarker, papers | `data/cache/gene_candidates.json` |
| 3 | Genomic context | `backend/pipeline/genomic.py` | gene_candidates | `data/cache/genomic_context.json` |
| 4 | Gene scoring | `backend/pipeline/scoring.py` | papers, gene_candidates, genomic_context | `data/cache/gene_scores.json` |
| 5 | Trials | `backend/pipeline/trials.py` | biomarker | `data/cache/trials.json` |
| 6 | Trial scoring | `backend/pipeline/scoring.py` | gene_scores, gene_candidates, genomic_context, trials, drug_targets, biomarker | `data/output/rankings.json` |
| 7 | API + UI | `backend/app/main.py`, `frontend/` | rankings and caches | dashboard |

### Schemas

```jsonc
// papers.json
[{ "paper_id": "PMID or DOI", "title": "", "year": 2024, "url": "",
   "genes_mentioned": ["ERBB2", "PIK3CA"],
   "relation": "one sentence, paraphrased, on how the paper links the gene to HER2",
   "source": "keenable | mock" }]

// gene_candidates.json  (includes the biomarker gene itself; stage 6 excludes it from genomic_match)
[{ "gene": "PIK3CA", "ensembl_id": "ENSG...", "in_targets_dataset": true,
   "paper_ids": ["..."], "source": "keenable | mock",
   "approved_symbol": "(optional) current HGNC symbol when papers use an old one",
   "targets_dataset": "name of the targets dataset, or 'pending (drug_targets.json seed used as stand-in)'" }]

// genomic_context.json
[{ "gene": "PIK3CA", "assembly": "GRCh38", "region": "chr3:start-end",   // gene body, 1-based inclusive
   "model_task": "expression (g0-expression-8192) + promoter (...) + ... + composite (annotation->expression)",
   "model_output": { "summary": "", "task_scores": { "expression": 0.0, "composite": 0.0, "promoter": 0.0,
                     "chromatin": 0.0, "enhancer": 0.0, "splice": 0.0, "annotation": 0.0 },
                     "task_raw": {}, "tasks_used": [], "weights": {}, "locus": {}, "expression": {}, "composite": {},
                     "promoter": {}, "chromatin": {}, "enhancer": {}, "splice": {}, "annotation": {},
                     "models": {}, "retrieved": "YYYY-MM-DD", "demo_key": true },
   "model_score": 0.0,            // [0,1]; null on mock rows (never invented)
   "source": "genomic_intelligence | mock" }]
// full model_output shape: lanes/B-genomic/README.md

// gene_scores.json
[{ "gene": "PIK3CA", "literature_score": 0.0, "model_score": 0.0, "combined_score": 0.0 }]

// trials.json
[{ "nct_id": "NCT...", "title": "", "phase": "", "status": "", "url": "",
   "conditions": [""], "interventions": [""], "eligibility_text": "",
   "source": "clinicaltrials.gov snapshot | mock" }]

// rankings.json  (the only file the dashboard needs)
[{ "rank": 1, "nct_id": "NCT...", "title": "", "phase": "", "status": "", "url": "",
   "trial_score": 0.0, "biomarker_directness": 0.0, "genomic_match": 0.0,
   "matched_genes": [{ "gene": "PIK3CA", "combined_score": 0.0, "paper_ids": ["..."] }],
   "source": "clinicaltrials.gov snapshot | mock",       // the trial's own source
   "mock_inputs": ["trials", "gene_candidates", "genomic_context"] }]  // non-empty -> UI shows "mock data"

// data/input/drug_targets.json
[{ "drug": "trastuzumab", "aliases": ["Herceptin"], "target_genes": ["ERBB2"], "source": "where the pair came from" }]
```

The pydantic models for every file above live in `backend/schemas.py`; read and write them only through `backend/store.py`.

Side caches (not contracts; written and read by one stage only): `data/cache/ensembl_genes.json` (Ensembl lookups), `data/cache/genomic_raw/<GENE>.json` (one digest of the GI calls per gene, with request ids), `data/cache/amplicon_context.json` (optional: genes GI finds around the biomarker gene; context for the UI, not scored).

## 5. Scoring (v0, deliberately simple)

All scores are floats in [0, 1]. All weights live in `backend/config.py`. Never hard-code a weight inside a function.

**Gene level**

- `literature_score = min(1, supporting_papers / LIT_SATURATION)` with `LIT_SATURATION = 5`
- `model_score` = the stage 3 Genomic Intelligence score, min-max normalized across the candidate set. Stage 3 runs **every GI task** at the gene's canonical TSS and reduces each to one task score in [0, 1]: expression (target-context level + specificity vs `expression_reference`), composite (find genes + expression), promoter, chromatin (on-tissue calls), enhancer, splice (canonical junctions recovered) and annotation (gene finder confidence at the TSS). Probabilities and fractions are used as-is; unbounded readouts are min-max normalized. `model_score` = weighted mean of the task scores the gene has (`W_GI_TASK`, 1.0 each). Higher means the DNA models see a well-formed, active, breast-relevant gene at that promoter. Details, caveats and the v0 → v1 status: `lanes/B-genomic/README.md`.
- `combined_score = W_LIT * literature_score + W_MODEL * model_score` with `W_LIT = 0.5`, `W_MODEL = 0.5`

**Trial level**

- `matched_genes` = candidate genes found in the trial's title, conditions, interventions, or eligibility text, plus genes reached through `data/input/drug_targets.json` (drug name to target gene, for example trastuzumab to ERBB2, alpelisib to PIK3CA)
- `genomic_match` = mean `combined_score` of the top 3 matched genes, excluding ERBB2 itself (0 if none)
- `biomarker_directness` = 1.0 if HER2/ERBB2 status is an eligibility requirement, 0.5 if only mentioned, 0 otherwise
- `trial_score = W_DIRECT * biomarker_directness + W_GENOMIC * genomic_match` with `W_DIRECT = 0.4`, `W_GENOMIC = 0.6`

ERBB2 is excluded from `genomic_match` on purpose. Every trial in the snapshot is already about HER2, so including it would flatten the ranking. The signal we want is the "in addition to the biomarker" part.

These formulas are a starting point for a demo, not a validated method. Keep them readable so the team can explain them to judges in one sentence each.

## 6. External services

| Service | Used for | Notes |
|---|---|---|
| **Keenable** (hackathon sponsor) | Stage 1 paper search, stage 2 gene targets dataset | Web app: https://app.keenable.ai (search, fetch, API keys). API auth not yet recorded here. See open questions. All calls go through `backend/clients/keenable.py`. |
| **Genomic Intelligence** (hackathon sponsor) | Stage 3 genomic context and model score | Docs: https://docs.genomicintelligence.ai (llms.txt index, `AGENTS.md`, OpenAPI at `api.genomicintelligence.ai/v1/openapi.json`). We call the hosted MCP server `https://mcp.genomicintelligence.ai/mcp` (MCP Streamable HTTP). It answers on a shared demo key, so no key is needed; set `GI_API_KEY` to use our own key on the same server. Tools used: `list_models`, `fetch_gene_for_expression`, `fetch_region`, `predict_expression`, `predict_promoter`, `predict_chromatin`, `find_genes_and_predict_expression`. Sequences are fetched server-side and passed as handles, so DNA never transits our code. Switch on `error.code`, never the message. All calls go through `backend/clients/genomic_intelligence.py`. |
| **Ensembl REST** | Gene symbol to Ensembl ID, GRCh38 coordinates, canonical TSS | Fetch coordinates, do not type them from memory. All calls go through `backend/clients/ensembl.py` (cached in `data/cache/ensembl_genes.json`; resolves old HGNC symbols). |
| **ClinicalTrials.gov API v2** | One-time snapshot for stage 5 | Run once, save to `data/cache/trials.json`, commit it. The demo never calls it live. |

Rules for all clients:

- One thin wrapper file per service. Pipeline code never calls an HTTP endpoint directly.
- **Cache first.** If the cache file exists, use it. Only call the network when run with `--refresh`, or for items missing from a per-item cache (stage 3 sends only uncached genes to GI; `--offline` forbids even that).
- Keys come from `.env` (see `.env.example`). Never commit a key. Never print one.
- If a service is unreachable or undocumented, write a mock that returns the right schema with `"source": "mock"` and keep going. The UI must show a visible "mock data" tag on anything mocked.

## 7. Tech stack (default, change only by editing this section)

- **Backend:** Python 3.11, FastAPI, pydantic models that mirror the schemas above, `httpx` for clients
- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui
- **Storage:** JSON files in `data/`. No database.
- **Run:** `python -m backend.pipeline.run` builds every cache and `rankings.json`. `uvicorn backend.app.main:app` serves it. `npm run dev` in `frontend/`.

```
AGENTS.md  CLAUDE.md  README.md (the plan for people, formerly HUMAN.md)
backend/
  config.py            weights and paths
  schemas.py           pydantic models for every contract file (section 4)
  store.py             read_rows / write_rows: validated JSON I/O
  clients/             keenable.py, genomic_intelligence.py, ensembl.py, clinicaltrials.py
  pipeline/            biomarker.py, literature.py, targets.py, genomic.py, trials.py, scoring.py, run.py
  app/main.py          GET /api/biomarker, /api/rankings, /api/genes, /api/papers (+ /api/genes/{gene}, /api/meta, /api/health)
data/
  input/               biomarker.json, drug_targets.json
  cache/               stage outputs (committed, so the demo works offline)
  output/rankings.json
frontend/
lanes/                 one folder per lane (A-literature, B-genomic, C-trials-scoring, D-dashboard): scope, status, hand-offs
tests/                 one offline smoke test per stage
```

Setup: `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt`.

## 8. Dashboard requirements

- One page. Header shows the biomarker card (Breast, HER2, ERBB2, IHC ± ISH).
- Main view is the ranked trial list: rank, title, phase, status, score bar, matched gene chips, link to the trial.
- Clicking a row expands the evidence: per-gene scores (literature, model, combined) and the supporting papers with links.
- Footer disclaimer: research prototype, not medical advice.
- Layout references: biomarkershealth.com and clintrialfinder.com. Borrow the layout pattern (clean ranked list, card rows, score chips). Do not copy their code, logos, text, or brand assets.

## 9. Domain facts agents may rely on

- HER2 is the protein; ERBB2 is the gene that encodes it (chromosome 17q12).
- HER2 status is measured by IHC (0, 1+, 2+, 3+). IHC 3+ is positive. IHC 2+ is equivocal and resolved by ISH (amplified means positive). IHC 1+ or 2+ with negative ISH is commonly called HER2-low.
- The usual mechanism behind HER2 positivity is ERBB2 gene amplification, which is why genomic context around ERBB2 and its neighbors is relevant.
- Sanity check, not a hard-coded answer: a working stage 1 and 2 should surface genes like PIK3CA, ERBB3, EGFR, GRB7, CDK12, TOP2A, PTEN, TP53, ESR1. If none of these appear, the retrieval is probably broken.
- Seed entries for `drug_targets.json`: trastuzumab, pertuzumab, trastuzumab deruxtecan, trastuzumab emtansine, tucatinib, lapatinib, neratinib, margetuximab (all ERBB2).

## 10. Rules for agents

1. **Never fabricate data.** No invented papers, PMIDs, NCT IDs, scores, or model outputs. Real result, or a clearly labeled mock.
2. **Stay in your stage.** Touch only the module you were asked to build. Communicate through the JSON contracts.
3. **Demo over depth.** Prefer the simplest thing that makes the end to end run work. No auth, no database, no deployment config, no test suites beyond one smoke test per stage.
4. **Small commits, one stage each.** Branch per workstream, merge to `main` often.
5. **Paraphrase papers.** Store titles, IDs, links, and a one sentence summary in our own words. Do not store or display copied abstracts.
6. **Ask, do not guess,** on anything listed under open questions.

## 11. Build order

1. Scaffold repo layout, `config.py`, pydantic schemas, `biomarker.json`.
2. Write mock versions of every stage so `run.py` produces a `rankings.json` in the first hour.
3. Frontend renders `rankings.json` (works from mocks immediately).
4. Replace mocks with real calls one stage at a time: trials snapshot, then Keenable, then Genomic Intelligence.
5. Tune weights, add the evidence drawer, rehearse the demo.

## 12. Open questions (resolve, then edit this file)

- **Keenable:** name and web app resolved (Keenable, https://app.keenable.ai). Still open: API auth method, and whether it returns structured gene mentions or raw text we must parse.
- **Gene targets dataset:** which dataset Keenable gives us and its license.
- **Weights:** are 0.5/0.5 and 0.4/0.6 acceptable defaults for the demo?
- **Owners:** who takes lanes A, C and D in `README.md` (lane B: Contactashmeetsingh).

### Resolved

- **Genomic Intelligence task and meaning of "higher"** (2026-11-14, lane B owner). The score is based on the output of **every** GI task (promoter, splice, enhancer, chromatin, expression, annotation, find genes + expression), one task score each, used in the ranking and compared against the Keenable literature evidence. Higher = the DNA models see the gene as well-formed, active and breast-relevant at its promoter. See section 5 and `lanes/B-genomic/README.md`.
