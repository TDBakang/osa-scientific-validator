import json
import uuid
from pathlib import Path
import pytest
import yaml

from rocsa_generator.engine import RocsaEngine
from rocsa_generator.exceptions import ValidationError
from rocsa_generator.models import GenerationRequest


@pytest.fixture
def temp_output_dir(tmp_path):
    return tmp_path / "output"


@pytest.fixture
def engine(temp_output_dir):
    return RocsaEngine(output_dir=temp_output_dir)


@pytest.fixture
def mock_catalog_json(tmp_path):
    json_path = tmp_path / "csa_test_catalog.json"
    content = [
        {"control_id": "TEST-01", "name": "Control 1"},
        {"control_id": "TEST-02", "name": "Control 2"},
    ]
    json_path.write_text(json.dumps(content), encoding="utf-8")
    return json_path


def test_load_definition_valid_file(engine, mock_catalog_json):
    data = engine.load_definition(mock_catalog_json)
    assert isinstance(data, list)
    assert len(data) == 2


def test_load_definition_missing_file(engine, tmp_path):
    missing_file = tmp_path / "non_existent.json"
    with pytest.raises(ValidationError):
        engine.load_definition(missing_file)


def test_validate_definition_list_payload(engine):
    raw_list = [{"id": 1}, {"id": 2}]
    request = engine.validate_definition(raw_list)

    assert isinstance(request, GenerationRequest)
    assert uuid.UUID(str(request.request_id))
    assert "controls" in request.parameters
    assert len(request.parameters["controls"]) == 2
    assert request.parameters["controls"][0]["control_id"] == "1"
    assert request.parameters["controls"][1]["control_id"] == "2"


def test_build_sdk_from_json_file(engine, mock_catalog_json, temp_output_dir):
    result = engine.build_sdk(mock_catalog_json)

    assert result.success is True
    assert Path(result.output_path).exists()
    assert Path(result.output_path).parent == temp_output_dir

    generated_data = json.loads(Path(result.output_path).read_text(encoding="utf-8"))
    assert "request_id" in generated_data
    assert generated_data["name"] == "csa_test_catalog"


def test_build_sdk_deterministic_uuid(engine, mock_catalog_json):
    expected_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, mock_catalog_json.stem))

    result1 = engine.build_sdk(mock_catalog_json)
    result2 = engine.build_sdk(mock_catalog_json)

    assert str(result1.request_id) == expected_uuid
    assert str(result2.request_id) == expected_uuid


def test_build_sdk_yaml_format(engine, tmp_path):
    yaml_file = tmp_path / "csa_yaml_test.yaml"
    content = {"format": "yaml", "parameters": {"key": "value"}}
    yaml_file.write_text(yaml.dump(content), encoding="utf-8")

    result = engine.build_sdk(yaml_file)

    assert result.success is True
    assert result.output_path.endswith(".yaml")
    assert Path(result.output_path).exists()
