from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from rocsa_generator.models.csa import CSAFamily, CSASeverity, EvidenceLevel

class CSAStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"

class EvidenceItem(BaseModel):
    code: str
    description: str
    level: EvidenceLevel = EvidenceLevel.DOCUMENTARY_EVIDENCE
    raw_data: Optional[Dict[str, Any]] = None

class CSAResult(BaseModel):
    control_id: str
    semantic_code: str
    family: CSAFamily
    severity: CSASeverity
    status: CSAStatus
    title: str = ""
    summary: str = ""
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidences: List[EvidenceItem] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
