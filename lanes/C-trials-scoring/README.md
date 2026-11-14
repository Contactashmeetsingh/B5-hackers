# Lane C: Trials and scoring (stages 4, 5, 6 and the orchestrator)

**Owner:** TBD

**Scope:** take the clinical trial snapshot (stage 5), merge literature and model evidence into one score per gene (stage 4), and rank trials by how well their extra genes and drugs line up with those gene scores (stage 6). Also owns `run.py`, which runs stages 1 to 6 in order. Spec: `AGENTS.md` sections 4 and 5. If this file and `AGENTS.md` disagree, `AGENTS.md` wins.

## Files this lane owns

| File | What it does |
|---|---|
| `backend/clients/clinicaltrials.py` | Thin ClinicalTrials.gov API v2 client. `fetch_studies(query_cond, query_term, page_size, max_studies, overall_status=None)` follows `nextPageToken` and maps each study to a `Trial`. `to_trial(study)` holds the field mapping. Field paths were checked against one live 2-study request. |
| `backend/pipeline/trials.py` | Stage 5. Cache first. `--refresh` takes a real snapshot, with the query built from the biomarker record. If `--refresh` fails it keeps the existing cache. A mock is written only when no cache exists. |
| `backend/pipeline/scoring.py` | Stage 4 `run_gene_scores()` and stage 6 `run_trial_rankings()`. Pure functions of files on disk, with every weight read from `backend/config.py`. |
| `backend/pipeline/run.py` | Orchestrator. Prints one line per stage: rows written, how many are mock, output file. |
| `data/cache/trials.json` | Stage 5 output. **Currently MOCK:** 6 trials, `MOCK-NCT-0001` to `MOCK-NCT-0006`, `source: "mock"`, no URLs. |
| `tests/test_trials.py`, `tests/test_scoring.py` | One offline smoke test per stage. The scoring test checks the formulas on a hand-computed fixture. |

## Contract

| Stage | Reads | Writes |
|---|---|---|
| 4 Gene scoring | `papers.json`, `gene_candidates.json`, `genomic_context.json` | `data/cache/gene_scores.json` (list of `GeneScore`, sorted by `combined_score` desc) |
| 5 Trials | biomarker | `data/cache/trials.json` (list of `Trial`) |
| 6 Trial scoring | biomarker, `gene_scores.json`, `gene_candidates.json`, `genomic_context.json`, `trials.json`, `data/input/drug_targets.json` | `data/output/rankings.json` (list of `Ranking`, rank 1 first) |

Stage 6 also reads `gene_candidates` (for `paper_ids`) and `genomic_context` (to know which inputs are mock), in addition to the two inputs in the `AGENTS.md` table.

## Scoring, one sentence each

All scores are in [0, 1], rounded to 4 decimals. Each derived score is computed from the rounded inputs, so the numbers in the dashboard add up exactly.

- **literature_score** = `min(1, papers / LIT_SATURATION)`: five supporting papers means full literature credit. Paper IDs are de-duplicated first.
- **model_score** = lane B's `model_score`, min-max normalised across the candidate set: the gene the model rates highest gets 1, the lowest gets 0.
- **combined_score** = `W_LIT * literature + W_MODEL * model`.
- **genomic_match** = mean `combined_score` of the trial's top `TOP_N_MATCHED` matched genes, leaving out the biomarker gene. It is 0 if no other gene matched.
- **biomarker_directness** = 1.0 if eligibility requires biomarker status, 0.5 if the biomarker is only mentioned, 0 otherwise.
- **trial_score** = `W_DIRECT * directness + W_GENOMIC * genomic_match`. Ties are broken by `nct_id`.

### Choices made (so we can explain them to judges)

- **Unscored genes.** A candidate missing from `genomic_context.json`, or with `model_score: null`, gets `model_score = 0.0`. The stage prints a note naming those genes. Only candidates take part in the min-max. Extra rows in `genomic_context.json`, such as amplicon genes, do not move it.
- **Degenerate min-max.** If every scored gene has the same raw value (one scored gene included), every gene gets `model_score = 0.0`. A model signal that does not vary cannot tell genes apart, so it adds nothing. This is also what min-max gives when every gene is the minimum.
- **Gene matching.** The match is on the whole term in title, conditions, interventions and eligibility, and the term may not touch a letter or digit, so `PIK3CA-mutant` and `(ERBB2)` match. Short, all-letter symbols (up to 4 letters: SRC, JUN, ATM, TNF, PGR, EGFR, PTEN) must match exact case, so "Jun 2025" is not JUN. Other symbols, including any with a digit, match case-insensitively.
- **Drug matching.** If a drug name or alias from `drug_targets.json` appears in title, interventions or eligibility, its `target_genes` count as matched. Example: "Piqray" matches PIK3CA. Only genes in the candidate set count, because a drug target with no gene score has nothing to contribute.
- **Biomarker gene.** Any biomarker alias (HER2, HER-2, HER2/neu, ...) counts as a mention of the biomarker gene. That gene stays in `matched_genes` so the UI can show its chip, but it never counts toward `genomic_match`.
- **Mean of available genes.** `genomic_match` is the mean over the top N matched genes, or over fewer if fewer matched. A trial that matches one strong gene can therefore beat a trial that matches three slightly weaker ones. Revisit this when tuning (see to-do list).
- **"Required" heuristic** (`_biomarker_directness`). The check looks only at the inclusion part of the eligibility text, meaning everything before "Exclusion Criteria". Each biomarker alias found there is classed as follows:
  - *positive*: "HER2+" (a `+` right after the alias), or a status word on the same line within `STATUS_WINDOW_CHARS` (25). Status words are positive, overexpress, amplif, low or ultralow, IHC, ISH/FISH/CISH, and 0+ to 3+.
  - *negated*: "HER2-negative", "HER2 negative", "HER2-", or a negation between the alias and its status word ("HER2 not overexpressed", "HER2 non-amplified", "HER2 status negative by IHC").
  - Neither, if "equivocal" or "ineligible" comes before the status word.

  Aliases are matched longest first, so "HER2/neu-negative" is caught.
  - **Decided per trial.** A trial is *required* (1.0) if at least one occurrence is positive and none is negated. One stray positive-looking line in a HER2-negative trial does not flip it. For example, NCT07137871 says "HR+, HER2 negative" and also "If HER2 overexpression is equivocal by IHC"; it scores 0.5.
  - **HER2-low exception.** A positive "low"/"ultralow" occurrence makes the trial *required* even next to "HER2-negative". HER2-low is defined as a subset of HER2-negative, and those trials do select on HER2 status.
  - Why negation matters: the first live sample returned two HR+/HER2-negative trials. A trial that requires HER2-negative disease scores as *mentioned* (0.5), not *required*.
  - Trade-off: a multi-cohort trial with both a HER2-positive and a HER2-negative cohort (for example, NCT06625775) also scores as *mentioned*.
  - Known miss: phrasing that puts the status word first ("positive for HER2") falls back to *mentioned*.
