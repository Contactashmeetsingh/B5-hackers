"""Paths, weights and service settings for the pipeline.

Every tunable number lives here (AGENTS.md section 5). Pipeline functions import
these names; they never hard-code a weight.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # .env is optional; keys are read from the environment either way.
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"

BIOMARKER_PATH = INPUT_DIR / "biomarker.json"
DRUG_TARGETS_PATH = INPUT_DIR / "drug_targets.json"

PAPERS_PATH = CACHE_DIR / "papers.json"                    # stage 1
GENE_CANDIDATES_PATH = CACHE_DIR / "gene_candidates.json"  # stage 2
GENOMIC_CONTEXT_PATH = CACHE_DIR / "genomic_context.json"  # stage 3
GENE_SCORES_PATH = CACHE_DIR / "gene_scores.json"          # stage 4
TRIALS_PATH = CACHE_DIR / "trials.json"                    # stage 5
RANKINGS_PATH = OUTPUT_DIR / "rankings.json"               # stage 6

# Stage 3 keeps every raw Genomic Intelligence response, one file per gene, so a
# re-run never re-spends quota and every score can be traced to a request_id.
GI_RAW_DIR = CACHE_DIR / "genomic_raw"
# Optional stage 3 extra: genes found in the biomarker's own amplicon region.
AMPLICON_CONTEXT_PATH = CACHE_DIR / "amplicon_context.json"

# ---------------------------------------------------------------- gene level (stage 4)
LIT_SATURATION = 5      # papers needed for literature_score = 1.0
W_LIT = 0.5             # combined_score weight on literature_score
W_MODEL = 0.5           # combined_score weight on model_score

# ---------------------------------------------------------------- trial level (stage 6)
W_DIRECT = 0.4          # trial_score weight on biomarker_directness
W_GENOMIC = 0.6         # trial_score weight on genomic_match
TOP_N_MATCHED = 3       # genomic_match = mean combined_score of the top N matched genes
DIRECTNESS_REQUIRED = 1.0   # biomarker status is an eligibility requirement
DIRECTNESS_MENTIONED = 0.5  # biomarker only mentioned
DIRECTNESS_ABSENT = 0.0
STATUS_WINDOW_CHARS = 25    # "required" heuristic: max chars after a biomarker alias (same line) for a status word

# ---------------------------------------------------------------- trial snapshot (stage 5)
TRIALS_CONDITION_TEMPLATE = "{tissue} Cancer"                  # ClinicalTrials.gov query.cond
TRIALS_PAGE_SIZE = 100
TRIALS_MAX_STUDIES = 200
TRIALS_STATUSES = ["RECRUITING", "NOT_YET_RECRUITING"]         # only trials a user could still join

# ---------------------------------------------------------------- Keenable (stages 1 and 2)
KEENABLE_API_KEY = os.getenv("KEENABLE_API_KEY") or None

# ---------------------------------------------------------------- Genomic Intelligence (stage 3)
# Transport: the hosted MCP server. It answers anonymously on a shared demo key;
# set GI_API_KEY in .env to use your own key and caps instead.
GI_MCP_URL = os.getenv("GI_MCP_URL", "https://mcp.genomicintelligence.ai/mcp")
GI_API_KEY = os.getenv("GI_API_KEY") or None
GI_TIMEOUT_S = 240.0
GI_MAX_RETRIES = 4
GI_BACKOFF_CAP_S = 30.0
GI_SPECIES = "human"
GI_ASSEMBLY = "GRCh38"

# model_score is built from one readout per Genomic Intelligence task, each
# measured at the gene's canonical TSS (see backend/pipeline/genomic.py):
#   expression  predicted log(TPM+1) in the target context, blended with
#               specificity (target minus reference context)
#   composite   find genes + expression: expression of the transcript the gene
#               finder itself places at the canonical TSS
#   promoter    promoter probability, TSS +/- 1 kb
#   chromatin   DeepSEA features called in on-tissue (breast-lineage) cells
#   enhancer    peak enhancer activity (DeepSTARR; Drosophila-trained, see README)
#   splice      share of the canonical transcript's splice junctions recovered
#   annotation  confidence of the gene finder's transcript at the canonical TSS
# Probabilities and fractions are used as-is; unbounded readouts are min-max
# normalised across the candidate set. model_score is the weighted mean over the
# tasks that produced a readout for that gene. Set a weight to 0 to drop a task.
W_GI_TASK = {
    "expression": 1.0,
    "composite": 1.0,
    "promoter": 1.0,
    "chromatin": 1.0,
    "enhancer": 1.0,
    "splice": 1.0,
    "annotation": 1.0,
}
W_EXPR_LEVEL = 0.5        # inside the expression task: predicted level in the target context
W_EXPR_SPECIFICITY = 0.5  # inside the expression task: target minus reference context

# Sequence windows (gene-sense unless noted), all anchored on the canonical TSS.
# Promoter, chromatin, enhancer: [TSS - H, TSS + H) with H below. 2 kb matches the
# promoter model's window and covers two chromatin windows.
GI_TSS_HALF_WINDOW_BP = 1000
GI_SPLICE_WINDOW_BP = 15_000        # TSS downstream, = the splice model's context window
GI_SPLICE_TOLERANCE_BP = 10         # a called site within this of a junction counts as recovered
# Gene finder + composite: TSS +/- 40 kb, plus strand. A fixed size keeps the readout
# comparable across genes. (Tried "canonical transcript + 5 kb" on 5 genes: no better;
# the finder's sensitivity is gene-dependent either way, see lanes/B-genomic/README.md.)
GI_ANNOTATION_HALF_BP = 40_000
GI_TSS_MATCH_TOLERANCE_BP = 1_000   # a predicted TSS within this of the canonical TSS "finds" the gene
GI_WORKERS = 3                      # genes queried in parallel (shared demo key: keep small)

# Optional amplicon scan: genes found and scored in this many bp on each side of
# the biomarker gene's TSS (composite workflow; above 50 kb it runs async).
GI_AMPLICON_HALF_WIDTH_BP = 100_000

# ---------------------------------------------------------------- Ensembl REST
ENSEMBL_REST_URL = "https://rest.ensembl.org"
ENSEMBL_TIMEOUT_S = 30.0
ENSEMBL_CACHE_PATH = CACHE_DIR / "ensembl_genes.json"
