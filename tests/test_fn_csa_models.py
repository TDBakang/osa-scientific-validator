import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocsa_generator.models.fn_csa import (
    FNCsaCatalog,
    FNCsaDefinition,
    FailurePrescription,
    ResultState,
)


ROOT = Path(__file__).parents[1]
CSA101 = ROOT / "src/rocsa_generator/definitions/catalog/csa_101.json"


def load_source() -> dict:
    return json.loads(CSA101.read_text(encoding="utf-8"))


def test_csa_101_structural_validation_and_lossless_round_trip() -> None:
    source = load_source()
    definition = FNCsaDefinition.model_validate(source)
    assert definition.model_dump(mode="json", exclude_none=True) == source
    assert definition.identity.csa_id == "CSA-101"
    assert definition.classification.criticality.value == "CRITICAL"
    assert [state.value for state in definition.results.states] == [
        "PASSED", "FAILED", "NOT_APPLICABLE", "ERROR"
    ]
    assert definition.results.on_failure.value == "BLOCK_DVS"


def test_csa_101_is_not_publishable_before_verified_references() -> None:
    definition = FNCsaDefinition.model_validate(load_source())
    with pytest.raises(ValueError, match="not publishable") as exc:
        definition.assert_publishable()
    message = str(exc.value)
    assert "RMCS references are missing" in message
    assert "ESVP references are missing" in message
    assert "scientific approval is pending" in message


def test_original_incomplete_csa_101_is_rejected() -> None:
    source = load_source()
    for section in ("governance", "scientific_description", "references", "history"):
        source.pop(section)
    with pytest.raises(ValidationError) as exc:
        FNCsaDefinition.model_validate(source)
    missing = {error["loc"][0] for error in exc.value.errors()}
    assert missing == {"governance", "scientific_description", "references", "history"}


@pytest.mark.parametrize("invalid_id", ["CSA-001", "CSA-01", "CSA-1000", "CSA-ABC"])
def test_invalid_csa_id_is_rejected(invalid_id: str) -> None:
    source = load_source()
    source["identity"]["csa_id"] = invalid_id
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)


def test_extra_fields_and_unknown_vocabularies_are_rejected() -> None:
    source = load_source()
    source["identity"]["unexpected"] = True
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)

    source = load_source()
    source["classification"]["criticality"] = "HIGH"
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)


def test_not_applicable_is_not_skipped() -> None:
    source = load_source()
    source["results"]["states"][2] = "SKIPPED"
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)


def test_warning_is_not_a_canonical_result_state() -> None:
    assert "WARNING" not in {state.value for state in ResultState}
    source = load_source()
    source["results"]["states"].append("WARNING")
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)


def test_on_failure_is_required_and_none_is_explicitly_allowed() -> None:
    assert "NONE" in {prescription.value for prescription in FailurePrescription}

    source = load_source()
    source["results"].pop("on_failure")
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)

    source = load_source()
    source["results"]["on_failure"] = "NONE"
    definition = FNCsaDefinition.model_validate(source)
    assert definition.results.on_failure is FailurePrescription.NONE


def test_csa_identifier_v1_is_exactly_three_digits() -> None:
    source = load_source()
    source["identity"]["csa_id"] = "CSA-999"
    assert FNCsaDefinition.model_validate(source).identity.csa_id == "CSA-999"

    source["identity"]["csa_id"] = "CSA-1000"
    with pytest.raises(ValidationError):
        FNCsaDefinition.model_validate(source)


def test_catalog_rejects_duplicate_identifiers() -> None:
    source = load_source()
    with pytest.raises(ValidationError, match="duplicate CSA identifiers"):
        FNCsaCatalog.model_validate({"catalog_version": "1.0.0", "controls": [source, source]})
