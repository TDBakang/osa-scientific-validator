from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class CSAContext(BaseModel):
    execution_id: str = Field(..., description="ID execution audit")
    target_name: str = Field(..., description="Cible audit")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    file_paths: Dict[str, Path] = Field(default_factory=dict)
    environment: Dict[str, str] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)

    def get_artifact(self, key: str) -> Optional[Any]:
        if key in self.payload:
            return self.payload[key]
        if key in self.file_paths:
            return self.file_paths[key]
        return None
