"""Modèles du writer 2.3-D-L3 : modes d'écriture, journal transactionnel,
manifeste final.

D-SCAFFOLD-23 : le manifeste (déclaratif, propriété) et le journal
transactionnel (`PublicationReport`, ce que le run a réellement fait) sont
deux objets distincts, jamais fusionnés.

D-SCAFFOLD-24 : le manifeste final porte `write_completed`, jamais
`publication_ready` (réservé au brouillon L2, verrouillé à False).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from .scaffold_models import NonEmpty, Sha256, ToolSemVer, StrictModel


class WriteMode(StrEnum):
    CREATE_ONLY = "CREATE_ONLY"
    REGENERATE_VERIFIED = "REGENERATE_VERIFIED"


class TransactionState(StrEnum):
    """Vocabulaire du journal transactionnel (D-SCAFFOLD-23) — distinct des
    ResultState canoniques FN-CSA (PASSED/FAILED/NOT_APPLICABLE/ERROR,
    D-FNCSA-RESULT-01). Jamais fusionnés ni substitués l'un à l'autre."""
    CREATED = "CREATED"
    REUSED_VERIFIED = "REUSED_VERIFIED"
    STAGED = "STAGED"
    PUBLISHED = "PUBLISHED"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    REFUSED = "REFUSED"


class FileWriteRecord(StrictModel):
    relative_path: NonEmpty
    state: TransactionState
    sha256: Sha256
    # True uniquement si CE run a créé le fichier (donc éligible au
    # rollback). Un fichier REUSED_VERIFIED n'est jamais owned_by_run.
    owned_by_run: bool
    detail: str | None = None


class DirectoryRollbackRecord(StrictModel):
    relative_path: NonEmpty
    outcome: NonEmpty


class PublicationReport(StrictModel):
    mode: WriteMode
    write_completed: bool
    rollback_performed: bool
    records: tuple[FileWriteRecord, ...]
    directory_rollbacks: tuple[DirectoryRollbackRecord, ...] = ()
    refusal_reason: NonEmpty | None = None


class FinalManifest(StrictModel):
    """Manifeste final, produit uniquement après écriture (ou constat de
    réutilisation vérifiée) réussie. Remplace ManifestDraft — jamais les
    deux en même temps pour un même run."""
    manifest_schema_version: ToolSemVer
    scaffold_contract_version: ToolSemVer
    generator_version: ToolSemVer
    template_set_version: ToolSemVer
    renderer_id: str
    canonicalization_version: ToolSemVer
    source: dict[str, object]
    qualification: dict[str, object]
    authority: dict[str, bool]
    payload_files: tuple[dict[str, object], dict[str, object]]
    infrastructure_files: tuple[dict[str, object], ...]
    bundle_fingerprint: Sha256
    write_completed: bool
