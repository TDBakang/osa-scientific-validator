import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


ROOT = Path(__file__).parents[1]
DEFINITIONS = ROOT / "src/rocsa_generator/definitions"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def control() -> dict:
    return read(DEFINITIONS / "catalog/csa_101.json")


@pytest.fixture
def control_schema() -> dict:
    return read(DEFINITIONS / "schema/fn_csa.schema.json")


@pytest.fixture
def catalog_schema() -> dict:
    return read(DEFINITIONS / "schema/csa_catalog.schema.json")


def test_schemas_are_valid_draft_2020_12(control_schema: dict, catalog_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(control_schema)
    jsonschema.Draft202012Validator.check_schema(catalog_schema)


def test_control_and_catalog_are_distinct(
    control: dict, control_schema: dict, catalog_schema: dict
) -> None:
    catalog = {"catalog_version": "1.0.0", "controls": [control]}
    jsonschema.validate(control, control_schema)
    jsonschema.validate(catalog, catalog_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(control, catalog_schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(catalog, control_schema)


def test_json_schema_rejects_incomplete_source(control: dict, control_schema: dict) -> None:
    for section in ("governance", "scientific_description", "references", "history"):
        control.pop(section)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(control, control_schema)


def test_json_schema_rejects_extra_fields(control: dict, control_schema: dict) -> None:
    control["identity"]["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(control, control_schema)
