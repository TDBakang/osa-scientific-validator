"""Strict immutable contracts for the pure 2.3-D-L2 boundary.

Réutilise directement CompilationArtifact/CompiledCSAControl de
rocsa_generator.models (2.3-C1/C2) plutôt que de dupliquer une projection
locale. Une projection dupliquée aurait maintenu deux sources de vérité
pour le même vocabulaire (DocumentStatus, FamilyId, SemanticVersion) —
c'est exactement le mécanisme qui a produit les régressions corrigées
lors de la revue de cette livraison (cf. DECISION-2.3-D-L2.md, addendum).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rocsa_generator.models import CompilationArtifact

# Versions internes de l'outillage L2 (générateur, templates, renderer,
# schéma, canonicalisation) : SemVer strict, sans suffixe de pré-version.
# Distinct de SemanticVersion de fn_csa.py (qui autorise les suffixes de
# pré-version pour les fiches source) — les deux vocabulaires ne se
# confondent jamais, cf. D-SCAFFOLD-21.
SemVer = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FileRole(StrEnum):
    MODULE = "MODULE"
    SCAFFOLD_TEST = "SCAFFOLD_TEST"
    PACKAGE_MARKER = "PACKAGE_MARKER"


class Materialization(StrEnum):
    PRODUCED = "PRODUCED"
    REQUIRED = "REQUIRED"


class Ownership(StrEnum):
    CURRENT_RUN = "CURRENT_RUN"
    UNRESOLVED = "UNRESOLVED"


class ScaffoldConfiguration(StrictModel):
    scaffold_contract_version: SemVer = "1.2.0"
    generator_version: SemVer = "0.4.0"
    template_set_version: SemVer = "1.0.0"
    renderer_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] = "python_pure_v1"
    manifest_schema_version: SemVer = "1.2.0"
    canonicalization_version: SemVer = "1.0.0"


class PlannedFile(StrictModel):
    relative_path: NonEmpty
    role: FileRole
    materialization: Materialization
    ownership: Ownership

    @model_validator(mode="after")
    def state_pair_is_valid(self) -> "PlannedFile":
        allowed = {
            (Materialization.PRODUCED, Ownership.CURRENT_RUN),
            (Materialization.REQUIRED, Ownership.UNRESOLVED),
        }
        if (self.materialization, self.ownership) not in allowed:
            raise ValueError("invalid L2 materialization/ownership pair")
        return self


class ScaffoldPlan(StrictModel):
    # Le vrai CompilationArtifact de 2.3-C2 (control/provenance/field_trace/
    # omitted_source_sections/qualification), pas une projection locale.
    artifact: CompilationArtifact
    configuration: ScaffoldConfiguration
    payload_files: tuple[PlannedFile, PlannedFile]
    infrastructure_files: tuple[PlannedFile, ...]

    @model_validator(mode="after")
    def unique_paths(self) -> "ScaffoldPlan":
        paths = [f.relative_path for f in (*self.payload_files, *self.infrastructure_files)]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate relative paths")
        return self


class RenderedFile(StrictModel):
    relative_path: NonEmpty
    role: FileRole
    content: bytes
    sha256: Sha256
    size_bytes: int = Field(ge=0)


class ManifestDraft(StrictModel):
    manifest_schema_version: SemVer
    scaffold_contract_version: SemVer
    generator_version: SemVer
    template_set_version: SemVer
    renderer_id: str
    canonicalization_version: SemVer
    source: dict[str, object]
    qualification: dict[str, object]
    authority: dict[str, bool]
    payload_files: tuple[dict[str, object], dict[str, object]]
    infrastructure_files: tuple[dict[str, object], ...]
    bundle_fingerprint: Sha256
    publication_ready: bool = False


class RenderedScaffold(StrictModel):
    plan: ScaffoldPlan
    payload_files: tuple[RenderedFile, RenderedFile]
    infrastructure_files: tuple[RenderedFile, ...]
    manifest_draft: ManifestDraft
