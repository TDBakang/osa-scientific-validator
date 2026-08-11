"""Jalon 2.3-C2 — Tests de CompilationArtifact.

Couvre les critères d'acceptation AC-2.3-C2-01 à AC-2.3-C2-10.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocsa_generator.models import compilation_artifact
from rocsa_generator.models.compilation_artifact import (
    FIELD_TRACE_REGISTRY,
    OMITTED_SOURCE_SECTIONS,
    CompilationArtifact,
    compile_artifact,
    compile_catalog,
    fingerprint_of,
    from_canonical_json,
    to_canonical_json,
)
from rocsa_generator.models.fn_csa import FNCsaCatalog, FNCsaDefinition


ROOT = Path(__file__).parents[1]
CSA101 = ROOT / "src/rocsa_generator/definitions/catalog/csa_101.json"


def load_source() -> dict:
    return json.loads(CSA101.read_text(encoding="utf-8"))


def load_definition() -> FNCsaDefinition:
    return FNCsaDefinition.model_validate(load_source())


def second_valid_source(csa_id: str = "CSA-901") -> dict:
    """Fiche valide distincte, dérivée de CSA-101, pour les tests de
    catalogue (ordre, unicité)."""
    source = load_source()
    source["identity"]["csa_id"] = csa_id
    source["identity"]["semantic_code"] = "AUDIT.SECOND.CHECK"
    source["classification"]["family"] = "CSA-900"
    source["classification"]["sub_family"] = "Test"
    return source


# --- AC-2.3-C2-01 / 02 : sérialisation canonique, aller-retour sans perte --

def test_canonical_json_is_deterministic() -> None:
    definition = load_definition()
    first = to_canonical_json(compile_artifact(definition))
    second = to_canonical_json(compile_artifact(definition))
    assert first == second


def test_round_trip_is_lossless() -> None:
    artifact = compile_artifact(load_definition())
    text = to_canonical_json(artifact)
    restored = from_canonical_json(text)
    assert restored == artifact
    assert to_canonical_json(restored) == text


def test_canonical_json_rejects_unknown_fields_on_load() -> None:
    artifact = compile_artifact(load_definition())
    payload = json.loads(to_canonical_json(artifact))
    payload["unexpected_top_level_field"] = True
    with pytest.raises(ValidationError):
        from_canonical_json(json.dumps(payload))


def test_c2_api_is_publicly_exported() -> None:
    from rocsa_generator.models import (
        compile_artifact as public_compile_artifact,
        compile_catalog as public_compile_catalog,
        from_canonical_json as public_from_canonical_json,
        to_canonical_json as public_to_canonical_json,
    )

    assert public_compile_artifact is compile_artifact
    assert public_compile_catalog is compile_catalog
    assert public_from_canonical_json is from_canonical_json
    assert public_to_canonical_json is to_canonical_json


# --- AC-2.3-C2-03 : provenance complète et vérifiable ------------------------

def test_provenance_fields_are_populated() -> None:
    definition = load_definition()
    artifact = compile_artifact(definition)
    assert artifact.provenance.source_csa_id == "CSA-101"
    assert artifact.provenance.source_version == definition.identity.version
    assert len(artifact.provenance.source_fingerprint) == 64  # SHA-256 hex
    assert artifact.provenance.compiler_contract_version == "1.0.0"


def test_provenance_rejects_invalid_sha256_and_versions() -> None:
    artifact = compile_artifact(load_definition())
    payload = artifact.provenance.model_dump(mode="json")

    with pytest.raises(ValidationError):
        artifact.provenance.__class__.model_validate(
            {**payload, "source_fingerprint": "not-a-sha256"}
        )
    with pytest.raises(ValidationError):
        artifact.provenance.__class__.model_validate(
            {**payload, "compiler_contract_version": "v1"}
        )


def test_fingerprint_is_stable_across_independent_loads() -> None:
    """Deux chargements indépendants de la même source produisent la
    même empreinte : la provenance ne dépend pas de l'identité objet."""
    first = compile_artifact(load_definition())
    second = compile_artifact(load_definition())
    assert first.provenance.source_fingerprint == second.provenance.source_fingerprint


def test_fingerprint_changes_when_source_content_changes() -> None:
    source = load_source()
    baseline = fingerprint_of(FNCsaDefinition.model_validate(source).model_dump(mode="json"))

    source["identity"]["official_name"] = "Titre modifié pour le test"
    modified = fingerprint_of(FNCsaDefinition.model_validate(source).model_dump(mode="json"))

    assert baseline != modified


def test_no_implicit_timestamp_in_provenance() -> None:
    """Aucune horloge implicite : le module ne doit pas importer le
    module datetime, qui casserait le déterminisme entre deux
    compilations successives de la même source."""
    module_source = Path(
        ROOT / "src/rocsa_generator/models/compilation_artifact.py"
    ).read_text(encoding="utf-8")
    assert "datetime" not in module_source
    assert "time.time" not in module_source


# --- AC-2.3-C2-04 / 05 : traçabilité champ par champ, sections omises -------

