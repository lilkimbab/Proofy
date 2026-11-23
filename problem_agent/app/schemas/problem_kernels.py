from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ContentAtomType(StrEnum):
    definition = "definition"
    classification = "classification"
    rule = "rule"
    formula = "formula"
    procedure = "procedure"
    comparison = "comparison"
    cause_effect = "cause_effect"
    condition_exception = "condition_exception"
    evidence_claim = "evidence_claim"
    data_table = "data_table"
    code_state = "code_state"
    example_case = "example_case"


class AtomConfidenceLevel(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ContentAtom(BaseModel):
    atom_id: str = Field(min_length=1, max_length=128)
    atom_type: ContentAtomType
    source_chunk_id: str = Field(min_length=1, max_length=128)
    statement: str = Field(min_length=1, max_length=1200)
    evidence_quote: str | None = Field(default=None, max_length=1200)
    concepts: list[str] = Field(default_factory=list, max_length=20)
    symbols: list[str] = Field(default_factory=list, max_length=20)
    variables: list[str] = Field(default_factory=list, max_length=20)
    conditions: list[str] = Field(default_factory=list, max_length=20)
    exceptions: list[str] = Field(default_factory=list, max_length=20)
    examples: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(default=0.0, ge=0, le=1)
    confidence_level: AtomConfidenceLevel = AtomConfidenceLevel.medium


class ProblemKernelType(StrEnum):
    recall_define = "recall_define"
    explain_concept = "explain_concept"
    apply_rule_to_case = "apply_rule_to_case"
    diagnose_error = "diagnose_error"
    condition_mutation = "condition_mutation"
    compare_boundary = "compare_boundary"
    compute_from_given = "compute_from_given"
    trace_process = "trace_process"
    evidence_to_claim = "evidence_to_claim"
    design_under_constraints = "design_under_constraints"
    counterexample_or_limitation = "counterexample_or_limitation"


class EvidenceRole(StrEnum):
    definition = "definition"
    rule = "rule"
    formula = "formula"
    condition = "condition"
    exception = "exception"
    contrast = "contrast"
    example = "example"
    procedure_step = "procedure_step"
    data_point = "data_point"
    source_claim = "source_claim"


EvidencePlacement = Literal["question", "answer", "explanation", "distractor", "rubric"]


class EvidenceObligation(BaseModel):
    role: EvidenceRole
    required: bool = True
    must_be_cited: bool = True
    must_appear_in: list[EvidencePlacement] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)


class EvidenceLink(BaseModel):
    link_id: str = Field(default="", max_length=128)
    atom_id: str = Field(min_length=1, max_length=128)
    source_chunk_id: str = Field(min_length=1, max_length=128)
    evidence_role: EvidenceRole
    evidence_quote: str = Field(min_length=1, max_length=1200)
    used_in: list[EvidencePlacement] = Field(default_factory=list, min_length=1, max_length=5)
    supported_claim: str = Field(min_length=1, max_length=1200)

    @field_validator("used_in", mode="before")
    @classmethod
    def normalize_used_in(cls, value: object) -> list[EvidencePlacement] | object:
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def fill_link_id(self) -> EvidenceLink:
        if self.link_id:
            return self
        placements = "_".join(self.used_in)
        self.link_id = f"link_{self.atom_id}_{self.evidence_role.value}_{placements}"[:128]
        return self


class ComputationScenarioValue(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=40)
    role: str = Field(min_length=1, max_length=160)


class ComputationScenarioSpec(BaseModel):
    formula_atom_id: str = Field(min_length=1, max_length=128)
    source_chunk_id: str = Field(min_length=1, max_length=128)
    formula_or_rule_quote: str = Field(min_length=1, max_length=1200)
    variables_or_inputs: list[str] = Field(default_factory=list, max_length=20)
    generated_given_values: list[ComputationScenarioValue] = Field(default_factory=list, max_length=12)
    required_derivation_steps: list[str] = Field(default_factory=list, max_length=12)
    required_interpretation: str | None = Field(default=None, max_length=300)
    constraints: list[str] = Field(default_factory=list, max_length=12)
    prohibited_patterns: list[str] = Field(default_factory=list, max_length=12)


class EvidencePackAtom(BaseModel):
    atom_id: str = Field(min_length=1, max_length=128)
    atom_type: str = Field(min_length=1, max_length=80)
    source_chunk_id: str = Field(min_length=1, max_length=128)
    evidence_quote: str | None = Field(default=None, max_length=1200)
    statement: str = Field(min_length=1, max_length=1200)
    roles: list[str] = Field(default_factory=list, max_length=8)
    concepts: list[str] = Field(default_factory=list, max_length=12)


class EvidencePack(BaseModel):
    selected_atoms: list[EvidencePackAtom] = Field(default_factory=list, max_length=20)
    required_obligations: list[str] = Field(default_factory=list, max_length=20)
    computation_scenario: ComputationScenarioSpec | None = None
    allowed_generated_scenario_values: bool = False
    prohibited_patterns: list[str] = Field(default_factory=list, max_length=20)
    source_chunk_id_whitelist: list[str] = Field(default_factory=list, max_length=30)
    compact_context_notes: list[str] = Field(default_factory=list, max_length=30)


class ProblemKernelPlan(BaseModel):
    kernel_type: ProblemKernelType
    content_atom_ids: list[str] = Field(default_factory=list, max_length=20)
    target_cognitive_level: str = Field(min_length=1, max_length=80)
    required_evidence_roles: list[EvidenceObligation] = Field(default_factory=list, max_length=12)
    allows_generated_scenario_values: bool = False
    requires_derivation_check: bool = False
    requires_distinct_distractors: bool = False
    requires_source_claim_alignment: bool = False
    anti_patterns: list[str] = Field(default_factory=list, max_length=20)
    failure_reason: str | None = Field(default=None, max_length=200)
    caution: str | None = Field(default=None, max_length=300)
    available_atom_types: list[str] = Field(default_factory=list, max_length=20)
    missing_atom_types: list[str] = Field(default_factory=list, max_length=20)
    closest_alternative_kernel: ProblemKernelType | None = None
    computation_scenario: ComputationScenarioSpec | None = None