- **mock_inputs** on each ranking lists `"trials"` if the trial is mock. It lists `"gene_candidates"` or `"genomic_context"` if the row for any matched gene, the biomarker gene included, is mock. The dashboard shows a mock tag whenever this list is not empty.
- **No cache in scoring.** `refresh` is accepted for the common interface but does nothing. Scoring has no network calls, and a cached score could only ever be stale.

## Status

Done
- [x] ClinicalTrials.gov v2 client, with field paths checked live (2 studies, not saved)
- [x] Stage 5 cache-first, `--refresh` with fallback, mock snapshot built to exercise every scoring branch
- [x] Stages 4 and 6 per `AGENTS.md` section 5, with every weight from `config.py`
- [x] `run.py` with `--refresh` and `--from-stage N`, importing each stage module lazily
- [x] Offline smoke tests for stages 5 and 4+6
- [x] Dry run of stages 4 and 6 on the current upstream files (lane A candidates, lane B genomic context, mock trials), output sent to a scratch folder

To do
- [ ] **Take the real snapshot** (team decides when): `.venv/bin/python -m backend.pipeline.trials --refresh`, check it, commit `data/cache/trials.json`. Settings are in `backend/config.py` (`TRIALS_*`): 200 studies max, `RECRUITING` and `NOT_YET_RECRUITING` only.
- [ ] After the snapshot, read the top 10 rankings by hand and adjust the "required" heuristic if needed (for example, add "positive for HER2")
- [ ] Tune weights in `config.py` (`AGENTS.md` open question: are 0.5/0.5 and 0.4/0.6 acceptable?)
- [ ] Decide whether `genomic_match` should reward breadth, for example dividing by `TOP_N_MATCHED` even when fewer genes matched
- [x] `STATUS_WINDOW_CHARS` and the snapshot settings moved into `config.py`
- [x] ClinicalTrials.gov eligibility text is unescaped (the API returns backslash-escaped Markdown such as `HER2\-negative`), so the directness regexes see plain text

## How to run

```bash
.venv/bin/python -m backend.pipeline.trials             # use trials.json; write the mock if none exists
.venv/bin/python -m backend.pipeline.trials --refresh   # take a real ClinicalTrials.gov snapshot
.venv/bin/python -m backend.pipeline.scoring            # stage 4 then stage 6, always recomputed
.venv/bin/python -m backend.pipeline.run                # stages 1-6, cache first
.venv/bin/python -m backend.pipeline.run --from-stage 4 # rescore after an upstream change
.venv/bin/python -m pytest tests/test_trials.py tests/test_scoring.py -q
```

## Handoff

- **From lane B (genomic, stage 3):** stage 4 reads `GenomicContext.model_score` for each candidate `gene`, using `gene` as the join key. It min-max normalises that score across the candidates into `GeneScore.model_score`. Lane B's normalisation is internal, so higher must mean "more relevant to the biomarker context". `None` means "could not score" and becomes 0.0. Any row with `source: "mock"` shows up in `mock_inputs` for every trial that matches that gene. After lane B updates `genomic_context.json`, run `run --from-stage 4`.
- **From lane A (stages 1 and 2):** `literature_score` counts the unique `paper_ids` on each candidate row. IDs not found in `papers.json` are still counted, and a warning is printed.
- **To lane D (dashboard):** `data/output/rankings.json` is the only file the dashboard needs. Each row has `rank`, `trial_score`, `biomarker_directness`, `genomic_match`, `matched_genes` (sorted by `combined_score`, with the biomarker gene included for its chip, each with `paper_ids`), `source`, and `mock_inputs`. Show a mock tag when `mock_inputs` is not empty. Mock trials have `url: ""`, so do not render a link for them. For the per-gene evidence drawer, use `gene_scores.json` for literature, model and combined scores, and `papers.json` for paper titles and links.
