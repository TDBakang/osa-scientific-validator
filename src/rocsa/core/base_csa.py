import time
from abc import ABC, abstractmethod
from typing import List
from rocsa.core.context import CSAContext
from rocsa.core.result import CSAResult, CSAStatus
from rocsa_generator.models.csa import CSAFamily, CSASeverity

class BaseCSA(ABC):
    control_id: str
    semantic_code: str
    title: str
    family: CSAFamily
    severity: CSASeverity
    requirements: List[str] = []

    def run(self, context: CSAContext) -> CSAResult:
        start_time = time.perf_counter()
        try:
            result = self.execute(context)
        except Exception as exc:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            result = CSAResult(
                control_id=self.control_id,
                semantic_code=self.semantic_code,
                family=self.family,
                severity=self.severity,
                status=CSAStatus.ERROR,
                title=self.title,
                summary=f"Erreur d'exécution : {str(exc)}",
                execution_time_ms=elapsed,
                observations=[f"Exception: {type(exc).__name__} - {str(exc)}"],
            )
        else:
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000.0
        return result

    @abstractmethod
    def execute(self, context: CSAContext) -> CSAResult:
        pass
