"""Strict immutable contracts for the pure 2.3-D-L2 boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models.compilation_artifact import CompilationArtifact

ToolSemVer = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]
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
    scaffold_contract_version: ToolSemVer = "1.2.1"
    generator_version: ToolSemVer = "0.4.1"
    template_set_version: ToolSemVer = "1.0.1"
    renderer_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")] = "python_pure_v1"
    manifest_schema_version: ToolSemVer = "1.2.1"
    canonicalization_version: ToolSemVer = "1.0.0"


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
    manifest_schema_version: ToolSemVer
    scaffold_contract_version: ToolSemVer
    generator_version: ToolSemVer
    template_set_version: ToolSemVer
    renderer_id: str
    canonicalization_version: ToolSemVer
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
