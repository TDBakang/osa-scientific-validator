"""Pure planning: no filesystem, clock, environment, Git, or network."""

from .canonical import validate_relative_path
from .scaffold_models import (
    CompilationArtifact, FileRole, Materialization, Ownership, PlannedFile,
    ScaffoldConfiguration, ScaffoldPlan,
)

FAMILY_SEGMENTS = {"CSA-100": "crypto"}


def build_scaffold_plan(artifact: CompilationArtifact, configuration: ScaffoldConfiguration) -> ScaffoldPlan:
    try:
        family = FAMILY_SEGMENTS[artifact.control.family]
    except KeyError as exc:
        raise ValueError(f"unsupported family: {artifact.control.family}") from exc
    stem = artifact.control.control_id.lower().replace("-", "_")
    module = validate_relative_path(f"src/rocsa_generator/generated/{family}/{stem}.py")
    test = validate_relative_path(f"tests/generated/test_{stem}_scaffold.py")
    markers = (
        "src/rocsa_generator/generated/__init__.py",
        f"src/rocsa_generator/generated/{family}/__init__.py",
    )
    payloads = (
        PlannedFile(relative_path=module, role=FileRole.MODULE, materialization=Materialization.PRODUCED, ownership=Ownership.CURRENT_RUN),
        PlannedFile(relative_path=test, role=FileRole.SCAFFOLD_TEST, materialization=Materialization.PRODUCED, ownership=Ownership.CURRENT_RUN),
    )
    infrastructure = tuple(
        PlannedFile(relative_path=validate_relative_path(p), role=FileRole.PACKAGE_MARKER, materialization=Materialization.REQUIRED, ownership=Ownership.UNRESOLVED)
        for p in markers
    )
    return ScaffoldPlan(artifact=artifact, configuration=configuration, payload_files=payloads, infrastructure_files=infrastructure)
