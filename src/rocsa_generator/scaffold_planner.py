"""Pure planning: no filesystem, clock, environment, Git, or network."""

from rocsa_generator.models import CompilationArtifact

from .canonical import validate_relative_path
from .scaffold_models import (
    FileRole, Materialization, Ownership, PlannedFile,
    ScaffoldConfiguration, ScaffoldPlan,
)

# Mapping du FamilyId réel (D-FNCSA-ID-01/02/03, fn_csa.py) vers le segment
# de chemin du paquet généré. Seule CSA-100 (crypto) est couverte à ce
# stade — CSA-101 est la fiche pilote unique. Toute extension à une autre
# centaine est un ajout doctrinal explicite, pas un effet de bord.
FAMILY_SEGMENTS = {"CSA-100": "crypto"}


def build_scaffold_plan(artifact: CompilationArtifact, configuration: ScaffoldConfiguration) -> ScaffoldPlan:
    control = artifact.control
    try:
        family_segment = FAMILY_SEGMENTS[control.family]
    except KeyError as exc:
        raise ValueError(f"unsupported family: {control.family}") from exc
    stem = control.control_id.lower().replace("-", "_")
    module = validate_relative_path(f"src/rocsa_generator/generated/{family_segment}/{stem}.py")
    test = validate_relative_path(f"tests/generated/test_{stem}_scaffold.py")
    markers = (
        "src/rocsa_generator/generated/__init__.py",
        f"src/rocsa_generator/generated/{family_segment}/__init__.py",
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
