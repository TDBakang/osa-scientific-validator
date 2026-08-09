import importlib
from pathlib import Path
from typing import Dict, List, Optional, Union
import yaml

from rocsa.core.base_csa import BaseCSA
from rocsa.core.context import CSAContext
from rocsa.core.result import CSAResult
from rocsa_generator.models.csa import CSAFamily, CSASeverity

class CSAExecutionEngine:
    def __init__(self):
        self._registry: Dict[str, BaseCSA] = {}

    def register(self, control: BaseCSA) -> None:
        self._registry[control.control_id] = control

    @classmethod
    def from_registry(cls, registry_file: Union[str, Path]) -> "CSAExecutionEngine":
        engine = cls()
        engine.load_registry(registry_file)
        return engine

    def load_registry(self, registry_file: Union[str, Path]) -> int:
        path = Path(registry_file)
        if not path.exists():
            raise FileNotFoundError(f"Fichier de registre introuvable : {path}")

        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not content:
            return 0

        count = 0
        for family_name, controls in content.items():
            for ctrl_info in controls:
                module_name = ctrl_info["module"]
                class_name = ctrl_info["class_name"]
                try:
                    module = importlib.import_module(module_name)
                    csa_class = getattr(module, class_name)
                    instance = csa_class()
                    self.register(instance)
                    count += 1
                except (ImportError, AttributeError) as exc:
                    print(f"[AVERTISSEMENT] Impossible de charger {module_name}.{class_name}: {exc}")
                    continue
        return count

    def run_control(self, control_id: str, context: CSAContext) -> Optional[CSAResult]:
        control = self._registry.get(control_id)
        if not control:
            return None
        return control.run(context)

    def run_family(self, family: Union[CSAFamily, str], context: CSAContext) -> List[CSAResult]:
        target_family = family.value if isinstance(family, CSAFamily) else str(family)
        return [ctrl.run(context) for ctrl in self._registry.values() if ctrl.family.value == target_family]

    def run_by_severity(self, severity: Union[CSASeverity, str], context: CSAContext) -> List[CSAResult]:
        target_severity = severity.value if isinstance(severity, CSASeverity) else str(severity)
        return [ctrl.run(context) for ctrl in self._registry.values() if ctrl.severity.value == target_severity]

    def run_all(self, context: CSAContext) -> List[CSAResult]:
        return [ctrl.run(context) for ctrl in self._registry.values()]

    def list_loaded_controls(self) -> List[str]:
        return list(self._registry.keys())
