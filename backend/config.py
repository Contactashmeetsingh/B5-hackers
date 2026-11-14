"""Paths and service settings for the pipeline.

Every tunable setting lives here. Pipeline functions import these names; they
never hard-code one. The old trial/gene scoring weights were removed with the
scoring system (AGENTS.md section 5).
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

PROFILE_PATH = INPUT_DIR / "profile.json"            # the biomarker profile (HER2 + PIK3CA)
BIOMARKER_PATH = INPUT_DIR / "biomarker.json"        # model conditioning for the sequence gene (ERBB2)
DRUG_TARGETS_PATH = INPUT_DIR / "drug_targets.json"
GENE_TERMS_PATH = INPUT_DIR / "gene_terms.json"      # clinical words for genes: ER -> ESR1, HR -> ESR1 + PGR
TRIALS_SPREADSHEET_PATH = ROOT / "clinical_trials" / "her2_candidate_marker_open_trials.xlsx"
ATLAS_PATH = ROOT / "pancancer_atlas" / "her2_dependence_tcga_pancan.csv"  # TCGA PanCancer Atlas table

PAPERS_PATH = CACHE_DIR / "papers.json"                    # stage 1
GENE_CANDIDATES_PATH = CACHE_DIR / "gene_candidates.json"  # stage 2
TRIALS_PATH = CACHE_DIR / "trials.json"                    # stage 3
GENOMIC_CONTEXT_PATH = CACHE_DIR / "genomic_context.json"  # stage 5

TRIAL_MATCHES_PATH = OUTPUT_DIR / "trial_matches.json"          # stage 4, Approach 1 result
GENE_ASSOCIATIONS_PATH = OUTPUT_DIR / "gene_associations.json"  # stage 6, Approach 2 result

# Stage 5 keeps every raw Genomic Intelligence response, one file per gene, so a
# re-run never re-spends quota and every score can be traced to a request_id.
GI_RAW_DIR = CACHE_DIR / "genomic_raw"
# Stage 1 provenance: every Keenable query and the hits it returned (no snippets).
KEENABLE_QUERY_LOG_PATH = CACHE_DIR / "keenable_queries.json"
# Optional stage 5 extra: genes found in the biomarker's own amplicon region.
AMPLICON_CONTEXT_PATH = CACHE_DIR / "amplicon_context.json"

# ---------------------------------------------------------------- trials (stage 3)
# The hard-coded trial list is the curated spreadsheet (one row per trial).
TRIALS_SHEET = "Open HER2 trials"
TRIALS_NOTES_SHEET = "Notes"            # its "Data caveat" row is attached to every trial
# Optional ClinicalTrials.gov snapshot (`trials --ctgov`); not used by the demo.
TRIALS_CONDITION_TEMPLATE = "{tissue} Cancer"                  # ClinicalTrials.gov query.cond
TRIALS_PAGE_SIZE = 100
TRIALS_MAX_STUDIES = 200
TRIALS_STATUSES = ["RECRUITING", "NOT_YET_RECRUITING"]         # only trials a user could still join

# ---------------------------------------------------------------- trial matching (stage 4)
STATUS_WINDOW_CHARS = 45       # how far after the biomarker its status is read (same clause; "HER2 IHC 1+ or IHC 2+ with negative ISH")
NEGATION_LOOKBACK_CHARS = 25   # how far before it ("must not have HER2", "no evidence of a PIK3CA", "positive for HER2")
MAX_SUPPORTING_PAPERS = 6      # papers shown per trial (the total found is always reported too)

# ---------------------------------------------------------------- Keenable (stage 1)
KEENABLE_API_KEY = os.getenv("KEENABLE_API_KEY") or None
KEENABLE_BASE_URL = "https://api.keenable.ai"
KEENABLE_APP_TITLE = "biomarker-research-poc"   # X-Keenable-Title for keyless calls: a generic app name, nothing personal
KEENABLE_TIMEOUT_S = 60.0
KEENABLE_MAX_RETRIES = 3
KEENABLE_BACKOFF_CAP_S = 30.0
KEENABLE_PUBMED_SITE = "pubmed.ncbi.nlm.nih.gov"  # papers only: every hit then has a PMID
KEENABLE_MAX_RESULTS = 10                          # per query (API allows 1-50)

# ---------------------------------------------------------------- PubMed (stage 1: checks each Keenable hit)
PUBMED_TOOL = "biomarker-research-poc"   # NCBI's "tool" parameter: a generic name, no contact details
PUBMED_BATCH = 100                       # PMIDs per efetch call
PUBMED_TIMEOUT_S = 60.0
PUBMED_MAX_RETRIES = 3
PUBMED_PAUSE_S = 0.4                     # between calls; NCBI allows 3 per second without a key

# ---------------------------------------------------------------- Genomic Intelligence (stage 5)
# Transport: the hosted MCP server. It answers anonymously on a shared demo key;
# set GI_API_KEY in .env to use your own key and caps instead.
GI_MCP_URL = os.getenv("GI_MCP_URL", "https://mcp.genomicintelligence.ai/mcp")
GI_API_KEY = os.getenv("GI_API_KEY") or None
GI_TIMEOUT_S = 240.0
GI_MAX_RETRIES = 4
GI_BACKOFF_CAP_S = 30.0
GI_SPECIES = "human"
GI_ASSEMBLY = "GRCh38"

# The GI activity summary (the `model_score` field of genomic_context.json; a model
# summary only, nothing is ranked by it) is built from one readout per Genomic Intelligence task, each
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
