"""Contrat compilé non exécutable, distinct de la représentation FN-CSA.

Jalon 2.3-C1 : compilation pure et déterministe d'une FNCsaDefinition
structurellement valide vers un CompiledCSAControl.

Ce module ne fait AUCUN des éléments suivants :
    - accès disque, réseau ou base de données ;
    - génération de code exécutable ;
    - exécution d'un algorithme cryptographique ;
    - modification de la fiche source ;
    - appel à assert_publishable() (la compilation ne juge jamais de la
      publiabilité — elle transforme, elle ne valide pas).

La compilation d'une fiche PROPOSED est délibérément autorisée (AC-2.3-C-07) :
compiler techniquement n'est pas publier. L'artefact compilé qui en résulte
ne porte aucune information de statut de publication — il n'a pas de
méthode assert_publishable(), par construction, pour qu'aucun code appelant
ne puisse être tenté de le traiter comme une autorisation.
"""

from pydantic import ConfigDict, BaseModel

from .fn_csa import (
    Criticality,
    CsaId,
    FailurePrescription,
    FamilyId,
    FNCsaDefinition,
    NonEmpty,
    ResultState,
    SemanticCode,
)


class CompiledCSAControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    control_id: CsaId
    semantic_code: SemanticCode
    title: NonEmpty
    severity: Criticality
    family: FamilyId
    allowed_states: tuple[ResultState, ...]
    on_failure: FailurePrescription


def compile_contract_only(definition: FNCsaDefinition) -> CompiledCSAControl:
    """Compile une FNCsaDefinition en CompiledCSAControl, sans effet de bord.

    Mapping strict, actée au journal 2.3-C (aucun champ inventé ni déduit) :
        identity.csa_id                -> control_id
        identity.semantic_code         -> semantic_code
        identity.official_name         -> title
        classification.criticality     -> severity
        classification.family          -> family
        results.states                 -> allowed_states
        results.on_failure             -> on_failure

    Ne lit ni n'écrit rien en dehors de l'objet `definition` passé en
    argument. Ne modifie pas `definition`. Ne consulte pas et n'appelle
    pas `definition.assert_publishable()`.
    """
    return CompiledCSAControl(
        control_id=definition.identity.csa_id,
        semantic_code=definition.identity.semantic_code,
        title=definition.identity.official_name,
        severity=definition.classification.criticality,
        family=definition.classification.family,
        allowed_states=tuple(definition.results.states),
        on_failure=definition.results.on_failure,
    )
