"""Pydantic models that mirror the stage contracts in AGENTS.md section 4.

Stages talk only through JSON files. These models are the single typed
definition of those files: every stage validates what it reads and writes
against them, so a schema drift fails loudly at the boundary.

If you change a model here, update AGENTS.md section 4 in the same commit.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

MOCK = "mock"


class _Row(BaseModel):
    # Keep unknown keys instead of dropping them, so a teammate can add a field
    # to their own stage output without breaking everyone else's reader.
    model_config = ConfigDict(extra="allow")


class _Sourced(_Row):
    source: str

    @property
    def is_mock(self) -> bool:
        return self.source == MOCK


# ---------------------------------------------------------------- stage 0 input
class ModelContext(_Row):
    """Biomarker-specific conditioning for the Genomic Intelligence models.

    Lives on the biomarker record (not in code) so a new biomarker row brings
    its own tissue context.
    """

    expression_target: str        # description string for the expression model
    expression_reference: str     # off-target context for the specificity contrast
    chromatin_cell_types: list[str]  # DeepSEA cell types that count as on-tissue


class Biomarker(_Row):
    tissue: str
    biomarker: str
    gene: str
    measurement: str
    source_field: str
    coverage: str
    aliases: list[str] = Field(default_factory=list)  # e.g. ["HER2", "ERBB2", "HER-2", "neu"]
    # AGENTS.md section 9 check: genes a working stage 1+2 should surface. Logged only.
    sanity_genes: list[str] = Field(default_factory=list)
    model_context: ModelContext


class ProfileBiomarker(_Row):
    """One biomarker of the input profile, e.g. HER2 positive or PIK3CA mutated."""

    biomarker: str                 # display name, e.g. "HER2"
    gene: str                      # HGNC symbol, e.g. "ERBB2"
    alteration: str                # what is measured: "overexpression / amplification", "mutation"
    status: str                    # the profile's value: "positive", "mutated"
    variant: Optional[str] = None  # optional detail, e.g. "H1047R"
    aliases: list[str] = Field(default_factory=list)  # spellings used to spot it in trial and paper text


class Profile(_Row):
    """The platform input: a tissue and its biomarkers (HER2 + PIK3CA for the PoC)."""

    tissue: str
    biomarkers: list[ProfileBiomarker]
    # Gene whose DNA sequence feeds Approach 2. Its model conditioning is biomarker.json.
    sequence_gene: str


class DrugTarget(_Row):
    drug: str
    aliases: list[str] = Field(default_factory=list)
    target_genes: list[str]
    source: str


class GeneTerm(_Row):
    """A clinical word that stands for one or more genes in trial text, e.g. "ER" -> ESR1."""

    term: str
    genes: list[str]
    note: str = ""      # what the term means, shown in the match reason
    source: str


# ---------------------------------------------------------------- stage 1
class Paper(_Sourced):
    paper_id: str
    title: str
    year: Optional[int] = None
    url: str = ""
    genes_mentioned: list[str] = Field(default_factory=list)
    relation: str = ""
    # True: checked by hand against PubMed (the curated set). False: a Keenable search
    # hit merged automatically, not yet reviewed. None: unknown (old rows, mocks).
    reviewed: Optional[bool] = None


# ---------------------------------------------------------------- stage 2
class GeneCandidate(_Sourced):
    gene: str
    ensembl_id: Optional[str] = None
    in_targets_dataset: bool = False
    paper_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- stage 5
class GenomicContext(_Sourced):
    gene: str
    assembly: str = "GRCh38"
    region: str = ""                 # "chr17:39687914-39730426", gene body, 1-based inclusive
    model_task: str = ""
    model_output: dict[str, Any] = Field(default_factory=dict)
    # GI activity summary in [0, 1]: mean of the task readouts. A model summary only;
    # nothing is ranked by it. None when GI could not read the gene.
    model_score: Optional[float] = None


# ---------------------------------------------------------------- stage 3
class Trial(_Sourced):
    nct_id: str
    title: str
    phase: str = ""
    status: str = ""
    url: str = ""
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    eligibility_text: str = ""


# ---------------------------------------------------------------- stage 4 (Approach 1 result)
class BiomarkerMatch(_Row):
    """How one profile biomarker shows up in a trial's criteria."""

    biomarker: str            # e.g. "HER2"
    gene: str                 # e.g. "ERBB2"
    status: str               # the profile's value, e.g. "positive"
    # required:  the criteria ask for the profile's status ("HER2-positive", "PIK3CA-mutated")
    # mentioned: named, but not as a requirement (or both positive and negative cohorts)
    # conflicts: the criteria ask for the opposite ("HER2-negative", "HER2-low", "PIK3CA wild-type")
    # absent:    not named anywhere in the trial text
    requirement: str
    evidence_text: str = ""   # the criteria line that triggered the call
    via_drugs: list[str] = Field(default_factory=list)  # trial drugs that target this gene


class DrugHit(_Row):
    drug: str
    matched_name: str          # the spelling found in the trial text, e.g. "Phesgo"
    target_genes: list[str]
    source: str = ""           # where the drug -> target pair comes from


class RelatedGene(_Row):
    """A literature-linked gene (from gene_candidates.json) that the trial involves."""

    gene: str
    how: list[str]                                        # e.g. ['"HR" named in the criteria', "target of fulvestrant"]
    paper_ids: list[str] = Field(default_factory=list)    # papers that link it to the biomarker


class SupportingPaper(_Row):
    paper_id: str
    title: str
    year: Optional[int] = None
    url: str = ""
    relation: str = ""
    source: str = ""
    reviewed: Optional[bool] = None
    why: list[str] = Field(default_factory=list)          # e.g. ["links PIK3CA to HER2", "mentions alpelisib"]


class TrialMatch(_Row):
    nct_id: str
    title: str
    phase: str = ""
    status: str = ""
    url: str = ""
    tier: str                  # see backend/pipeline/matching.py TIERS
    tier_rank: int             # 1 = closest fit to the profile; order only, not a score
    tier_label: str
    biomarker_matches: list[BiomarkerMatch] = Field(default_factory=list)
    drugs: list[DrugHit] = Field(default_factory=list)
    related_genes: list[RelatedGene] = Field(default_factory=list)
    unchecked_criteria: list[str] = Field(default_factory=list)  # genes whose status the criteria name but the profile lacks
    supporting_papers: list[SupportingPaper] = Field(default_factory=list)
    supporting_papers_total: int = 0   # before the MAX_SUPPORTING_PAPERS cut
    explanation: str = ""
    evidence_type: str = "research-paper evidence + trial criteria"
    source: str = ""                   # the trial's own source, copied from trials.json
    mock_inputs: list[str] = Field(default_factory=list)  # non-empty -> UI shows "mock data"

