from enum import Enum
from typing import Any, Dict
from uuid import UUID
from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"


class GenerationRequest(BaseModel):
    request_id: UUID
    name: str
    format: OutputFormat = OutputFormat.JSON
    parameters: Dict[str, Any] = Field(default_factory=dict)


class GenerationResult(BaseModel):
    request_id: UUID
    success: bool
    output_path: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
