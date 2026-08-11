"""Tests du périmètre pur L2 (planification + rendu, sans I/O).

Provenance des données de test — lire avant de modifier.
---------------------------------------------------------
D-SCAFFOLD-21 interdit la reconstruction manuelle d'un vecteur de preuve :
toute donnée doit provenir du pipeline C2 réel (`compile_artifact()` /
`generate_vector.py`), jamais être ressaisie à la main.

Ce fichier charge directement le vrai vecteur produit par
`generate_vector.py` via `from_canonical_json()` (aucun mapping manuel
champ par champ — c'est exactement l'intérêt de consommer le vrai type
`CompilationArtifact` plutôt qu'une projection locale dupliquée). Chemin
par défaut ou variable d'environnement `ROCSA_REAL_VECTOR_PATH`.

`test_real_vector_is_available` échoue intentionnellement si absent, pour
qu'un merge sur données inventées ne passe pas inaperçu comme "vert".

`test_c2_pipeline_output_matches_frozen_fixture` va plus loin : elle
relance réellement `compile_artifact()` sur le catalogue source CSA-101
et vérifie que sa sortie canonique correspond toujours à la fixture
figée. Contrairement au test précédent, elle passe en SKIP (pas en
échec) si le catalogue source n'est pas trouvé à l'emplacement attendu :
son rôle est de détecter une dérive de C2, pas de garantir la présence
du vecteur — c'est déjà le rôle du test précédent. À durcir en échec
strict une fois le chemin du catalogue confirmé stable dans le dépôt.
"""

import copy
import os
import statistics
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocsa_generator.canonical import sha256, validate_relative_path
from rocsa_generator.models import (
    CompilationArtifact, CompiledCSAControl, CompilationProvenance,
    CompilationQualification, FNCsaDefinition, compile_artifact,
    from_canonical_json, to_canonical_json,
)
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold

DEFAULT_REAL_VECTOR_PATH = Path("tests/fixtures/csa_101_compilation_artifact.canonical.json")
DEFAULT_CATALOG_ENTRY_PATH = Path("src/rocsa_generator/definitions/catalog/csa_101.json")


def _path_from_env_or_default(env_var: str, default: Path) -> Path | None:
    override = os.environ.get(env_var)
    candidate = Path(override) if override else default
    return candidate if candidate.is_file() else None


def _real_vector_path() -> Path | None:
    return _path_from_env_or_default("ROCSA_REAL_VECTOR_PATH", DEFAULT_REAL_VECTOR_PATH)


def _catalog_entry_path() -> Path | None:
    return _path_from_env_or_default("ROCSA_CSA_101_CATALOG_PATH", DEFAULT_CATALOG_ENTRY_PATH)


def illustrative_artifact() -> CompilationArtifact:
    """Valeur de repli STRUCTURELLEMENT valide mais NON probante.

    Construite directement avec les vrais types C1/C2 (CompiledCSAControl,
    CompilationProvenance, CompilationQualification) : la seule chose
    d'illustratif ici est le contenu des valeurs, pas leur type — donc
    aucune des régressions de vocabulaire déjà corrigées (SourceStatus,
    FamilyId, SourceVersion) ne peut plus se réintroduire silencieusement,
    Pydantic les rejetterait à la construction.
    """
    source = b'{"csa_id":"CSA-101","status":"PROPOSED"}'
    control = CompiledCSAControl(
        control_id="CSA-101", semantic_code="CRYPTO.INTEGRITY.VERIFY",
        title="Contrôle d'intégrité cryptographique", severity="CRITICAL",
        family="CSA-100", allowed_states=("PASSED", "FAILED", "NOT_APPLICABLE", "ERROR"),
        on_failure="BLOCK_DVS",
    )
    provenance = CompilationProvenance(
        source_csa_id="CSA-101", source_version="1.0.0-draft",
        source_fingerprint=sha256(source), compiler_contract_version="1.0.0",
    )
    qualification = CompilationQualification(
        source_status="PROPOSED", publication_eligible=False,
        publication_blocking_reasons=("Approbation scientifique absente",),
        execution_eligible=False, execution_blocking_reason="Implémentation métier absente",
    )
    return CompilationArtifact(
        control=control, provenance=provenance, field_trace=(), omitted_source_sections=(),
        qualification=qualification,
    )


def real_or_illustrative_artifact() -> CompilationArtifact:
    path = _real_vector_path()
    if path is None:
        return illustrative_artifact()
    return from_canonical_json(path.read_text(encoding="utf-8"))


# Alias rétrocompatible pour le reste du fichier.
artifact = real_or_illustrative_artifact


