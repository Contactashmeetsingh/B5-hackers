# Lane A: Literature and targets (stages 1 and 2)

**Owner:** TBD

**Scope:** find papers that link the biomarker gene (ERBB2 for the PoC, read from `data/input/biomarker.json`) to other genes, then turn them into a candidate gene list confirmed against a gene targets dataset. Spec: `AGENTS.md` sections 3, 4 and 9. If this file and `AGENTS.md` disagree, `AGENTS.md` wins.

## Files this lane owns

| File | What it does |
|---|---|
| `backend/clients/keenable.py` | Keenable client. Placeholder: `search_papers` and `fetch_gene_targets` raise `NotImplementedError` until docs and auth are known. Reads `KEENABLE_API_KEY` from `.env` and never prints it. |
| `backend/pipeline/literature.py` | Stage 1. Cache first. `--refresh` tries Keenable; if that fails it keeps the existing cache. Writes a mock (`MOCK-PAPER-001`, ...) only when no cache exists at all. |
| `backend/pipeline/targets.py` | Stage 2. Builds `gene_candidates.json` from the papers plus `drug_targets.json`, and logs the section 9 sanity check. |
| `data/cache/papers.json` | Stage 1 output. **Real:** 29 PubMed-verified papers (`source: "keenable"`). Built by hand with Keenable web search; see `keenable/her2_interactors_literature.md`. Do not regenerate it with mocks. |
| `data/cache/gene_candidates.json` | Stage 2 output. 30 genes, ERBB2 included. |
| `tests/test_literature.py`, `tests/test_targets.py` | One offline smoke test per stage. |

## Contract

| Stage | Reads | Writes |
|---|---|---|
| 1 Literature | biomarker | `data/cache/papers.json` (list of `Paper`) |
| 2 Gene targets | biomarker, `papers.json`, `data/input/drug_targets.json` | `data/cache/gene_candidates.json` (list of `GeneCandidate`) |

Each `gene_candidates.json` row has:

- `gene`: the symbol as the papers spell it. When Ensembl's current symbol differs, `approved_symbol` is added (for example `SLC9A3R1` -> `NHERF1`).
- `ensembl_id`: from `backend/clients/ensembl.py`, read from `data/cache/ensembl_genes.json`. It is `null` if Ensembl has no match.
- `paper_ids`: real PMIDs from `papers.json`, in file order. This is `[]` for genes that only come from `drug_targets.json`.
- `in_targets_dataset`: whether the gene is a target of a drug listed in `drug_targets.json`. This stands in for the real dataset for now.
- `source`: `"mock"` on every row for now, because the targets-dataset part is a stand-in. The paper evidence is real.
- `targets_dataset`: `"pending (drug_targets.json seed used as stand-in)"`.

Rows are sorted by number of supporting papers (highest first), then by gene.

## Status

Done
- [x] Stage 1 cache: 29 real papers, 30 genes
- [x] Keenable client placeholder (no guessed endpoints)
- [x] Stage 1 `--refresh` falls back to the cache and never overwrites real data
- [x] Stage 2 builds 30 candidates. Sanity check: PIK3CA, ERBB3, EGFR, GRB7, PTEN and ESR1 are present; CDK12, TOP2A and TP53 are missing.
- [x] Offline smoke tests for both stages

To do
- [ ] Keenable docs URL and auth (`AGENTS.md` open questions), then implement `KeenableClient.search_papers`
- [ ] Real gene targets dataset (which one, and its license), then implement `KeenableClient.fetch_gene_targets` and drop the stand-in
- [ ] Follow-up search for CDK12, TOP2A and TP53. These are expected by `AGENTS.md` section 9 but missing from the current literature run. Add only PubMed-verified papers.
- [ ] Once the real dataset exists, `source` on stage 2 rows becomes `"keenable"`

## How to run

```bash
.venv/bin/python -m backend.pipeline.literature            # load and validate papers.json
.venv/bin/python -m backend.pipeline.literature --refresh  # try Keenable; keeps the cache on failure
.venv/bin/python -m backend.pipeline.targets               # use gene_candidates.json if it exists
.venv/bin/python -m backend.pipeline.targets --refresh     # rebuild it from papers.json
.venv/bin/python -m pytest tests/test_literature.py tests/test_targets.py -q
```

After editing `papers.json`, re-run stage 2 with `--refresh`. Without it, stage 2 returns its existing cache.

## Handoff

- **Lane B (genomic, stage 3):** `backend/pipeline/genomic.py` reads `gene_candidates.json` and runs each `gene` (and `ensembl_id`) through Ensembl coordinates and Genomic Intelligence. Notes for lane B:
  - The biomarker gene (ERBB2) is in the list on purpose. Lane B can score it, and stage 6 leaves it out of `genomic_match`.
  - A row with `ensembl_id: null` cannot be placed on the genome. Skip it or mark it as mock.
  - Use `gene` as the join key, because stages 4 and 6 join on it. `approved_symbol` is for display only.
- **Lane C (scoring, stages 4 and 6):** `literature_score` counts `paper_ids` per gene. Every row is `source: "mock"` today, so `gene_candidates` should show up in a ranking's `mock_inputs` until the real targets dataset lands.
