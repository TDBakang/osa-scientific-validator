import copy
import time
from pathlib import Path

import pytest
import jsonschema

from rocsa_generator.canonical import validate_relative_path
from rocsa_generator.models import DocumentStatus, FNCsaDefinition, compile_artifact
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold


CATALOG_FILE = (
    Path(__file__).parents[1]
    / "src/rocsa_generator/definitions/catalog/csa_101.json"
)


def real_artifact():
    definition = FNCsaDefinition.model_validate_json(
        CATALOG_FILE.read_text(encoding="utf-8")
    )
    return compile_artifact(definition)


def test_real_c2_artifact_is_the_only_fixture_source():
    artifact = real_artifact()
    assert artifact.control.control_id == "CSA-101"
    assert artifact.control.family == "CSA-100"
    assert artifact.provenance.source_version == "1.0.0-draft"
    assert artifact.qualification.source_status is DocumentStatus.PROPOSED


def test_plan_and_render_are_deterministic_and_do_not_mutate_input():
    artifact, configuration = real_artifact(), ScaffoldConfiguration()
    before = copy.deepcopy(artifact.model_dump())
    first = render_scaffold(build_scaffold_plan(artifact, configuration))
    second = render_scaffold(build_scaffold_plan(artifact, configuration))
    assert first == second
    assert artifact.model_dump() == before


def test_payloads_and_markers_are_complete_and_distinct():
    rendered = render_scaffold(
        build_scaffold_plan(real_artifact(), ScaffoldConfiguration())
    )
    assert len(rendered.payload_files) == 2
    assert len(rendered.infrastructure_files) == 2
    assert all(item.content == b"" for item in rendered.infrastructure_files)
    assert all(
        item["materialization"] == "REQUIRED"
        for item in rendered.manifest_draft.infrastructure_files
    )
    assert all(
        item["ownership"] == "UNRESOLVED"
        for item in rendered.manifest_draft.infrastructure_files
    )
    assert rendered.manifest_draft.publication_ready is False


def test_generated_module_fails_closed():
    rendered = render_scaffold(
        build_scaffold_plan(real_artifact(), ScaffoldConfiguration())
    )
    namespace = {}
    exec(rendered.payload_files[0].content, namespace)
    with pytest.raises(namespace["ControlExecutionNotAuthorizedError"]):
        namespace["execute"]()


def test_generated_test_import_path_matches_planned_module():
    """Régression ciblée : le segment d'import du test généré doit
    correspondre au chemin réellement planifié, pas à un recalcul
    indépendant qui pourrait diverger (ex. deux mappings FAMILY_SEGMENTS
    distincts dans scaffold_planner.py et scaffold_renderer.py — voir
    aussi le correctif appliqué dans scaffold_renderer.py qui élimine
    cette seconde source de vérité)."""
    rendered = render_scaffold(
        build_scaffold_plan(real_artifact(), ScaffoldConfiguration())
    )
    module_path = rendered.payload_files[0].relative_path
    expected_segment = module_path.split("/")[-2]
    test_source = rendered.payload_files[1].content.decode("utf-8")
    assert f"generated.{expected_segment}." in test_source


def test_real_c2_render_validates_against_draft_schema():
    rendered = render_scaffold(
        build_scaffold_plan(real_artifact(), ScaffoldConfiguration())
    )
    schema = __import__("json").loads(
        (Path(__file__).parents[1] / "schemas/manifest_draft.schema.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(rendered.manifest_draft.model_dump(mode="json"), schema)


@pytest.mark.parametrize(
    "path", ["../x", "/x", "C:/x", "a\\b", "a//b", "a/./b"]
)
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError):
        validate_relative_path(path)


def test_smoke_performance_100_real_c2_artifacts():
    artifact, configuration = real_artifact(), ScaffoldConfiguration()
    started = time.perf_counter()
    for _ in range(100):
        render_scaffold(build_scaffold_plan(artifact, configuration))
    assert time.perf_counter() - started < 3.0
