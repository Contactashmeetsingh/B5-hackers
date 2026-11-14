# Lane B: Genomic model (stage 3)

**Owner:** Contactashmeetsingh

**Status, 2026-11-14:**
- **Done:** all 7 GI tasks (v1) on real model output, 30/30 genes, 0 mocks. The tasks are expression, find genes + expression, promoter, chromatin, enhancer, splice and annotation. The committed `genomic_context.json` and today's `rankings.json` are built from it.
- **Done:** GI vs Keenable comparison, as PoC 3 (`poc/compare_glm_vs_keenable.py` → `data/output/glm_vs_keenable.md`). The rank correlation is about 0, so the two are complementary signals.
- **Next:** add per-task scores to the ranking rows.

Lane B asks the Genomic Intelligence (GI) DNA language models what the genome says about each candidate gene, and turns the answers into a `model_score` in [0, 1]. Stage 4 blends that score 50/50 with the literature (Keenable) evidence.

## How it fits the system

```mermaid
flowchart LR
    A["Lane A<br/>gene_candidates.json"] --> B["Lane B: genomic.py<br/>(7 GI tasks via MCP)"]
    E["Ensembl REST<br/>coords, canonical TSS, exons"] --> B
    B --> GC["genomic_context.json<br/>model_score + model_output"]
    B --> RAW["genomic_raw/&lt;GENE&gt;.json<br/>per-gene call digest"]
    B -. optional .-> AMP["amplicon_context.json<br/>genes around ERBB2"]
    GC --> C4["Lane C: scoring.run_gene_scores<br/>combined = 0.5 lit + 0.5 model"]
    C4 --> C6["Lane C: trial ranking"]
    GC --> D["Lane D: evidence drawer<br/>GET /api/genes/{gene}"]
    AMP -. context .-> D
```

| | |
|---|---|
| Reads | `data/cache/gene_candidates.json` (lane A), `data/input/biomarker.json` (`model_context` block) |
| Writes | `data/cache/genomic_context.json` (contract in `AGENTS.md` §4) |
| Also writes | `data/cache/genomic_raw/<GENE>.json`, `data/cache/amplicon_context.json`, `data/cache/ensembl_genes.json` |
| Files owned | `backend/clients/genomic_intelligence.py`, `backend/clients/ensembl.py`, `backend/pipeline/genomic.py`, `tests/test_genomic.py`, this folder |
| Consumed by | Lane C uses `model_score`. Lane D shows `model_output`. |

**Hand-off rules for the other lanes**

- **Lane A:** add or remove genes in `gene_candidates.json`, then re-run stage 3. Only uncached genes and tasks are sent to GI. Old HGNC symbols are fine (`SLC9A3R1` resolves to `NHERF1`).
- **Lane C:** read only `gene`, `model_score` and `source`. `model_score` is `null` on mock rows, so treat it as 0.0. Per-task scores are in `model_output.task_scores` (v1) if you want to show them.
- **Lane D:** everything the evidence drawer needs is in `model_output` (shape below). Show a "mock data" tag when `source == "mock"`. Per-task scores are in `model_output.task_scores` (7 keys, each [0,1] or null).
- **New biomarker:** add a row with its own `model_context`. No code change is needed.

## Run it

```bash
.venv/bin/python -m backend.pipeline.genomic             # cache first; only uncached genes/tasks hit the network
.venv/bin/python -m backend.pipeline.genomic --refresh   # re-query GI for every gene and task
.venv/bin/python -m backend.pipeline.genomic --offline   # never call the network; genes without complete output become mock rows
.venv/bin/python -m backend.pipeline.genomic --amplicon  # also scan ERBB2 ± 100 kb (context only)
.venv/bin/python -m pytest tests/test_genomic.py -q      # offline smoke test
.venv/bin/python lanes/B-genomic/sanity_check.py         # biology sanity checks -> sanity_check.json
```

No key is needed. The hosted MCP server at `https://mcp.genomicintelligence.ai/mcp` answers on a shared demo key, which has shared rate limits and is for evaluation only. Put `GI_API_KEY=gi_...` in `.env` to use your own key on the same server; to request one, email contact@genomicintelligence.ai. The v1 run is slow on the demo key: about 30–60 s per gene, mostly the gene finder. `GI_WORKERS` in `config.py` sets how many genes run in parallel.

## What the model is asked, per gene (v1: every GI task)

Everything is anchored on the gene's canonical transcription start site (TSS). The TSS comes from Ensembl and is cross-checked against GI (`locus.tss_matches_ensembl`).