def test_field_trace_matches_registry() -> None:
    artifact = compile_artifact(load_definition())
    actual = {(entry.target_field, entry.source_path) for entry in artifact.field_trace}
    expected = set(FIELD_TRACE_REGISTRY)
    assert actual == expected


def test_omitted_sections_are_explicitly_recorded() -> None:
    artifact = compile_artifact(load_definition())
    assert artifact.omitted_source_sections == OMITTED_SOURCE_SECTIONS
    # Sections normatives connues, doivent être présentes dans le registre.
    for expected_section in ("governance", "scientific_description", "references", "history"):
        assert expected_section in artifact.omitted_source_sections


def test_field_trace_and_omitted_sections_are_immutable_tuples() -> None:
    artifact = compile_artifact(load_definition())
    assert isinstance(artifact.field_trace, tuple)
    assert isinstance(artifact.omitted_source_sections, tuple)


# --- AC-2.3-C2-06 : blocages publication/exécution conservés ----------------

def test_qualification_reflects_proposed_and_unpublishable_status() -> None:
    definition = load_definition()
    artifact = compile_artifact(definition)
    q = artifact.qualification

    assert q.source_status.value == "PROPOSED"
    assert q.publication_eligible is False
    assert "RMCS references are missing" in q.publication_blocking_reasons
    assert "ESVP references are missing" in q.publication_blocking_reasons
    assert "scientific approval is pending" in q.publication_blocking_reasons

    assert q.execution_eligible is False
    assert q.execution_blocking_reason  # non vide


def test_compile_artifact_never_raises_on_unpublishable_source() -> None:
    """D-FNCSA-COMPILE-01 : la compilation ne doit jamais échouer parce
    que la source n'est pas publiable — seule assert_publishable() le
    fait, séparément."""
    definition = load_definition()
    # Ne doit lever aucune exception, alors qu'assert_publishable() le
    # ferait pour cette même définition.
    with pytest.raises(ValueError):
        definition.assert_publishable()
    artifact = compile_artifact(definition)  # ne doit pas lever
    assert artifact.qualification.publication_eligible is False


def test_compiled_control_is_unchanged_from_c1() -> None:
    """Option B : l'enveloppe ne modifie ni ne duplique la logique de
    compilation du contrôle — CompilationArtifact.control est exactement
    ce que produirait compile_contract_only() directement."""
    from rocsa_generator.models.compiled_control import compile_contract_only

    definition = load_definition()
    direct = compile_contract_only(definition)
    enveloped = compile_artifact(definition).control
    assert direct == enveloped


# --- AC-2.3-C2-07 / 08 / 09 : compilation de catalogue -----------------------

def test_compile_catalog_orders_canonically_by_csa_id() -> None:
    catalog = FNCsaCatalog.model_validate({
        "catalog_version": "1.0.0",
        "controls": [second_valid_source("CSA-901"), load_source()],  # ordre volontairement inversé
    })
    artifacts = compile_catalog(catalog)
    ids = [a.provenance.source_csa_id for a in artifacts]
    assert ids == sorted(ids)
    assert ids == ["CSA-101", "CSA-901"]


def test_catalog_rejects_duplicate_identifiers_upstream() -> None:
    """AC-2.3-C2-08 : l'unicité est garantie en amont par FNCsaCatalog
    lui-même — un catalogue avec doublons ne peut pas être construit."""
    source = load_source()
    with pytest.raises(Exception):
        FNCsaCatalog.model_validate({
            "catalog_version": "1.0.0",
            "controls": [source, source],
        })


def test_compile_catalog_fails_atomically(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2.3-C2-09 : si une définition échoue à se compiler, aucune
    sortie partielle n'est retournée."""
    catalog = FNCsaCatalog.model_validate({
        "catalog_version": "1.0.0",
        "controls": [load_source(), second_valid_source("CSA-901")],
    })

    original_compile_artifact = compilation_artifact.compile_artifact

    completed: list[str] = []

    def flaky_compile(definition: FNCsaDefinition) -> CompilationArtifact:
        if definition.identity.csa_id == "CSA-901":
            raise RuntimeError("échec simulé pour test d'atomicité")
        result = original_compile_artifact(definition)
        completed.append(definition.identity.csa_id)
        return result

    monkeypatch.setattr(compilation_artifact, "compile_artifact", flaky_compile)

    with pytest.raises(RuntimeError, match="échec simulé"):
        compilation_artifact.compile_catalog(catalog)

    # La première définition (CSA-101, triée avant CSA-901) a bien été
    # tentée, mais aucun résultat partiel n'est accessible depuis
    # l'extérieur : l'appelant n'a reçu qu'une exception, jamais une
    # liste tronquée.
    assert completed == ["CSA-101"]


# --- AC-2.3-C2-10 : non-régression -------------------------------------------

def test_source_definition_still_not_mutated_through_artifact_compilation() -> None:
    definition = load_definition()
    before = copy.deepcopy(definition.model_dump(mode="json"))
    compile_artifact(definition)
    after = definition.model_dump(mode="json")
    assert before == after
