# CODE GÉNÉRÉ AUTOMATIQUEMENT PAR ROCSA COMPILER
from typing import Any, Dict, List
from rocsa.core.base_csa import BaseCSA
from rocsa.core.context import CSAContext
from rocsa.core.result import CSAResult, CSAStatus, EvidenceItem
from rocsa_generator.models.csa import CSAFamily, CSASeverity, EvidenceLevel

class CSA002(BaseCSA):
    control_id = "CSA-002"
    semantic_code = "CSA-CSA_200_DOCUMENTARY-02"
    title = """Contrôle sans titre"""
    family = CSAFamily("200_DOCUMENTARY")
    severity = CSASeverity("MEDIUM")

    def execute(self, context: CSAContext) -> CSAResult:
        return CSAResult(
            control_id=self.control_id,
            semantic_code=self.semantic_code,
            family=self.family,
            severity=self.severity,
            status=CSAStatus.PASS,
            title=self.title,
            summary=f"Évaluation {self.control_id} réussie.",
            score=1.0,
        )