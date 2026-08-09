"""Contrat compilé non exécutable, distinct de la représentation FN-CSA."""

from pydantic import ConfigDict, BaseModel

from .fn_csa import Criticality, CsaId, FailurePrescription, ResultState, SemanticCode


class CompiledCSAControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    control_id: CsaId
    semantic_code: SemanticCode
    title: str
    severity: Criticality
    family: str
    allowed_states: tuple[ResultState, ...]
    on_failure: FailurePrescription


def compile_contract_only(*args: object, **kwargs: object) -> CompiledCSAControl:
    raise RuntimeError("Compilation is outside phase 2.3-B")
