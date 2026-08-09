import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union
import uuid
import yaml
from jinja2 import Environment, FileSystemLoader

from rocsa_generator.exceptions import ValidationError
from rocsa_generator.models import (
    CSADefinition,
    CSAFamily,
    GenerationRequest,
    GenerationResult,
    OutputFormat,
)
from rocsa_generator.normalizer import CSANormalizer
from rocsa_generator.registry import RocsaRegistry


class RocsaEngine:
    """Moteur principal du compilateur ROCSA."""

    def __init__(self, output_dir: Optional[Union[str, Path]] = None):
        self.output_dir = Path(output_dir) if output_dir else Path("./output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        template_dir = Path(__file__).parent / "templates"
        if template_dir.exists():
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self.jinja_env = None

    def load_definition(self, file_path: Union[str, Path]) -> Union[dict, list]:
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"Fichier de définition introuvable : {path}")
        
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return json.loads(content)
        elif path.suffix.lower() in [".yaml", ".yml"]:
            return yaml.safe_load(content)
        else:
            raise ValidationError(f"Format non pris en charge : {path.suffix}")

    def validate_definition(
        self,
        raw_data: Union[dict, list],
        file_stem: str = "generic",
        output_format: OutputFormat = OutputFormat.JSON,
    ) -> GenerationRequest:
        normalized: CSADefinition = CSANormalizer.normalize(raw_data, file_stem=file_stem)
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, file_stem))
        
        return GenerationRequest(
            request_id=deterministic_id,
            name=normalized.name,
            format=output_format,
            parameters=normalized.model_dump(),
        )

    def build_sdk(self, file_path: Union[str, Path]) -> GenerationResult:
        path = Path(file_path)
        raw_data = self.load_definition(path)
        
        fmt = OutputFormat.YAML if path.suffix.lower() in [".yaml", ".yml"] else OutputFormat.JSON
        request = self.validate_definition(raw_data, file_stem=path.stem, output_format=fmt)
        
        ext = ".json" if request.format == OutputFormat.JSON else ".yaml"
        target_path = self.output_dir / f"{request.name}{ext}"
        
        payload = request.model_dump(mode="json")
        if request.format == OutputFormat.JSON:
            target_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        else:
            target_path.write_text(yaml.dump(payload), encoding="utf-8")
            
        return GenerationResult(
            request_id=request.request_id,
            success=True,
            output_path=str(target_path),
            metadata={"controls_count": len(request.parameters.get("controls", []))},
        )

    def generate_sdk(self, registry: RocsaRegistry, target_dir: Optional[Union[str, Path]] = None) -> Path:
        """Génère l'arborescence complète du SDK exécutable rocsa/."""
        sdk_root = Path(target_dir) if target_dir else self.output_dir / "rocsa"
        sdk_root.mkdir(parents=True, exist_ok=True)
        
        init_content = '"""ROCSA SDK Package"""\n__version__ = "0.1.0"\n\ntry:\n    from rocsa.core import BaseCSA, CSAContext, CSAResult, CSAExecutionEngine\n    from rocsa.integration import RMCSValidatorFacade\nexcept ImportError:\n    pass\n'
        (sdk_root / "__init__.py").write_text(init_content, encoding="utf-8")
        
        core_src = Path(__file__).parent.parent / "rocsa" / "core"
        core_dest = sdk_root / "core"
        core_dest.mkdir(parents=True, exist_ok=True)
        if core_src.exists():
            for item in core_src.glob("*.py"):
                (core_dest / item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

        integ_src = Path(__file__).parent.parent / "rocsa" / "integration"
        integ_dest = sdk_root / "integration"
        integ_dest.mkdir(parents=True, exist_ok=True)
        if integ_src.exists():
            for item in integ_src.glob("*.py"):
                (integ_dest / item.name).write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
        
        index_yaml = {}
        timestamp = datetime.now(timezone.utc).isoformat()
        
        template = self.jinja_env.get_template("control_class.py.j2") if self.jinja_env else None
        
        for entry in registry.list_all():
            csa_def: CSADefinition = entry.definition
            fam_folder_name = csa_def.family.value.lower().split("_")[-1]
            fam_dir = sdk_root / fam_folder_name
            fam_dir.mkdir(parents=True, exist_ok=True)
            (fam_dir / "__init__.py").touch()
            
            fam_index = []
            for control in csa_def.controls:
                ctrl_file_name = f"{control.control_id.lower().replace('-', '_')}.py"
                ctrl_file_path = fam_dir / ctrl_file_name
                
                if template:
                    code = template.render(
                        control=control,
                        definition=csa_def,
                        timestamp=timestamp,
                    )
                    ctrl_file_path.write_text(code, encoding="utf-8")
                
                fam_index.append({
                    "control_id": control.control_id,
                    "semantic_code": control.semantic_code,
                    "title": control.title,
                    "module": f"rocsa.{fam_folder_name}.{ctrl_file_name[:-3]}",
                    "class_name": control.control_id.replace("-", "").replace("_", "").upper(),
                })
            
            index_yaml[csa_def.family.value] = fam_index
            
        (sdk_root / "registry.yaml").write_text(yaml.dump(index_yaml, indent=2), encoding="utf-8")
        
        return sdk_root
