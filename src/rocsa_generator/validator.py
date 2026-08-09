from pathlib import Path
from typing import Any, Union
import json
import yaml

from rocsa_generator.models.csa import CSADefinition
from rocsa_generator.normalizer import CSANormalizer


class RocsaValidator:
    """Validateur scientifique pour les définitions ROCSA."""

    def __init__(self):
        pass

    def validate(self, raw_data: Any, file_stem: str = "generic") -> CSADefinition:
        return CSANormalizer.normalize(raw_data, file_stem=file_stem)

    def validate_file(self, file_path: Union[str, Path]) -> CSADefinition:
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            raw_data = json.loads(content)
        else:
            raw_data = yaml.safe_load(content)
        return self.validate(raw_data, file_stem=path.stem)
