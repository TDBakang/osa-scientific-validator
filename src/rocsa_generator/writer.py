"""Writer transactionnel (2.3-D-L3) : inspection sûre, résolution des
markers, publication atomique, rollback sélectif vérifié par ownership.

Révisé après revue de sécurité du 2026-08-11 (voir DECISION-2.3-D-L3.md,
addendum) : le rollback ne supprime jamais un fichier sans avoir vérifié
que son (device, inode) actuel correspond exactement à ce que ce run a
publié — jamais l'objet d'un processus concurrent.

Principe : toute la phase d'inspection est en lecture seule et ne crée
jamais de répertoire (SCAFFOLD-13, atomicité — rien n'est écrit tant que
l'état complet du lot n'est pas connu). Si l'inspection détecte un état
disque incompatible avec le mode demandé, rien n'est écrit et aucun
rollback n'est nécessaire.

Hors périmètre volontaire : rien ici ne valide scientifiquement CSA-101,
n'autorise sa publication, ni son exécution (authority.* reste inchangé,
toujours False à ce stade du projet).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .canonical import canonical_json, sha256 as sha256_of
from .safe_fs import (
    OwnedDirectory, PathSafetyError, close_owned_directories,
    lock_root_exclusive, lstat_leaf,
    open_root_dir_fd, read_leaf_nofollow, remove_directory_if_empty_and_owned,
    remove_leaf_if_owned, stage_and_publish, unlock_root,
)
from .scaffold_models import RenderedFile, RenderedScaffold
from .writer_models import (
    DirectoryRollbackRecord, FileWriteRecord, FinalManifest,
    PublicationReport, TransactionState, WriteMode,
)


class PublicationRefused(RuntimeError):
    """Levée quand l'inspection préalable (lecture seule) détecte un état
    disque incompatible avec le mode demandé. Rien n'est écrit dans ce
    cas — pas de rollback nécessaire, le refus est propre."""


def _resolved_labels(needs_write: bool) -> tuple[str, str]:
    """Correspond exactement à la table de D-SCAFFOLD-22 : un fichier créé
    par ce run est CREATED/CURRENT_RUN, un fichier préexistant vérifié
    conforme est REUSED/PREEXISTING_SHARED."""
    return ("CREATED", "CURRENT_RUN") if needs_write else ("REUSED", "PREEXISTING_SHARED")


def _inspect_infrastructure(root_fd: int, marker: RenderedFile) -> bool:
    """Inspecte un marker de paquet (lecture seule, ne crée jamais de
    répertoire). Retourne True si une écriture est nécessaire (absent),
    False si préexistant et conforme. Lève PublicationRefused sinon."""
    st = lstat_leaf(root_fd, marker.relative_path)
    if st is None:
        return True
    if not stat.S_ISREG(st.st_mode):
        raise PublicationRefused(f"marker exists but is not a regular file: {marker.relative_path}")
    if st.st_size != 0:
        raise PublicationRefused(f"marker exists with non-empty content, refusing (no FORCE): {marker.relative_path}")
    content = read_leaf_nofollow(root_fd, marker.relative_path)
    if content != b"":
        raise PublicationRefused(f"marker content changed between stat and read: {marker.relative_path}")
    return False


def _inspect_payload(root_fd: int, payload: RenderedFile, mode: WriteMode) -> bool:
    """Inspecte un fichier de charge utile (lecture seule, ne crée jamais
    de répertoire). Retourne True si une écriture est nécessaire, False
    si déjà présent et identique (idempotent, REGENERATE_VERIFIED
    uniquement). Lève PublicationRefused si présent et incompatible."""
    st = lstat_leaf(root_fd, payload.relative_path)
    if st is None:
        return True
    if mode is WriteMode.CREATE_ONLY:
        raise PublicationRefused(f"payload already exists (CREATE_ONLY mode): {payload.relative_path}")
    if not stat.S_ISREG(st.st_mode):
        raise PublicationRefused(f"payload exists but is not a regular file: {payload.relative_path}")
    existing = read_leaf_nofollow(root_fd, payload.relative_path)
    if existing != payload.content:
        raise PublicationRefused(
            f"payload exists with different content, refusing overwrite (no FORCE mode exists): {payload.relative_path}"
        )
    return False


def _build_final_manifest(
    rendered: RenderedScaffold,
    infra_plan: list[tuple[RenderedFile, bool]],
    payload_plan: list[tuple[RenderedFile, bool]],
) -> FinalManifest:
    draft = rendered.manifest_draft
    payload_files = []
    for (payload, needs_write), original in zip(payload_plan, draft.payload_files):
        materialization, ownership = _resolved_labels(needs_write)
        payload_files.append({**original, "materialization": materialization, "ownership": ownership})
    infra_files = []
    for (marker, needs_write), original in zip(infra_plan, draft.infrastructure_files):
        materialization, ownership = _resolved_labels(needs_write)
        infra_files.append({**original, "materialization": materialization, "ownership": ownership})
    fingerprint_input = {"payload_files": payload_files, "infrastructure_files": infra_files}
    bundle_fingerprint = sha256_of(canonical_json(fingerprint_input))
    return FinalManifest(
        manifest_schema_version=draft.manifest_schema_version,
        scaffold_contract_version=draft.scaffold_contract_version,
        generator_version=draft.generator_version,
        template_set_version=draft.template_set_version,
        renderer_id=draft.renderer_id,
        canonicalization_version=draft.canonicalization_version,
        source=draft.source,
        qualification=draft.qualification,
        authority=draft.authority,
        payload_files=tuple(payload_files),
        infrastructure_files=tuple(infra_files),
        bundle_fingerprint=bundle_fingerprint,
        write_completed=True,
    )


def publish_scaffold(
    rendered: RenderedScaffold, root: Path, mode: WriteMode
) -> tuple[PublicationReport, FinalManifest | None]:
    """Publie un scaffold rendu par L2 sur disque, de façon transactionnelle.

    Retourne (rapport, manifeste_final). Le manifeste final est None si la
    publication a été refusée dès l'inspection (rien n'a été écrit) ou si
    un rollback a eu lieu suite à un échec en cours d'écriture.
    """
    root_fd = open_root_dir_fd(root)
    locked = False
    try:
        lock_root_exclusive(root_fd)
        locked = True
        # --- Phase 1 : inspection en lecture seule, aucune écriture, ---
        # --- aucun répertoire créé ---
        try:
            infra_plan = [(marker, _inspect_infrastructure(root_fd, marker)) for marker in rendered.infrastructure_files]
            payload_plan = [(payload, _inspect_payload(root_fd, payload, mode)) for payload in rendered.payload_files]
        except (PublicationRefused, PathSafetyError) as exc:
            return (
                PublicationReport(mode=mode, write_completed=False, rollback_performed=False, records=(), refusal_reason=str(exc)),
                None,
            )

        # --- Phase 2 : publication atomique, fichier par fichier ---
        # Suivi interne pour le rollback : (relative_path, dev, ino), et
        # les répertoires créés (pour rollback si encore vides ensuite).
        published_this_run: list[tuple[str, int, int, int]] = []
        created_dirs_this_run: list[OwnedDirectory] = []
        records: list[FileWriteRecord] = []
        try:
            for marker, needs_write in infra_plan:
                if needs_write:
                    dev, ino, ctime_ns = stage_and_publish(
                        root_fd, marker.relative_path, marker.content,
                        created_dirs_this_run,
                    )
                    published_this_run.append((marker.relative_path, dev, ino, ctime_ns))
                    records.append(FileWriteRecord(relative_path=marker.relative_path, state=TransactionState.PUBLISHED, sha256=marker.sha256, owned_by_run=True))
                else:
                    records.append(FileWriteRecord(relative_path=marker.relative_path, state=TransactionState.REUSED_VERIFIED, sha256=marker.sha256, owned_by_run=False))
            for payload, needs_write in payload_plan:
                if needs_write:
                    # Garanti absent à ce stade (phase 1 a déjà refusé tout
                    # cas "présent et différent" ; "présent et identique"
                    # donne needs_write=False, jamais True).
                    dev, ino, ctime_ns = stage_and_publish(
                        root_fd, payload.relative_path, payload.content,
                        created_dirs_this_run,
                    )
                    published_this_run.append((payload.relative_path, dev, ino, ctime_ns))
                    records.append(FileWriteRecord(relative_path=payload.relative_path, state=TransactionState.PUBLISHED, sha256=payload.sha256, owned_by_run=True))
                else:
                    records.append(FileWriteRecord(relative_path=payload.relative_path, state=TransactionState.REUSED_VERIFIED, sha256=payload.sha256, owned_by_run=False))
        except Exception as exc:
            file_outcomes: dict[str, str] = {}
            for path, dev, ino, ctime_ns in reversed(published_this_run):
                try:
                    outcome = remove_leaf_if_owned(root_fd, path, dev, ino, ctime_ns)
                except BaseException as rollback_exc:  # rapport obligatoire
                    outcome = f"IO_ERROR:{type(rollback_exc).__name__}:{rollback_exc}"
                file_outcomes[path] = outcome
            # Répertoires créés par ce run, retirés uniquement s'ils sont
            # encore vides (jamais s'ils contiennent quelque chose,
            # même déposé par un tiers pendant la fenêtre du run).
            directory_records: list[DirectoryRollbackRecord] = []
            for owned_dir in reversed(created_dirs_this_run):
                try:
                    outcome = remove_directory_if_empty_and_owned(root_fd, owned_dir)
                except BaseException as rollback_exc:  # défense ultime
                    outcome = f"IO_ERROR:{type(rollback_exc).__name__}:{rollback_exc}"
                directory_records.append(
                    DirectoryRollbackRecord(
                        relative_path=owned_dir.relative_path, outcome=outcome
                    )
                )

            published_paths = {p for p, _, _, _ in published_this_run}
            rolled_back_records = tuple(
                FileWriteRecord(
                    relative_path=r.relative_path,
                    state=(
                        TransactionState.ROLLED_BACK
                        if file_outcomes.get(r.relative_path) in ("ROLLED_BACK", "ALREADY_ABSENT")
                        else TransactionState.ROLLBACK_FAILED
                    ),
                    sha256=r.sha256,
                    owned_by_run=r.owned_by_run,
                    detail=file_outcomes.get(r.relative_path),
                )
                if r.relative_path in published_paths else r
                for r in records
            )
            return (
                PublicationReport(
                    mode=mode, write_completed=False, rollback_performed=True,
                    records=rolled_back_records,
                    directory_rollbacks=tuple(directory_records),
                    refusal_reason=f"{type(exc).__name__}: {exc}",
                ),
                None,
            )

        report = PublicationReport(mode=mode, write_completed=True, rollback_performed=False, records=tuple(records), refusal_reason=None)
        final_manifest = _build_final_manifest(rendered, infra_plan, payload_plan)
        return report, final_manifest
    finally:
        if 'created_dirs_this_run' in locals():
            close_owned_directories(created_dirs_this_run)
        if locked:
            unlock_root(root_fd)
        os.close(root_fd)