def test_real_vector_is_available():
    """Échoue intentionnellement tant que le vrai vecteur C2 n'est pas fourni.

    Ce test ne doit JAMAIS être supprimé ou ignoré pour faire passer la
    suite au vert : c'est le garde-fou qui empêche un merge silencieux sur
    données inventées (D-SCAFFOLD-21).
    """
    path = _real_vector_path()
    assert path is not None, (
        "Vecteur C2 réel introuvable. Fournissez-le via "
        f"{DEFAULT_REAL_VECTOR_PATH} ou la variable d'environnement "
        "ROCSA_REAL_VECTOR_PATH avant d'accepter ce livrable."
    )


def test_c2_pipeline_output_matches_frozen_fixture():
    """Compatibilité dynamique C2 -> L2 : relance compile_artifact() sur le
    catalogue source réel et compare à la fixture figée, pour détecter
    une dérive de C2 que la fixture seule ne verrait jamais."""
    catalog_path, fixture_path = _catalog_entry_path(), _real_vector_path()
    if catalog_path is None or fixture_path is None:
        pytest.skip("catalogue source CSA-101 ou fixture figée indisponible dans cet environnement")
    definition = FNCsaDefinition.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    live = compile_artifact(definition)
    frozen = from_canonical_json(fixture_path.read_text(encoding="utf-8"))
    assert to_canonical_json(live) == to_canonical_json(frozen)


def test_plan_and_render_are_deterministic_and_do_not_mutate_input():
    a, c = artifact(), ScaffoldConfiguration()
    before = copy.deepcopy(a.model_dump())
    first = render_scaffold(build_scaffold_plan(a, c))
    second = render_scaffold(build_scaffold_plan(a, c))
    assert first == second
    assert a.model_dump() == before


def test_payloads_and_markers_are_complete_and_distinct():
    rendered = render_scaffold(build_scaffold_plan(artifact(), ScaffoldConfiguration()))
    assert len(rendered.payload_files) == 2
    assert len(rendered.infrastructure_files) == 2
    assert all(f.content == b"" for f in rendered.infrastructure_files)
    assert all(x["materialization"] == "REQUIRED" for x in rendered.manifest_draft.infrastructure_files)
    assert all(x["ownership"] == "UNRESOLVED" for x in rendered.manifest_draft.infrastructure_files)
    assert rendered.manifest_draft.publication_ready is False


def test_generated_module_fails_closed():
    rendered = render_scaffold(build_scaffold_plan(artifact(), ScaffoldConfiguration()))
    namespace = {}
    exec(rendered.payload_files[0].content, namespace)
    with pytest.raises(namespace["ControlExecutionNotAuthorizedError"]):
        namespace["execute"]()


def test_generated_test_import_path_matches_planned_module():
    """Régression ciblée : le segment d'import du test généré doit
    correspondre au chemin réellement planifié, pas à un recalcul depuis
    control.family.lower() (qui coïncidait par hasard avec l'ancienne
    valeur fautive "CRYPTO" mais diverge du vrai FamilyId "CSA-100")."""
    rendered = render_scaffold(build_scaffold_plan(artifact(), ScaffoldConfiguration()))
    module_path = rendered.payload_files[0].relative_path
    expected_segment = module_path.split("/")[-2]
    test_source = rendered.payload_files[1].content.decode("utf-8")
    assert f"generated.{expected_segment}." in test_source


@pytest.mark.parametrize("path", ["../x", "/x", "C:/x", "a\\b", "a//b", "a/./b"])
def test_unsafe_paths_are_rejected(path):
    with pytest.raises(ValueError):
        validate_relative_path(path)


def test_unknown_fields_and_incoherent_qualification_are_rejected():
    with pytest.raises(ValidationError):
        CompilationQualification(
            source_status="PROPOSED", publication_eligible=False,
            publication_blocking_reasons=(), execution_eligible=False,
            execution_blocking_reason="x", unknown=True,
        )


def test_smoke_performance_100_artifacts():
    """Garde-fou de fumée, pas un protocole statistique (celui-ci est D-L4).

    Rapporte la médiane et le p95 sur des tirages individuels plutôt qu'un
    seul temps cumulé : plus informatif en cas de régression et pas plus
    coûteux à exécuter.
    """
    a, c = artifact(), ScaffoldConfiguration()
    samples = []
    for _ in range(100):
        started = time.perf_counter()
        render_scaffold(build_scaffold_plan(a, c))
        samples.append(time.perf_counter() - started)
    samples.sort()
    median = statistics.median(samples)
    p95 = samples[int(len(samples) * 0.95)]
    assert sum(samples) < 3.0, f"total={sum(samples):.3f}s median={median * 1000:.2f}ms p95={p95 * 1000:.2f}ms"
