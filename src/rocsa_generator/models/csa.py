from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CSASeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CSAFamily(str, Enum):
    CRYPTO = "100_CRYPTO"
    DOCUMENTARY = "200_DOCUMENTARY"
    PROOFS = "300_PROOFS"
    DOCTRINAL = "400_DOCTRINAL"
    METHODOLOGY = "500_METHODOLOGY"
    ENGINES = "600_ENGINES"
    COHERENCE = "700_COHERENCE"
    GOVERNANCE = "800_GOVERNANCE"
    AUDIT = "900_AUDIT"


class EvidenceLevel(str, Enum):
    MATHEMATICAL_PROOF = "L3_MATH_PROOF"
    CRYPTOGRAPHIC_VERIFICATION = "L2_CRYPTO_VERIF"
    DOCUMENTARY_EVIDENCE = "L1_DOC_EVIDENCE"
    DECLARATIVE = "L0_DECLARATIVE"


class CSATrace(BaseModel):
    version: str = "1.0.0"
    deprecated: bool = False
    supersedes: Optional[str] = None
    requires: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class CSAMetadata(BaseModel):
    author: Optional[str] = None
    engine: Optional[str] = None
    evidence_level: EvidenceLevel = EvidenceLevel.DOCUMENTARY_EVIDENCE
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)


class CSARequirement(BaseModel):
    code: str
    description: str
    mandatory: bool = True


class CSAControl(BaseModel):
    control_id: str
    semantic_code: str
    title: str
    severity: CSASeverity = CSASeverity.MEDIUM
    family: CSAFamily = CSAFamily.DOCUMENTARY
    requirements: List[CSARequirement] = Field(default_factory=list)


class CSADefinition(BaseModel):
    """Objet central du compilateur ROCSA : la définition scientifique d'une règle ou famille CSA."""
    identity_code: str
    name: str
    family: CSAFamily = CSAFamily.DOCUMENTARY
    description: str = ""
    controls: List[CSAControl] = Field(default_factory=list)
    traceability: CSATrace = Field(default_factory=CSATrace)
    metadata: CSAMetadata = Field(default_factory=CSAMetadata)