| Task (model) | Input | Readout | Task score |
|---|---|---|---|
| **expression** (`g0-expression-8192`) | GI's TSS-centred 81,920 bp, gene-sense | log(TPM+1) with description `"HER2-positive breast cancer cell line"`, and specificity = that minus the `"liver tissue"` prediction | 0.5 × minmax(level) + 0.5 × minmax(specificity) |
| **composite** (find genes + expression) | TSS ± 40 kb, plus strand | expression of the transcript the gene finder itself places at the canonical TSS | minmax; none if the finder misses the TSS |
| **promoter** (`g0-promoter-2000bp`) | TSS ± 1 kb, gene-sense | max promoter probability | as-is (a probability) |
| **chromatin** (`g0-deepsea`) | TSS ± 1 kb | DeepSEA features called (≥ 0.5) in breast-lineage cells (HMEC, MCF-7, T-47D) | minmax |
| **enhancer** (`g0-deepstarr`) | TSS ± 1 kb, gene-sense | peak developmental/housekeeping activity | minmax. **Caveat:** this model is trained on fruit-fly DNA. Set its weight to 0 if judges object. |
| **splice** (`g0-splice-bigbird`) | TSS → TSS + 15 kb, gene-sense | share of the canonical transcript's splice junctions (from Ensembl exons) that the model calls within 10 bp | as-is (a fraction); none if the window has no junction |
| **annotation** (`g0-annotation`) | TSS ± 40 kb, plus strand | confidence of the transcript the gene finder places within 1 kb of the canonical TSS | as-is (a probability); 0 if the finder misses the gene |

```
model_score = weighted mean of the task scores the gene has     (W_GI_TASK in config.py, 1.0 each)
```

Probabilities and fractions are used as-is. Unbounded readouts are min-max normalised across the candidate set. A task with no readout for a gene, such as splice on a single-exon gene, is left out of that gene's mean rather than counted as 0. The weights and windows live in `backend/config.py` (`W_GI_TASK`, `W_EXPR_*`, `GI_*_BP`). The context strings live in `data/input/biomarker.json` → `model_context`.

**In one sentence for judges:** a gene scores high when the DNA models agree it looks like a well-formed, active gene in HER2-positive breast cells. That means expressed (more than in liver), with an open promoter and enhancer-like activity at its start site, and a structure the splice and gene-finder models recognise.

### v0 (superseded)

The first run scored three components: expression and specificity (as above), and regulatory = 0.5 × promoter + 0.5 × minmax(chromatin). v1 replaced it. The v0 numbers are still in each gene's `genomic_raw` digest.

### Model ids are resolved, not hard-coded

Each run asks GI for every task's current `default_model` and passes it on every call, so a run never straddles a default change. The ids are recorded in `model_output.models` and in `model_task`.

## `model_output` shape (v1, what lane D can render)

```jsonc
{
  "summary": "one sentence with the key numbers",
  "task_scores": { "expression": 0.0, "composite": 0.0, "promoter": 0.0, "chromatin": 0.0,
                   "enhancer": 0.0, "splice": 0.0, "annotation": 0.0 },          // [0,1] or null
  "task_raw":    { "expression_level": 0.0, "expression_specificity": 0.0, "composite": 0.0, "promoter": 0.0,
                   "chromatin": 0, "enhancer": 0.0, "splice": 0.0, "annotation": 0.0 },
  "tasks_used": ["..."], "weights": { "task.expression": 1.0, "...": 1.0 },
  "locus": { "ensembl_id", "chrom", "strand", "tss", "tss_source", "tss_matches_ensembl",
             "expression_window", "tss_window", "splice_window", "annotation_window" },
  "expression": { "target": { "description", "log_tpm", "tpm", "scored_window", "request_id" }, "reference": { "..." } },
  "composite":  { "description", "genes_found", "found_at_tss", "log_tpm", "distance_to_canonical_tss_bp", "request_id" },
  "promoter":   { "max_probability", "upstream_window_probability", "request_id" },
  "chromatin":  { "threshold", "on_tissue_cell_types", "on_tissue_labels_called", "on_tissue_by_feature", "top_on_tissue_calls", "request_id" },
  "enhancer":   { "dev_score_max", "hk_score_max", "dev_score_mean", "hk_score_mean", "request_id" },
  "splice":     { "junctions_in_window", "junctions_recovered", "recall", "sites_called", "precision", "request_id" },
  "annotation": { "transcripts_found", "found_at_tss", "confidence", "transcript_type", "distance_to_canonical_tss_bp", "request_id" },
  "models": { "expression": "g0-expression-8192", "...": "..." }, "retrieved": "2026-11-14", "demo_key": true
}
```

