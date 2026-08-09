"""Jalon 2.3-C2 — Artefact de compilation qualifié et traçable.

Ce module N'ÉTEND PAS CompiledCSAControl (D-FNCSA-COMPILE-03, préservée
intacte : cet objet n'a et n'aura jamais de champ de statut de
publication). Il enveloppe un CompiledCSAControl inchangé dans un objet
distinct, CompilationArtifact, qui porte :
    - la provenance de compilation (identifiant source, empreinte
      canonique, version du contrat de compilation) ;
    - la traçabilité champ par champ (registre explicite et fermé) ;
    - le registre explicite des sections source volontairement non
      compilées ;
    - la qualification (éligibilité publication/exécution), calculée
      sans jamais lever d'exception.

compile_artifact() n'appelle jamais assert_publishable() (D-FNCSA-COMPILE-01) :
la qualification est une observation, jamais une barrière.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from .compiled_control import CompiledCSAControl, compile_contract_only
from .fn_csa import (
    CsaId,
    DocumentStatus,
    FNCsaCatalog,
    FNCsaDefinition,
    NonEmpty,
    SemanticVersion,
)


COMPILATION_CONTRACT_VERSION = "1.0.0"

# D-FNCSA-COMPILE-06 (voir DECISIONS-DOCTRINALES-2.3-C2.md) : l'exécution
# n'est PAS encore implémentée dans le projet (Jalon 2.3-D non commencé).
# Cette raison est structurelle et globale au projet, jamais déduite au
# cas par cas d'une fiche particulière.
EXECUTION_NOT_YET_IMPLEMENTED_REASON = (
    "Aucune classe exécutable n'est générée à ce stade du projet "
    "(Jalon 2.3-D non commencé) : execution_eligible est toujours faux, "
    "quelle que soit la fiche source."
)


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Sérialisation JSON canonique : clés triées récursivement (via
    sort_keys), séparateurs compacts, UTF-8 non échappé. Déterministe
    pour un même contenu logique, indépendamment de l'ordre d'insertion
    des clés dans le dict source."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def fingerprint_of(payload: dict[str, Any]) -> str:
    """Empreinte SHA-256 de la représentation canonique d'un payload.

    Note doctrinale (D-FNCSA-COMPILE-06) : cette empreinte est un moyen
    technique de provenance et de traçabilité de compilation. Elle NE
    CONSTITUE PAS l'exécution d'un contrôle scientifique CSA — en
    particulier, elle ne réalise ni ne préfigure la logique métier de
    CSA-101 (vérification d'intégrité cryptographique d'un objet
    scientifique soumis au contrôle). AC-2.3-C-09 reste respecté :
    aucun contrôle CSA n'est exécuté ici, seule une fiche FN-CSA déjà
    validée structurellement est hachée pour traçabilité interne du
    compilateur.
    """
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


class CompilationProvenance(StrictFrozenModel):
    source_csa_id: CsaId
    source_version: SemanticVersion
    source_fingerprint: Sha256Hex
    compiler_contract_version: SemanticVersion


class CompilationTraceEntry(StrictFrozenModel):
    target_field: NonEmpty
    source_path: NonEmpty


class CompilationQualification(StrictFrozenModel):
    source_status: DocumentStatus
    publication_eligible: bool
    publication_blocking_reasons: tuple[NonEmpty, ...]
    execution_eligible: bool
    execution_blocking_reason: NonEmpty


class CompilationArtifact(StrictFrozenModel):
    control: CompiledCSAControl
    provenance: CompilationProvenance
    field_trace: tuple[CompilationTraceEntry, ...]
    omitted_source_sections: tuple[NonEmpty, ...]
    qualification: CompilationQualification


# Registre explicite et fermé : chaque champ compilé -> son chemin source.
# Identique au mapping de compile_contract_only() (2.3-C1) — dupliqué ici
# volontairement sous forme déclarative pour servir de trace vérifiable,
# indépendante du code de compilation lui-même.
FIELD_TRACE_REGISTRY: tuple[tuple[str, str], ...] = (
    ("control_id", "identity.csa_id"),
    ("semantic_code", "identity.semantic_code"),
    ("title", "identity.official_name"),
    ("severity", "classification.criticality"),
    ("family", "classification.family"),
    ("allowed_states", "results.states"),
    ("on_failure", "results.on_failure"),
)

# Registre explicite des sections/champs source volontairement NON
# compilés. Toute évolution de cette liste doit être une décision
# doctrinale explicite, jamais un oubli silencieux.
OMITTED_SOURCE_SECTIONS: tuple[str, ...] = (
    "identity.version",
    "identity.status",
    "classification.sub_family",
    "classification.domains",
    "governance",
    "scientific_description",
    "execution.inputs",
    "execution.preconditions",
    "execution.dependencies",
    "execution.method",
    "execution.parameters",
    "execution.postconditions",
    "results.justification",
    "results.proofs_used",
    "results.rules_applied",
    "results.confidence_level",
    "results.exceptions",
    "references",
    "history",
)


def _qualify(definition: FNCsaDefinition) -> CompilationQualification:
    publishable, reasons = definition.publishability_report()
    return CompilationQualification(
        source_status=definition.identity.status,
        publication_eligible=publishable,
        publication_blocking_reasons=tuple(reasons),
        execution_eligible=False,
        execution_blocking_reason=EXECUTION_NOT_YET_IMPLEMENTED_REASON,
    )


def compile_artifact(definition: FNCsaDefinition) -> CompilationArtifact:
    """Compile une FNCsaDefinition en CompilationArtifact qualifié et
    traçable.

    N'appelle jamais assert_publishable() : la qualification reflète
    l'état réel de la fiche source sans jamais lever d'exception
    bloquante (D-FNCSA-COMPILE-01). Une fiche PROPOSED se compile donc
    toujours avec succès ; seule sa qualification indique qu'elle
    n'est pas publiable.
    """
    control = compile_contract_only(definition)

    source_payload = definition.model_dump(mode="json")
    provenance = CompilationProvenance(
        source_csa_id=definition.identity.csa_id,
        source_version=definition.identity.version,
        source_fingerprint=fingerprint_of(source_payload),
        compiler_contract_version=COMPILATION_CONTRACT_VERSION,
    )

    field_trace = tuple(
        CompilationTraceEntry(target_field=target, source_path=source)
        for target, source in FIELD_TRACE_REGISTRY
    )

    return CompilationArtifact(
        control=control,
        provenance=provenance,
        field_trace=field_trace,
        omitted_source_sections=OMITTED_SOURCE_SECTIONS,
        qualification=_qualify(definition),
    )


def compile_catalog(catalog: FNCsaCatalog) -> tuple[CompilationArtifact, ...]:
    """Compile un catalogue complet, dans l'ordre canonique par csa_id.

    Échec atomique (AC-2.3-C2-09) : si une seule définition échoue à se
    compiler, l'exception se propage immédiatement et aucune sortie
    partielle n'est retournée — pas de compilation silencieuse
    incomplète.

    L'unicité des identifiants (AC-2.3-C2-08) est déjà garantie en
    amont par FNCsaCatalog.ids_are_unique() : un FNCsaCatalog contenant
    des doublons ne peut pas exister, donc ne peut pas être passé ici.
    """
    ordered = sorted(catalog.controls, key=lambda d: d.identity.csa_id)
    return tuple(compile_artifact(definition) for definition in ordered)


def to_canonical_json(artifact: CompilationArtifact) -> str:
    """Sérialise un CompilationArtifact en JSON canonique (clés triées,
    représentation stable et reproductible)."""
    payload = artifact.model_dump(mode="json")
    return canonical_json_bytes(payload).decode("utf-8")


def from_canonical_json(text: str) -> CompilationArtifact:
    """Désérialise un CompilationArtifact depuis du JSON. Rejette tout
    champ inconnu (extra="forbid" à tous les niveaux du modèle)."""
    return CompilationArtifact.model_validate_json(text)
