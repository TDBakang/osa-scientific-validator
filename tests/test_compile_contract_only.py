"""Jalon 2.3-C1 — Tests du compilateur pur FNCsaDefinition -> CompiledCSAControl.

Couvre les critères d'acceptation AC-2.3-C-01 à AC-2.3-C-10.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocsa_generator.models.compiled_control import CompiledCSAControl, compile_contract_only
from rocsa_generator.models.fn_csa import FNCsaDefinition


ROOT = Path(__file__).parents[1]
CSA101 = ROOT / "src/rocsa_generator/definitions/catalog/csa_101.json"


def load_definition() -> FNCsaDefinition:
    source = json.loads(CSA101.read_text(encoding="utf-8"))
    return FNCsaDefinition.model_validate(source)


def test_compile_contract_only_is_publicly_exported() -> None:
    from rocsa_generator.models import compile_contract_only as public_compile

    assert public_compile is compile_contract_only


# --- AC-2.3-C-04 / correspondance champ par champ ---------------------------

def test_field_by_field_mapping_matches_source() -> None:
    definition = load_definition()
    compiled = compile_contract_only(definition)

    assert compiled.control_id == definition.identity.csa_id == "CSA-101"
    assert compiled.semantic_code == definition.identity.semantic_code
    assert compiled.title == definition.identity.official_name
    assert compiled.severity == definition.classification.criticality
    assert compiled.family == definition.classification.family
    assert compiled.allowed_states == tuple(definition.results.states)
    assert compiled.on_failure == definition.results.on_failure


def test_no_field_is_invented_or_defaulted() -> None:
    """AC-2.3-C-04 : le compilé ne contient que les 7 champs du mapping acté,
    rien de plus (pas de valeur de secours, pas de champ supplémentaire)."""
    compiled = compile_contract_only(load_definition())
    expected_fields = {
        "control_id", "semantic_code", "title",
        "severity", "family", "allowed_states", "on_failure",
    }
    assert set(type(compiled).model_fields.keys()) == expected_fields


# --- AC-2.3-C-01 : déterminisme ----------------------------------------------

def test_same_input_produces_same_output() -> None:
    definition = load_definition()
    first = compile_contract_only(definition)
    second = compile_contract_only(definition)
    assert first == second

    # Deux instances FNCsaDefinition distinctes issues de la même source
    # doivent aussi produire des compilés identiques.
    third = compile_contract_only(load_definition())
    assert first == third


# --- AC-2.3-C-05 : aucune mutation de la source ------------------------------

def test_source_definition_is_not_mutated() -> None:
    definition = load_definition()
    before = copy.deepcopy(definition.model_dump(mode="json"))

    compile_contract_only(definition)

    after = definition.model_dump(mode="json")
    assert before == after


# --- AC-2.3-C-06 : sortie strictement typée et immuable ----------------------

def test_compiled_control_is_frozen() -> None:
    compiled = compile_contract_only(load_definition())
    with pytest.raises(ValidationError):
        compiled.control_id = "CSA-999"  # type: ignore[misc]


def test_compiled_control_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CompiledCSAControl(
            control_id="CSA-101",
            semantic_code="CRYPTO.INTEGRITY.VERIFY",
            title="x",
            severity="CRITICAL",
            family="CSA-100",
            allowed_states=("PASSED",),
            on_failure="BLOCK_DVS",
            unexpected_field="should not be allowed",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (("title", ""), ("family", "CSA-101")),
)
def test_compiled_control_enforces_normative_string_types(
    field: str, invalid_value: str
) -> None:
    payload = compile_contract_only(load_definition()).model_dump()
    payload[field] = invalid_value

    with pytest.raises(ValidationError):
        CompiledCSAControl.model_validate(payload)


# --- AC-2.3-C-07 / AC-2.3-C-08 : PROPOSED compilable mais jamais publiable --

def test_proposed_csa_101_is_compilable() -> None:
    definition = load_definition()
    assert definition.identity.status.value == "PROPOSED"
    # Ne doit lever aucune exception.
    compiled = compile_contract_only(definition)
    assert compiled.control_id == "CSA-101"


def test_source_remains_unpublishable_after_compilation() -> None:
    """La compilation ne change ni n'efface le statut de publication de la
    source. assert_publishable() doit toujours échouer après compilation,
    exactement comme avant."""
    definition = load_definition()
    compile_contract_only(definition)

    with pytest.raises(ValueError, match="not publishable"):
        definition.assert_publishable()


def test_compiled_control_carries_no_publication_authority() -> None:
    """L'artefact compilé n'a, par construction, aucune méthode de type
    assert_publishable() : personne ne peut le confondre avec une
    autorisation de publication."""
    compiled = compile_contract_only(load_definition())
    assert not hasattr(compiled, "assert_publishable")


# --- AC-2.3-C-09 : aucun contrôle cryptographique exécuté --------------------

def test_compile_contract_only_has_no_crypto_side_effects() -> None:
    """Vérification structurelle : le module ne doit importer ni hashlib,
    ni tout autre module de primitive cryptographique."""
    module_source = Path(
        ROOT / "src/rocsa_generator/models/compiled_control.py"
    ).read_text(encoding="utf-8")
    forbidden_imports = ("hashlib", "hmac", "cryptography", "Crypto")
    for forbidden in forbidden_imports:
        assert forbidden not in module_source, (
            f"compiled_control.py ne doit référencer aucune primitive "
            f"cryptographique ({forbidden} trouvé)."
        )