A mock row has `source: "mock"`, `model_score: null` and `model_output: {"error": "..."}`. No number is ever invented. Every real number carries the GI `request_id` that produced it.

## Evidence that the signal behaves like biology

From `sanity_check.json` and the runs so far, all on 2026-11-14 on the demo key. These are checks for the demo story, not a validation of the method.

- **Tissue control works:** ALB, a liver gene, scores 9.69 in "liver tissue" and 0.52 in the HER2+ breast context. HBB scores 3.53 vs 0.74. ERBB2 scores 3.17 in breast vs 1.87 in liver.
- **Deterministic:** the same request twice gives the same value (ERBB2: 3.168 and 3.168).
- **Strand handling is right:** for 5 of 6 minus-strand genes, the gene-sense TSS window looks more promoter-like than its reverse complement. JUN is the exception; it is a single-exon gene with a CpG-island promoter.
- **The splice model recovers real gene structure:** for ERBB2, all 17 canonical splice junctions in the first 15 kb were called, with no extra sites. Across the 30 genes, 25 had every junction in their window recovered. IGF1R's single junction in the window was missed, because the model called no sites there. JUN is single-exon, so it has no splice readout.
- **The gene finder rediscovers the 17q12 amplicon** (`amplicon_context.json`, ERBB2 ± 100 kb). It found 9 transcripts with TSSs within 1 bp of ERBB2's canonical TSS, 21 bp of GRB7's, 18 bp of PGAP3's and 8 bp of MIEN1's, plus transcripts within 600 bp of TCAP and PNMT. It missed STARD3, NEUROD2 and PPP1R1B, whose TSSs are inside the window.
- **The gene finder is gene-dependent.** It finds ERBB2, GRB7 and HSP90AA1 with high confidence, but misses STAT3, EZR and PIK3CA in their ± 40 kb windows. A window spanning the whole transcript did no better on 5 test genes. Read a low annotation score as "the model did not recognise this locus", not as biology. Across all 30 genes the gene finder placed a transcript at the canonical TSS for 19.
- **Description wording matters.** Bare cell-line names gave unreliable numbers: `"MCF-7"` gave ESR1 0.16, which is wrong for an ER+ line. We use full phrases and keep them fixed across runs, as GI's docs advise.

## Known limits (say these out loud if asked)

- The models read the **reference genome**. They score a gene's baseline regulatory potential in a context, not a patient's tumour. They cannot see HER2 amplification or copy number.
- Context strings are free text that conditions the model, not a controlled vocabulary. A different wording gives different numbers. Compare only runs that use the same strings.
- The enhancer model is *Drosophila*-trained (DeepSTARR). Its human scores are relative signal at best.
- The absolute values are noisy. GAPDH, a housekeeping gene, scores 1.67 in "liver tissue". Read scores as relative, within this candidate set.
- The demo key shares quota with other evaluators. If it rate-limits, the client backs off and retries. Persistent failure produces mock rows and the run continues.
- Min-max normalisation is relative to the current candidate set, so adding genes can shift every score.

## Status

- [x] GI client over hosted MCP (session handling, retries on GI's transient error codes, optional key)
- [x] Ensembl client (symbol → ID, coordinates, canonical TSS, exons, old-symbol fallback)
- [x] v0: stage 3 on real model output for all 30 literature genes (expression, promoter, chromatin)
- [x] v1 code: all 7 GI tasks, per-task scores, per-gene and per-task cache, parallel workers, smoke test updated
- [x] Optional amplicon scan around the biomarker gene, labelled with Ensembl genes
- [x] Biology sanity checks (`sanity_check.py`)
- [x] **v1 full run:** 30/30 genes with all 7 tasks, committed, and stages 4–6 re-run
- [ ] **Per-task scores in the ranking:** add `model_task_scores` to `gene_scores.json` and `matched_genes`, plus a per-trial breakdown of which task drove `genomic_match`. This touches lane C's `scoring.py` and `backend/schemas.py`, so agree it with lane C.
- [x] **Compare GI with Keenable** (PoC 3): `poc/compare_glm_vs_keenable.py` writes `data/output/glm_vs_keenable.{json,md}`, with the Spearman correlation overall and per task and the agreement quadrants. There is no API endpoint, because the UI is parked.
- [ ] Get our own `GI_API_KEY` for private quota (same code path)
- [ ] Decide with the team whether `"liver tissue"` is the best reference context, and whether to keep the enhancer task
- [ ] Later: GI's `genomic-variant-interpretation` workflow scores patient VCF variants near TSSs. It is REST-only and not finished on GI's side, but it is the path from "reference genome" to "this patient".
