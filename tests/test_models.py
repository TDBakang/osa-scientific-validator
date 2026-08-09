import uuid
import pytest
from pydantic import ValidationError
from rocsa_generator.models import GenerationRequest, GenerationResult, OutputFormat

def test_generation_request_valid_uuid():
    valid_uuid = str(uuid.uuid4())
    req = GenerationRequest(
        request_id=valid_uuid,
        name="test_request",
        format=OutputFormat.JSON,
        parameters={"key": "value"},
    )
    assert str(req.request_id) == valid_uuid

def test_generation_request_invalid_uuid():
    with pytest.raises(ValidationError):
        GenerationRequest(
            request_id="INVALID_STRING_REQ_100",
            name="test_request",
            format=OutputFormat.JSON,
            parameters={},
        )
