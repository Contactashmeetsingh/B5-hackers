// TypeScript mirror of backend/schemas.py (the stage contracts in AGENTS.md section 4)
// plus the API-only views in backend/app/main.py (GeneDetail, Meta, Health).
// If a pydantic model changes, change it here too. Backend rows allow extra keys,
// so any field not listed here may still be present at runtime.

/** Value of `source` on any row that is not real data. Show the "mock data" tag. */
export const MOCK = "mock";

// ---------------------------------------------------------------- stage 0 input
export interface ModelContext {
  expression_target: string;
  expression_reference: string;
  chromatin_cell_types: string[];
}

export interface Biomarker {
  tissue: string;
  biomarker: string; // e.g. "HER2"; always read it from the API, never hard-code it
  gene: string; // e.g. "ERBB2"
  measurement: string;
  source_field: string;
  coverage: string;
  aliases: string[];
  model_context: ModelContext;
}

export interface DrugTarget {
  drug: string;
  aliases: string[];
  target_genes: string[];
  source: string;
}

// ---------------------------------------------------------------- stage 1
export interface Paper {
  paper_id: string; // PMID or DOI
  title: string;
  year: number | null;
  url: string;
  genes_mentioned: string[];
  relation: string; // one paraphrased sentence, never an abstract
  source: string; // "kleenable" | "mock"
}

// ---------------------------------------------------------------- stage 2
export interface GeneCandidate {
  gene: string;
  ensembl_id: string | null;
  in_targets_dataset: boolean;
  paper_ids: string[];
  source: string; // "kleenable" | "mock"
}

// ---------------------------------------------------------------- stage 3
// TODO(lane D + lane B): confirm against lanes/B-genomic/README.md, which owns the
// shape of model_output written by backend/pipeline/genomic.py. The optional fields
// below are the top-level keys seen in data/cache/genomic_context.json at scaffold
// time; everything stays optional so a shape change cannot crash the drawer.
export interface GenomicModelOutput {
  summary?: string; // one human-readable line per gene
  components?: Record<string, number>; // normalised [0, 1]: expression, specificity, regulatory
  raw?: Record<string, number>; // un-normalised model values behind the components
  weights?: Record<string, number>; // how components combine into model_score
  [key: string]: unknown; // per-task detail (locus, expression, promoter, chromatin, request ids)
}

export interface GenomicContext {
  gene: string;
  assembly: string; // "GRCh38"
  region: string; // "chr17:39687914-39730426", gene body, 1-based inclusive
  model_task: string;
  model_output: Record<string, unknown>; // cast to GenomicModelOutput once it is typed
  model_score: number | null; // [0, 1]; null only when the gene could not be scored
  source: string; // "genomic_intelligence" | "mock"
}

// ---------------------------------------------------------------- stage 4
export interface GeneScore {
  gene: string;
  literature_score: number;
  model_score: number;
  combined_score: number;
}

// ---------------------------------------------------------------- stage 5
export interface Trial {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  url: string;
  conditions: string[];
  interventions: string[];
  eligibility_text: string;
  source: string; // "clinicaltrials.gov snapshot" | "mock"
}

// ---------------------------------------------------------------- stage 6
export interface MatchedGene {
  gene: string;
  combined_score: number;
  paper_ids: string[];
}

export interface Ranking {
  rank: number;
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  url: string;
  trial_score: number;
  biomarker_directness: number;
  genomic_match: number;
  matched_genes: MatchedGene[];
  source: string; // the trial's own source, copied from trials.json
  /** Upstream inputs behind this row that are mocks, e.g. ["trials", "genomic_context"]. */
  mock_inputs: string[];
}

// ---------------------------------------------------------------- API-only views
/** GET /api/genes/{gene}: everything the evidence drawer shows for one gene. */
export interface GeneDetail {
  gene: string;
  score: GeneScore | null;
  candidate: GeneCandidate | null;
  genomic_context: GenomicContext | null;
  papers: Paper[]; // the papers behind literature_score
  mock_inputs: string[];
}

/** GET /api/meta: global mock flag, disclaimer and the scoring weights from config.py. */
export interface Meta {
  has_mock_data: boolean;
  mock_inputs: string[];
  disclaimer: string;
  weights: {
    W_LIT: number;
    W_MODEL: number;
    W_DIRECT: number;
    W_GENOMIC: number;
    LIT_SATURATION: number;
    TOP_N_MATCHED: number;
  };
}

/** GET /api/health: which contract files exist. */
export interface Health {
  status: "ok";
  files: Record<string, boolean>;
}

/** Body of a 503 (stage not run yet) or 500 (malformed file) error. */
export interface ApiErrorDetail {
  message: string;
  contract?: string;
  file?: string;
  stage?: string;
  run?: string;
}
