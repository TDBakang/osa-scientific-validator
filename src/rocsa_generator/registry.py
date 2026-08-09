import json
from pathlib import Path
from typing import Dict, List, Optional, Union
import yaml
from pydantic import BaseModel, Field

from rocsa_generator.models.csa import CSADefinition, CSAFamily, CSASeverity
from rocsa_generator.normalizer import CSANormalizer


class RegistryEntry:
    def __init__(self, entry_id: str, file_path: Path, definition: CSADefinition):
        self.entry_id = entry_id
        self.file_path = file_path
        self.definition = definition

    @property
    def family(self) -> CSAFamily:
        return self.definition.family

    @property
    def control_count(self) -> int:
        return len(self.definition.controls)


class RegistryIndex(BaseModel):
    total_entries: int = 0
    families: Dict[str, int] = Field(default_factory=dict)


class RocsaRegistry:
    def __init__(self):
        self._entries: Dict[str, RegistryEntry] = {}

    def register(self, entry_id: str, file_path: Path, raw_data: Union[dict, list, CSADefinition]) -> RegistryEntry:
        normalized_def = CSANormalizer.normalize(raw_data, file_stem=file_path.stem)
        entry = RegistryEntry(entry_id=entry_id, file_path=file_path, definition=normalized_def)
        self._entries[entry_id] = entry
        return entry

    def get(self, entry_id: str) -> Optional[RegistryEntry]:
        return self._entries.get(entry_id)

    def list_all(self) -> List[RegistryEntry]:
        return list(self._entries.values())

    def search_by_family(self, family: CSAFamily) -> List[RegistryEntry]:
        return [entry for entry in self._entries.values() if entry.family == family]

    def search_by_severity(self, severity: CSASeverity) -> List[RegistryEntry]:
        return [
            entry for entry in self._entries.values()
            if any(ctrl.severity == severity for ctrl in entry.definition.controls)
        ]

    def get_index(self) -> RegistryIndex:
        families_count: Dict[str, int] = {}
        for entry in self._entries.values():
            fam_key = entry.family.value
            families_count[fam_key] = families_count.get(fam_key, 0) + 1
        return RegistryIndex(
            total_entries=len(self._entries),
            families=families_count
        )

    def scan_directory(self, target_dir: Path) -> int:
        count = 0
        if not target_dir.exists():
            return count

        for file_path in target_dir.glob("**/*"):
            if file_path.suffix.lower() in [".json", ".yaml", ".yml"]:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    if file_path.suffix.lower() == ".json":
                        raw_data = json.loads(content)
                    else:
                        raw_data = yaml.safe_load(content)

                    if raw_data is not None:
                        entry_id = file_path.stem
                        self.register(entry_id, file_path, raw_data)
                        count += 1
                except Exception:
                    continue
        return count
