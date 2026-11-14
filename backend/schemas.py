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


class DrugTarget(_Row):
    drug: str
    aliases: list[str] = Field(default_factory=list)
    target_genes: list[str]
    source: str


# ---------------------------------------------------------------- stage 1
class Paper(_Sourced):
    paper_id: str
    title: str
    year: Optional[int] = None
    url: str = ""
    genes_mentioned: list[str] = Field(default_factory=list)
    relation: str = ""


# ---------------------------------------------------------------- stage 2
class GeneCandidate(_Sourced):
    gene: str
    ensembl_id: Optional[str] = None
    in_targets_dataset: bool = False
    paper_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- stage 3
class GenomicContext(_Sourced):
    gene: str
    assembly: str = "GRCh38"
    region: str = ""                 # "chr17:39687914-39730426", gene body, 1-based inclusive
    model_task: str = ""
    model_output: dict[str, Any] = Field(default_factory=dict)
    model_score: Optional[float] = None  # [0, 1]; None only when the gene could not be scored


# ---------------------------------------------------------------- stage 4
class GeneScore(_Row):
    gene: str
    literature_score: float
    model_score: float
    combined_score: float


# ---------------------------------------------------------------- stage 5
class Trial(_Sourced):
    nct_id: str
    title: str
    phase: str = ""
    status: str = ""
    url: str = ""
    conditions: list[str] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    eligibility_text: str = ""


# ---------------------------------------------------------------- stage 6
class MatchedGene(_Row):
    gene: str
    combined_score: float
    paper_ids: list[str] = Field(default_factory=list)


class Ranking(_Row):
    rank: int
    nct_id: str
    title: str
    phase: str = ""
    status: str = ""
    url: str = ""
    trial_score: float
    biomarker_directness: float
    genomic_match: float
    matched_genes: list[MatchedGene] = Field(default_factory=list)
    source: str = ""  # the trial's own source, copied from trials.json
    # Which upstream inputs behind this row are mocks, e.g. ["trials", "genomic_context"].
    # The dashboard shows a "mock data" tag whenever this is non-empty.
    mock_inputs: list[str] = Field(default_factory=list)
