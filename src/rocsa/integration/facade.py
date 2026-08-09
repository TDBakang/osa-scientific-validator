from pathlib import Path
from typing import List, Optional, Union

from rocsa.core.context import CSAContext
from rocsa.core.engine import CSAExecutionEngine
from rocsa.core.report import CSAReport
from rocsa.core.result import CSAResult
from rocsa_generator.models.csa import CSAFamily, CSASeverity

class RMCSValidatorFacade:
    def __init__(self, engine: CSAExecutionEngine):
        self._engine = engine

    @classmethod
    def load_sdk(cls, sdk_path: Union[str, Path]) -> "RMCSValidatorFacade":
        path = Path(sdk_path)
        registry_file = path / "registry.yaml" if path.is_dir() else path
        engine = CSAExecutionEngine.from_registry(registry_file)
        return cls(engine)

    def run(self, control_id: str, context: CSAContext) -> Optional[CSAResult]:
        return self._engine.run_control(control_id, context)

    def run_family(self, family: Union[CSAFamily, str], context: CSAContext) -> List[CSAResult]:
        if isinstance(family, str):
            for fam in CSAFamily:
                if fam.value.upper() == family.upper() or fam.name.upper() == family.upper():
                    family = fam
                    break
        return self._engine.run_family(family, context)

    def run_severity(self, severity: Union[CSASeverity, str], context: CSAContext) -> List[CSAResult]:
        if isinstance(severity, str):
            try:
                severity = CSASeverity(severity.upper())
            except ValueError:
                pass
        return self._engine.run_by_severity(severity, context)

    def run_all(self, context: CSAContext) -> List[CSAResult]:
        return self._engine.run_all(context)

    def audit_all(self, context: CSAContext) -> CSAReport:
        results = self.run_all(context)
        return CSAReport.generate(context, results)

    def audit_family(self, family: Union[CSAFamily, str], context: CSAContext) -> CSAReport:
        results = self.run_family(family, context)
        return CSAReport.generate(context, results)

    @property
    def loaded_controls_count(self) -> int:
        return len(self._engine.list_loaded_controls())
