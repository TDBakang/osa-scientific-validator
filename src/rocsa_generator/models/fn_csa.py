"""Modèles normatifs stricts des Fiches Normatives CSA (FN-CSA).

Ce module représente la norme. Il ne charge aucun registre, ne génère aucune
classe exécutable et n'implémente aucun algorithme cryptographique.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmpty = Annotated[str, Field(min_length=1)]
CsaId = Annotated[str, Field(pattern=r"^CSA-[1-9][0-9]{2}$")]
SemanticCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")]
SemanticVersion = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")]
FamilyId = Annotated[str, Field(pattern=r"^CSA-[1-9]00$")]


class StrictModel(BaseModel):
    # JSON encode nécessairement enums et dates comme chaînes. Pydantic les
    # décode vers leurs types fermés, tout en refusant les champs inconnus.
    model_config = ConfigDict(extra="forbid")


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    ACTIVE_WITH_RESERVATIONS = "ACTIVE_WITH_RESERVATIONS"
    RETIRED = "RETIRED"


class Criticality(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFORMATIVE = "INFORMATIVE"


class StabilityLevel(StrEnum):
    DRAFT = "DRAFT"
    EXPERIMENTAL = "EXPERIMENTAL"
    STABLE = "STABLE"
    DEPRECATED = "DEPRECATED"


class ResultState(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


class FailurePrescription(StrEnum):
    NONE = "NONE"
    BLOCK_DVS = "BLOCK_DVS"
    SUSPEND_VALIDATION = "SUSPEND_VALIDATION"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    RECORD_FINDING = "RECORD_FINDING"


class Identity(StrictModel):
    csa_id: CsaId
    semantic_code: SemanticCode
    official_name: NonEmpty
    version: SemanticVersion
    status: DocumentStatus


class Classification(StrictModel):
    family: FamilyId
    sub_family: NonEmpty
    domains: Annotated[list[NonEmpty], Field(min_length=1)]
    criticality: Criticality


class Governance(StrictModel):
    author: NonEmpty
    reviewer: NonEmpty
    authority: NonEmpty
    doctrinal_version: NonEmpty
    document_status: DocumentStatus
    criticality_level: Criticality
    stability_level: StabilityLevel


class ScientificDescription(StrictModel):
    objective: NonEmpty
    scope: NonEmpty | list[NonEmpty]
    limits: NonEmpty | list[NonEmpty]
    hypotheses: NonEmpty | list[NonEmpty]
    exclusions: NonEmpty | list[NonEmpty]


class Execution(StrictModel):
    inputs: list[NonEmpty]
    preconditions: list[NonEmpty]
    dependencies: list[CsaId]
    method: NonEmpty | None = None
    parameters: dict[str, Any] | None = None
    postconditions: list[NonEmpty] | None = None


class ResultException(StrictModel):
    code: NonEmpty
    description: NonEmpty


class Results(StrictModel):
    states: Annotated[list[ResultState], Field(min_length=1)]
    on_failure: FailurePrescription
    justification: NonEmpty | None = None
    proofs_used: list[NonEmpty] | None = None
    rules_applied: list[NonEmpty] | None = None
    confidence_level: Annotated[float, Field(ge=0, le=1)] | None = None
    exceptions: list[ResultException] | None = None

    @model_validator(mode="after")
    def states_are_unique(self) -> "Results":
        if len(self.states) != len(set(self.states)):
            raise ValueError("results.states must contain unique values")
        return self


class References(StrictModel):
    doctrinal_documents: list[NonEmpty]
    rmcs_ids: list[NonEmpty]
    esvp_requirements: list[NonEmpty]


class HistoryEntry(StrictModel):
    version: NonEmpty
    date: date
    nature: NonEmpty
    justification: NonEmpty
    approved_by: NonEmpty


class FNCsaDefinition(StrictModel):
    identity: Identity
    classification: Classification
    governance: Governance
    scientific_description: ScientificDescription
    execution: Execution
    results: Results
    references: References
    history: Annotated[list[HistoryEntry], Field(min_length=1)]

    @model_validator(mode="after")
    def cross_section_consistency(self) -> "FNCsaDefinition":
        if self.governance.criticality_level != self.classification.criticality:
            raise ValueError("governance and classification criticality differ")
        if self.governance.document_status != self.identity.status:
            raise ValueError("governance and identity status differ")
        return self

    def assert_publishable(self) -> None:
        """Refuse toute publication d'une fiche encore proposée ou non référencée."""
        errors: list[str] = []
        if self.identity.status not in {
            DocumentStatus.VALIDATED,
            DocumentStatus.ACTIVE,
            DocumentStatus.ACTIVE_WITH_RESERVATIONS,
        }:
            errors.append("document status is not publishable")
        if self.governance.stability_level != StabilityLevel.STABLE:
            errors.append("governance stability is not STABLE")
        if not self.references.doctrinal_documents:
            errors.append("doctrinal references are missing")
        if not self.references.rmcs_ids:
            errors.append("RMCS references are missing")
        if not self.references.esvp_requirements:
            errors.append("ESVP references are missing")
        if self.history[-1].approved_by.startswith("PENDING_"):
            errors.append("scientific approval is pending")
        if errors:
            raise ValueError("FN-CSA is not publishable: " + "; ".join(errors))


class FNCsaCatalog(StrictModel):
    catalog_version: SemanticVersion
    controls: Annotated[list[FNCsaDefinition], Field(min_length=1)]

    @model_validator(mode="after")
    def ids_are_unique(self) -> "FNCsaCatalog":
        ids = [control.identity.csa_id for control in self.controls]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate CSA identifiers in catalog")
        return self
