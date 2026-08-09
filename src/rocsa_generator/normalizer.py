from typing import Any, List
from rocsa_generator.models.csa import (
    CSAControl,
    CSADefinition,
    CSAFamily,
    CSASeverity,
)


class CSANormalizer:
    @staticmethod
    def _detect_family(file_stem: str) -> CSAFamily:
        stem_upper = file_stem.upper()
        for fam in CSAFamily:
            if fam.value in stem_upper or fam.name in stem_upper:
                return fam
        return CSAFamily.DOCUMENTARY

    @staticmethod
    def normalize(raw_data: Any, file_stem: str = "generic") -> CSADefinition:
        if isinstance(raw_data, CSADefinition):
            return raw_data

        if isinstance(raw_data, dict) and "identity_code" in raw_data and "controls" in raw_data:
            return CSADefinition(**raw_data)

        if isinstance(raw_data, list):
            controls: List[CSAControl] = []
            family = CSANormalizer._detect_family(file_stem)
            for idx, item in enumerate(raw_data):
                if isinstance(item, dict):
                    raw_id = item.get("control_id") if item.get("control_id") is not None else item.get("id")
                    ctrl_id = str(raw_id) if raw_id is not None else f"CSA-{idx+1:03d}"
                    sem_code = str(item.get("semantic_code") or f"CSA-{file_stem.upper()}-{idx+1:02d}")
                    title = str(item.get("title") or item.get("name") or "Contrôle sans titre")
                    sev_raw = str(item.get("severity", "MEDIUM")).upper()
                    try:
                        severity = CSASeverity(sev_raw)
                    except ValueError:
                        severity = CSASeverity.MEDIUM

                    controls.append(
                        CSAControl(
                            control_id=ctrl_id,
                            semantic_code=sem_code,
                            title=title,
                            severity=severity,
                            family=family,
                        )
                    )

            return CSADefinition(
                identity_code=file_stem.upper(),
                name=file_stem,
                family=family,
                description=f"Définition normalisée depuis {file_stem}",
                controls=controls,
            )

        if isinstance(raw_data, dict):
            family = CSANormalizer._detect_family(file_stem)
            return CSADefinition(
                identity_code=file_stem.upper(),
                name=file_stem,
                family=family,
                description=f"Définition dictionnaire depuis {file_stem}",
                controls=[],
            )

        raise ValueError(f"Format de données non pris en charge : {type(raw_data)}")
