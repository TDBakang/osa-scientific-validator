"""Pure deterministic rendering entirely in memory."""

from .canonical import canonical_json, sha256, text_bytes
from .scaffold_models import FileRole, ManifestDraft, RenderedFile, RenderedScaffold, ScaffoldPlan


def _module(plan: ScaffoldPlan) -> bytes:
    control = plan.artifact.control
    provenance = plan.artifact.provenance
    return text_bytes(f'''"""Generated scaffold for {control.control_id}; no scientific execution authority."""

CONTROL_ID = "{control.control_id}"
SOURCE_FINGERPRINT = "{provenance.source_fingerprint}"

class ControlExecutionNotAuthorizedError(RuntimeError):
    """Raised because generated scaffolds are deliberately non-operational."""

def execute(*_args: object, **_kwargs: object) -> None:
    raise ControlExecutionNotAuthorizedError("{control.control_id} execution is not authorized")
''')


def _test(plan: ScaffoldPlan) -> bytes:
    stem = plan.artifact.control.control_id.lower().replace("-", "_")
    # Le segment de famille du chemin importable est dérivé du module déjà
    # planifié (résolu via FAMILY_SEGMENTS dans scaffold_planner), jamais
    # recalculé depuis control.family.lower() : ce dernier n'est pas
    # garanti être un identifiant Python valide ni correspondre au segment
    # de chemin réel (ex. FamilyId "CSA-100" -> segment "crypto").
    family_segment = plan.payload_files[0].relative_path.split("/")[-2]
    return text_bytes(f'''import pytest

from rocsa_generator.generated.{family_segment}.{stem} import ControlExecutionNotAuthorizedError, execute

def test_scaffold_fails_closed() -> None:
    with pytest.raises(ControlExecutionNotAuthorizedError):
        execute()
''')


def _rendered(path: str, role: FileRole, content: bytes) -> RenderedFile:
    return RenderedFile(relative_path=path, role=role, content=content, sha256=sha256(content), size_bytes=len(content))


def render_scaffold(plan: ScaffoldPlan) -> RenderedScaffold:
    payloads = (
        _rendered(plan.payload_files[0].relative_path, FileRole.MODULE, _module(plan)),
        _rendered(plan.payload_files[1].relative_path, FileRole.SCAFFOLD_TEST, _test(plan)),
    )
    markers = tuple(_rendered(f.relative_path, FileRole.PACKAGE_MARKER, b"") for f in plan.infrastructure_files)
    payload_manifest = tuple({"relative_path": f.relative_path, "role": f.role.value, "sha256": f.sha256, "size_bytes": f.size_bytes} for f in payloads)
    infra_manifest = tuple({"relative_path": f.relative_path, "role": f.role.value, "required_sha256": f.sha256, "required_size_bytes": f.size_bytes, "materialization": "REQUIRED", "ownership": "UNRESOLVED"} for f in markers)
    fingerprint_input = {"payload_files": payload_manifest, "infrastructure_files": infra_manifest}
    control, provenance, qualification, c = plan.artifact.control, plan.artifact.provenance, plan.artifact.qualification, plan.configuration
    draft = ManifestDraft(
        manifest_schema_version=c.manifest_schema_version, scaffold_contract_version=c.scaffold_contract_version,
        generator_version=c.generator_version, template_set_version=c.template_set_version,
        renderer_id=c.renderer_id, canonicalization_version=c.canonicalization_version,
        source={
            "csa_id": control.control_id,
            "source_version": provenance.source_version,
            "source_fingerprint": provenance.source_fingerprint,
            "compilation_contract_version": provenance.compiler_contract_version,
        },
        qualification=qualification.model_dump(mode="json"),
        authority={"generated_code": True, "scientifically_validated": False, "publication_authorized": False, "execution_authorized": False},
        payload_files=payload_manifest, infrastructure_files=infra_manifest,
        bundle_fingerprint=sha256(canonical_json(fingerprint_input)), publication_ready=False,
    )
    return RenderedScaffold(plan=plan, payload_files=payloads, infrastructure_files=markers, manifest_draft=draft)
