# HER2 candidate genes ranked by Genomic Intelligence DNA context

The 30 HER2 candidate genes ranked by **DNA context only**: the promoter and chromatin models. **Expression predictions are left out on purpose.**

- **Data:** `data/cache/genomic_context.json` on branch `lane-b/genomic-poc` (commit `ee33e9d`). These are GI v0 results, retrieved 2026-11-14 on the shared demo key. No new GI calls were made for this table.
- **Models:** `g0-promoter-2000bp` (promoter) and `g0-deepsea` (chromatin, DeepSEA). Both read the DNA within ±1 kb of each gene's canonical start site (TSS).
- **Score:** `0.5 × promoter probability + 0.5 × minmax(chromatin calls)`. This is the branch's `regulatory` component, and I recomputed it for all 30 genes with 0 mismatches.
- **Chromatin calls:** DeepSEA features called at ≥ 0.5 in breast-lineage cells (HMEC, MCF-7, T-47D). Across these genes they range from 9 to 56.
- **Tiers:** high ≥ 0.82 (top third), middle 0.615–0.82, low < 0.615.
- **Literature evidence:** from [`keenable/her2_interactors_experimental.md`](../keenable/her2_interactors_experimental.md).
- **Per-gene detail:** [`her2_genes_dna_context_ranking.csv`](her2_genes_dna_context_ranking.csv) has every feature count plus the GI `request_id` behind each number.

## High

| Rank | Gene | DNA-context score | Promoter prob. | Chromatin calls | H3K27ac / Pol2 | Literature evidence |
|---|---|---|---|---|---|---|
| 1 | **PSMD3** | 0.988 | 0.976 | 56 | 5 / 7 | functional |
| 2 | **STAT3** | 0.920 | 0.988 | 49 | 5 / 6 | functional |
| 3 | **ATM** | 0.913 | 0.974 | 49 | 5 / 7 | physical + functional |
| 4 | **HSP90AA1** | 0.886 | 0.984 | 46 | 4 / 7 | physical + functional |
| 5 | **PTPN1** | 0.857 | 0.991 | 43 | 5 / 6 | functional |
| 6 | **STARD3** | 0.846 | 0.990 | 42 | 4 / 7 | functional |
| 7 | **PGAP3** | 0.836 | 0.949 | 43 | 5 / 6 | functional |
| 8 | **PIK3CA** | 0.835 | 0.989 | 41 | 5 / 5 | functional |
| 9 | **ERBIN** | 0.828 | 0.975 | 41 | 3 / 7 | physical + functional |
| 10 | **MEMO1** | 0.824 | 0.989 | 40 | 4 / 7 | physical + functional |

## Middle

| Rank | Gene | DNA-context score | Promoter prob. | Chromatin calls | H3K27ac / Pol2 | Literature evidence |
|---|---|---|---|---|---|---|
| 11 | **SLC9A3R1** | 0.781 | 0.988 | 36 | 3 / 6 | physical + functional |
| 12 | **ERBB3** | 0.774 | 0.930 | 38 | 0 / 5 | physical + functional |
| 13 | **EZR** | 0.772 | 0.990 | 35 | 4 / 6 | physical + functional |
| 14 | **STUB1** | 0.727 | 0.858 | 37 | 2 / 6 | functional |
| 15 | **IGF1R** | 0.689 | 0.953 | 29 | 2 / 3 | physical + functional |
| 16 | **VAV2** | 0.678 | 0.974 | 27 | 0 / 3 | functional |
| 17 | **PTEN** | 0.669 | 0.721 | 38 | 5 / 5 | functional |
| 18 | **SRC** | 0.643 | 0.988 | 23 | 2 / 2 | functional |
| 19 | **ERBB2** | 0.622 | 0.988 | 21 | 1 / 2 | biomarker |
| 20 | **EGFR** | 0.615 | 0.975 | 21 | 0 / 2 | physical + functional |

## Low

| Rank | Gene | DNA-context score | Promoter prob. | Chromatin calls | H3K27ac / Pol2 | Literature evidence |
|---|---|---|---|---|---|---|
| 21 | **SHC1** | 0.609 | 0.919 | 23 | 0 / 2 | physical + functional |
| 22 | **TNF** | 0.589 | 0.901 | 22 | 2 / 2 | functional |
| 23 | **ITGB4** | 0.569 | 0.989 | 16 | 0 / 2 | physical + functional |
| 24 | **ESR1** | 0.569 | 0.946 | 18 | 1 / 0 | functional |
| 25 | **CDCP1** | 0.558 | 0.989 | 15 | 0 / 1 | physical + functional |
| 26 | **GRB7** | 0.551 | 0.975 | 15 | 0 / 2 | physical + functional |
| 27 | **JUN** | 0.550 | 0.312 | 46 | 5 / 6 | functional |
| 28 | **PGR** | 0.509 | 0.868 | 16 | 0 / 0 | physical + functional |
| 29 | **MUC4** | 0.472 | 0.944 | 9 | 0 / 0 | functional |
| 30 | **ERBB4** | 0.471 | 0.773 | 17 | 0 / 1 | functional |

## How to read it

- **Chromatin drives the ranking.** 26 of the 30 genes have a promoter probability above 0.85, so the promoter model barely separates them.
- **High scores favor genes that are active everywhere.** PSMD3, HSP90AA1, STAT3 and ATM are broadly expressed, so their start sites look open in most epithelial cells. A high score does not make a gene HER2-specific.
- **3 of the top 7 are on the 17q12 amplicon with ERBB2:** PSMD3, STARD3 and PGAP3. That matches the co-amplification literature (PMID 23253899). The models read the **reference genome**, so they cannot see the amplification itself.
- **ERBB2 ranks 19th.** It has a strong promoter (0.988) but only 21 chromatin calls. The reference genome has no extra HER2 copies, and those copies are what define HER2+ disease.
- **JUN is an outlier:** promoter 0.312 but 46 chromatin calls. The lane B README notes the promoter model misreads this single-exon gene.
- **H3K4me3 is 0 for every gene,** probably because that mark is grouped under "Other". Treat the zeros as uninformative.

Research prototype; not for medical decisions.
