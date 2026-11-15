/** Architecture v2 API contracts. Model readouts are not relevance scores. */
export const MOCK = "mock";
export interface ProfileBiomarker {
  biomarker: string;
  gene: string;
  alteration: string;
  status: string;
  variant: string | null;
  aliases: string[];
}
export interface Profile {
  tissue: string;
  biomarkers: ProfileBiomarker[];
  sequence_gene: string;
}
export interface Paper {
  paper_id: string;
  title: string;
  year: number | null;
  url: string;
  genes_mentioned?: string[];
  relation: string;
  source: string;
  reviewed?: boolean | null;
  opposite_status?: string[];
  why?: string[];
}
export interface GeneCandidate {
  gene: string;
  ensembl_id: string | null;
  in_targets_dataset: boolean;
  paper_ids: string[];
  source: string;
}
export interface GenomicModelOutput {
  summary?: string;
  task_scores?: Record<string, number | null>;
  task_raw?: Record<string, unknown>;
  tasks_used?: string[];
  [key: string]: unknown;
}
export interface GenomicContext {
  gene: string;
  assembly: string;
  region: string;
  model_task: string;
  model_output: GenomicModelOutput;
  model_score: number | null;
  source: string;
}
export interface BiomarkerMatch {
  biomarker: string;
  gene: string;
  status: string;
  requirement: "required" | "mentioned" | "conflicts" | "absent";
  evidence_text: string;
  via_drugs: string[];
}
export interface TrialMatch {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  url: string;
  tier: string;
  tier_rank: number;
  tier_label: string;
  biomarker_matches: BiomarkerMatch[];
  drugs: {
    drug: string;
    matched_name: string;
    target_genes: string[];
    source: string;
  }[];
  related_genes: { gene: string; how: string[]; paper_ids: string[] }[];
  unchecked_criteria: string[];
  supporting_papers: Paper[];
  supporting_papers_total: number;
  explanation: string;
  evidence_type: string;
  source: string;
  mock_inputs: string[];
  eligibility_text?: string;
  sponsor?: string;
  status_detail?: string;
  status_as_of?: string;
  status_caveat?: string;
}
export interface GeneDetail {
  gene: string;
  candidate: GeneCandidate | null;
  genomic_context: GenomicContext | null;
  papers: Paper[];
  mock_inputs: string[];
}
export interface Meta {
  has_mock_data: boolean;
  mock_inputs: string[];
  disclaimer: string;
}
export interface Health {
  status: string;
  files: Record<string, boolean>;
}
export interface ApiErrorDetail {
  message: string;
  contract?: string;
  file?: string;
  stage?: string;
  run?: string;
}
export interface GeneDrugOption {
  gene: string;
  association: string;
  profile_status: string;
  drug_class: string;
  drugs: { drug: string; aliases: string[] }[];
  drug_footnote: string;
  trials: string[];
  trial_note: string;
  paper_ids: string[];
  source: string;
}
export interface ResearchData {
  profile: Profile;
  meta: Meta;
  health: Health;
  trials: TrialMatch[];
  papers: Paper[];
  genes: GeneCandidate[];
  contexts: GenomicContext[];
  gene_drugs?: GeneDrugOption[];
}
