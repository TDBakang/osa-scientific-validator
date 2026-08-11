"""Tests du writer 2.3-D-L3, sur vrai système de fichiers (tmp_path).

Inclut les cas adversariaux identifiés lors de la revue de sécurité du
2026-08-11 : échappement de racine, préflight non-mutant, apparition
concurrente avant publication, perte d'ownership avant rollback, écriture
partielle, fichiers spéciaux, absence de résidus temporaires.
"""

from __future__ import annotations

import fcntl
import os
import stat as stat_module
from pathlib import Path

import pytest

from rocsa_generator.models import CompiledCSAControl, CompilationArtifact, CompilationProvenance, CompilationQualification
from rocsa_generator.models.fn_csa import Criticality, DocumentStatus, FailurePrescription, ResultState
from rocsa_generator.scaffold_models import ScaffoldConfiguration
from rocsa_generator.scaffold_planner import build_scaffold_plan
from rocsa_generator.scaffold_renderer import render_scaffold
from rocsa_generator import safe_fs
from rocsa_generator.writer import PublicationRefused, publish_scaffold
from rocsa_generator.writer_models import TransactionState, WriteMode


def _artifact() -> CompilationArtifact:
    control = CompiledCSAControl(
        control_id="CSA-101", semantic_code="CRYPTO.INTEGRITY.VERIFY",
        title="Contrôle d'intégrité cryptographique", severity=Criticality.CRITICAL,
        family="CSA-100", allowed_states=(ResultState.PASSED, ResultState.FAILED, ResultState.NOT_APPLICABLE, ResultState.ERROR),
        on_failure=FailurePrescription.BLOCK_DVS,
    )
    provenance = CompilationProvenance(
        source_csa_id="CSA-101", source_version="1.0.0-draft",
        source_fingerprint="c5030d3420fc355c014420da36e134d02f72c7efadcbde1369bc5424207026b5",
        compiler_contract_version="1.0.0",
    )
    qualification = CompilationQualification(
        source_status=DocumentStatus.PROPOSED, publication_eligible=False,
        publication_blocking_reasons=("Approbation scientifique absente",),
        execution_eligible=False, execution_blocking_reason="Implémentation métier absente",
    )
    return CompilationArtifact(control=control, provenance=provenance, field_trace=(), omitted_source_sections=(), qualification=qualification)


def _rendered():
    return render_scaffold(build_scaffold_plan(_artifact(), ScaffoldConfiguration()))


# --- Scénarios fonctionnels de base ---------------------------------------

def test_create_only_happy_path_writes_all_files(tmp_path: Path):
    rendered = _rendered()
    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is True
    assert report.rollback_performed is False
    assert manifest is not None
    assert manifest.write_completed is True

    for payload in rendered.payload_files:
        target = tmp_path / payload.relative_path
        assert target.is_file()
        assert target.read_bytes() == payload.content
    for marker in rendered.infrastructure_files:
        target = tmp_path / marker.relative_path
        assert target.is_file()
        assert target.read_bytes() == b""

    states = {r.relative_path: r.state for r in report.records}
    assert all(s == TransactionState.PUBLISHED for s in states.values())

    # Aucun fichier temporaire résiduel après un run réussi.
    all_names = [p.name for p in tmp_path.rglob("*")]
    assert not any(n.endswith(".tmp") for n in all_names)


def test_preexisting_conforming_marker_is_reused_not_rewritten(tmp_path: Path):
    rendered = _rendered()
    marker_path = tmp_path / rendered.infrastructure_files[0].relative_path
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_bytes(b"")
    mtime_before = marker_path.stat().st_mtime_ns

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is True
    record = next(r for r in report.records if r.relative_path == rendered.infrastructure_files[0].relative_path)
    assert record.state == TransactionState.REUSED_VERIFIED
    assert record.owned_by_run is False
    assert marker_path.stat().st_mtime_ns == mtime_before

    infra_entry = next(f for f in manifest.infrastructure_files if f["relative_path"] == rendered.infrastructure_files[0].relative_path)
    assert infra_entry["materialization"] == "REUSED"
    assert infra_entry["ownership"] == "PREEXISTING_SHARED"


def test_create_only_refuses_when_payload_already_exists(tmp_path: Path):
    rendered = _rendered()
    target = tmp_path / rendered.payload_files[0].relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"contenu different")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is False
    assert report.rollback_performed is False
    assert manifest is None
    assert "CREATE_ONLY" in report.refusal_reason
    for other in rendered.infrastructure_files:
        assert not (tmp_path / other.relative_path).exists()


def test_marker_with_non_empty_content_is_refused(tmp_path: Path):
    rendered = _rendered()
    marker_path = tmp_path / rendered.infrastructure_files[0].relative_path
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_bytes(b"import something  # ne devrait jamais etre la\n")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is False
    assert manifest is None
    assert "non-empty" in report.refusal_reason


def test_regenerate_verified_is_idempotent_on_identical_content(tmp_path: Path):
    rendered = _rendered()
    report1, manifest1 = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)
    assert report1.write_completed

    report2, manifest2 = publish_scaffold(rendered, tmp_path, WriteMode.REGENERATE_VERIFIED)
    assert report2.write_completed is True
    assert all(r.state == TransactionState.REUSED_VERIFIED for r in report2.records)
    assert all(r.owned_by_run is False for r in report2.records)


def test_regenerate_verified_refuses_when_content_differs(tmp_path: Path):
    rendered = _rendered()
    target = tmp_path / rendered.payload_files[0].relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"# contenu different du rendu attendu\n")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.REGENERATE_VERIFIED)

    assert report.write_completed is False
    assert manifest is None
    assert "different content" in report.refusal_reason


# --- Défense contre l'échappement de racine (revue de sécurité, pt. 1) ----

def test_relative_path_with_dotdot_is_rejected_by_safe_fs_directly(tmp_path: Path):
    """safe_fs doit se protéger lui-même, indépendamment de la validation
    déjà faite par L2 — un module « safe » ne peut pas dépendre
    uniquement de la discipline de son appelant."""
    root = tmp_path / "root"
    root.mkdir()
    outside_marker = tmp_path / "ESCAPED_MARKER"
    root_fd = safe_fs.open_root_dir_fd(root)
    try:
        with pytest.raises(safe_fs.PathSafetyError):
            safe_fs.stage_and_publish(root_fd, "../ESCAPED_MARKER", b"ESCAPED")
    finally:
        os.close(root_fd)
    assert not outside_marker.exists()


@pytest.mark.parametrize("bad_path", [
    "../escape.py", "a/../../escape.py", "/absolute/path.py", "a//b.py",
    "a/./b.py", "a/../b.py", "", ".", "..", "a\\b.py",
])
def test_all_unsafe_relative_paths_are_rejected(tmp_path: Path, bad_path: str):
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        with pytest.raises(safe_fs.PathSafetyError):
            safe_fs.stage_and_publish(root_fd, bad_path, b"x")
        with pytest.raises(safe_fs.PathSafetyError):
            safe_fs.lstat_leaf(root_fd, bad_path)
    finally:
        os.close(root_fd)


def test_symlink_path_component_is_rejected(tmp_path: Path):
    rendered = _rendered()
    real_target = tmp_path / "elsewhere"
    real_target.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "rocsa_generator").mkdir()
    os.symlink(real_target, tmp_path / "src" / "rocsa_generator" / "generated")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is False
    assert manifest is None
    assert "symlink" in report.refusal_reason.lower() or "unsafe" in report.refusal_reason.lower()
    assert list(real_target.iterdir()) == []


def test_root_itself_as_symlink_is_rejected(tmp_path: Path):
    real_root = tmp_path / "real_root"
    real_root.mkdir()
    fake_root = tmp_path / "fake_root_symlink"
    os.symlink(real_root, fake_root)

    rendered = _rendered()
    with pytest.raises(Exception) as exc_info:
        publish_scaffold(rendered, fake_root, WriteMode.CREATE_ONLY)
    assert "symlink" in str(exc_info.value).lower()


# --- Préflight non-mutant (revue de sécurité, pt. 2) -----------------------

def test_preflight_inspection_never_creates_directories(tmp_path: Path):
    """lstat_leaf sur un chemin dont les répertoires intermédiaires
    n'existent pas doit renvoyer None SANS jamais créer ces répertoires —
    l'inspection est strictement en lecture seule."""
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        result = safe_fs.lstat_leaf(root_fd, "a/b/c/nonexistent.txt")
    finally:
        os.close(root_fd)
    assert result is None
    assert not (tmp_path / "a").exists()


def test_refused_publication_leaves_no_directories_behind(tmp_path: Path):
    """Un refus en phase d'inspection (CREATE_ONLY sur cible déjà
    existante) ne doit laisser aucune arborescence vide créée par erreur
    pendant l'inspection des AUTRES fichiers du lot."""
    rendered = _rendered()
    target = tmp_path / rendered.payload_files[0].relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"bloque le lot entier")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is False
    # Seul le répertoire qu'on a nous-mêmes créé pour poser le fichier
    # bloquant existe ; aucun autre répertoire du plan n'a été créé par
    # inspection des markers/tests.
    test_dir = tmp_path / "tests"
    assert not test_dir.exists()


# --- Ownership au rollback (revue de sécurité, pt. 4) ----------------------

def test_rollback_removes_only_files_created_this_run(tmp_path: Path, monkeypatch):
    rendered = _rendered()
    import rocsa_generator.writer as writer_module

    call_count = {"n": 0}
    original = writer_module.stage_and_publish

    def _flaky_stage_and_publish(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated failure on second write, for rollback testing")
        return original(*args, **kwargs)

    monkeypatch.setattr(writer_module, "stage_and_publish", _flaky_stage_and_publish)

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)

    assert report.write_completed is False
    assert report.rollback_performed is True
    assert manifest is None
    all_targets = [tmp_path / f.relative_path for f in (*rendered.infrastructure_files, *rendered.payload_files)]
    assert not any(t.exists() for t in all_targets)


def test_rollback_refuses_to_remove_file_replaced_by_concurrent_process(tmp_path: Path):
    """Si le fichier publié par ce run est remplacé (autre device/inode)
    avant le rollback, remove_leaf_if_owned doit refuser de le supprimer
    plutôt que de détruire l'objet d'un tiers."""
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        dev, ino, ctime_ns = safe_fs.stage_and_publish(root_fd, "owned.txt", b"contenu original")
        # Simulation d'un remplacement concurrent : suppression puis
        # recréation du même nom (nouvel inode).
        (tmp_path / "owned.txt").unlink()
        (tmp_path / "owned.txt").write_bytes(b"contenu d'un autre processus")

        outcome = safe_fs.remove_leaf_if_owned(root_fd, "owned.txt", dev, ino, ctime_ns)
        assert outcome == "OWNERSHIP_LOST"
        assert (tmp_path / "owned.txt").read_bytes() == b"contenu d'un autre processus"
    finally:
        os.close(root_fd)


def test_rollback_of_matching_ownership_succeeds(tmp_path: Path):
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        dev, ino, ctime_ns = safe_fs.stage_and_publish(root_fd, "owned.txt", b"contenu")
        outcome = safe_fs.remove_leaf_if_owned(root_fd, "owned.txt", dev, ino, ctime_ns)
        assert outcome == "ROLLED_BACK"
        assert not (tmp_path / "owned.txt").exists()
    finally:
        os.close(root_fd)


def test_directory_rollback_removes_only_if_still_empty(tmp_path: Path):
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        created = []
        safe_fs.stage_and_publish(root_fd, "newdir/file.txt", b"x", created)
        assert [d.relative_path for d in created] == ["newdir"]
        # Le répertoire n'est plus vide (contient file.txt) : ne doit pas
        # être supprimé par le rollback de répertoire.
        removed = safe_fs.remove_directory_if_empty_and_owned(root_fd, created[0])
        assert removed == "NOT_EMPTY"
        assert (tmp_path / "newdir").exists()

        (tmp_path / "newdir" / "file.txt").unlink()
        removed = safe_fs.remove_directory_if_empty_and_owned(root_fd, created[0])
        assert removed == "ROLLED_BACK"
        assert not (tmp_path / "newdir").exists()
    finally:
        safe_fs.close_owned_directories(created)
        os.close(root_fd)


def test_failed_stage_keeps_created_directories_in_shared_journal(tmp_path: Path, monkeypatch):
    """Un échec après mkdir ne peut pas faire perdre la propriété des parents."""
    created = []
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    real_write_all = safe_fs._write_all
    try:
        monkeypatch.setattr(safe_fs, "_write_all", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError, match="disk full"):
            safe_fs.stage_and_publish(root_fd, "a/b/file.txt", b"x", created)
        assert [d.relative_path for d in created] == ["a", "a/b"]
        assert not list((tmp_path / "a" / "b").glob("*.tmp"))
        for owned in reversed(created):
            assert safe_fs.remove_directory_if_empty_and_owned(root_fd, owned) == "ROLLED_BACK"
        assert not (tmp_path / "a").exists()
    finally:
        safe_fs.close_owned_directories(created)
        monkeypatch.setattr(safe_fs, "_write_all", real_write_all)
        os.close(root_fd)


def test_rollback_errors_are_reported_and_do_not_escape(tmp_path: Path, monkeypatch):
    rendered = _rendered()
    import rocsa_generator.writer as writer_module

    original_stage = writer_module.stage_and_publish
    calls = {"n": 0}

    def fail_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("publication failure")
        return original_stage(*args, **kwargs)

    monkeypatch.setattr(writer_module, "stage_and_publish", fail_second)
    monkeypatch.setattr(writer_module, "remove_leaf_if_owned", lambda *_: (_ for _ in ()).throw(OSError("rollback failure")))

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)
    assert manifest is None
    assert report.write_completed is False
    assert report.rollback_performed is True
    failed = [r for r in report.records if r.state == TransactionState.ROLLBACK_FAILED]
    assert failed and "IO_ERROR" in (failed[0].detail or "")


def test_created_directory_replaced_before_cleanup_is_preserved(tmp_path: Path):
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    created = []
    try:
        safe_fs.stage_and_publish(root_fd, "newdir/file.txt", b"x", created)
        (tmp_path / "newdir" / "file.txt").unlink()
        (tmp_path / "newdir").rmdir()
        (tmp_path / "newdir").mkdir()
        assert safe_fs.remove_directory_if_empty_and_owned(root_fd, created[0]) == "OWNERSHIP_LOST"
        assert (tmp_path / "newdir").is_dir()
    finally:
        safe_fs.close_owned_directories(created)
        os.close(root_fd)


# --- Écriture partielle et fichiers spéciaux (revue de sécurité, pt. 5-6) --

def test_write_all_loops_until_content_fully_written(tmp_path: Path, monkeypatch):
    """Simule un os.write() qui n'écrit qu'une partie du contenu à
    chaque appel (comportement autorisé par POSIX) : le contenu final
    doit malgré tout être intégral."""
    import rocsa_generator.safe_fs as safe_fs_module

    real_write = os.write

    def _short_write(fd, data):
        return real_write(fd, data[:1]) if len(data) > 1 else real_write(fd, data)

    monkeypatch.setattr(safe_fs_module.os, "write", _short_write)

    root_fd = safe_fs_module.open_root_dir_fd(tmp_path)
    try:
        content = b"contenu de plusieurs octets pour forcer plusieurs appels write"
        safe_fs_module.stage_and_publish(root_fd, "chunked.txt", content)
    finally:
        os.close(root_fd)
    assert (tmp_path / "chunked.txt").read_bytes() == content


def test_read_leaf_rejects_fifo_special_file(tmp_path: Path):
    """Un FIFO créé à la place d'un fichier régulier attendu doit être
    refusé, pas lu (lire un FIFO sans écrivain de l'autre côté bloque
    indéfiniment)."""
    fifo_path = tmp_path / "special.txt"
    os.mkfifo(fifo_path)
    assert stat_module.S_ISFIFO(os.lstat(fifo_path).st_mode)

    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        with pytest.raises(safe_fs.PathSafetyError):
            safe_fs.read_leaf_nofollow(root_fd, "special.txt")
    finally:
        os.close(root_fd)


def test_concurrent_target_appearance_is_rejected_atomically(tmp_path: Path):
    """Le fichier apparaît entre la fin de l'inspection et la publication
    (simulation) : os.link doit échouer atomiquement, sans fenêtre."""
    root_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        (tmp_path / "race.txt").write_bytes(b"deja la")
        with pytest.raises(safe_fs.PathSafetyError):
            safe_fs.stage_and_publish(root_fd, "race.txt", b"nouveau contenu")
        # Le contenu original n'a pas été écrasé.
        assert (tmp_path / "race.txt").read_bytes() == b"deja la"
        # Aucun résidu temporaire.
        leftover_tmp = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftover_tmp == []
    finally:
        os.close(root_fd)


# --- Verrou coopératif (D-SCAFFOLD-26) -------------------------------------

def test_lock_is_released_even_when_inspection_refuses_before_any_write(tmp_path: Path):
    """Un refus dès l'inspection (avant toute écriture) ne doit jamais
    laisser le verrou orphelin — sinon un run ultérieur resterait bloqué
    indéfiniment sur un simple refus, sans aucune écriture en cours."""
    rendered = _rendered()
    target = tmp_path / rendered.payload_files[0].relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"bloque des l'inspection")

    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)
    assert report.write_completed is False  # refus confirmé, comme attendu

    # Le verrou doit être libéré : une acquisition non bloquante immédiate
    # doit réussir. S'il était resté tenu, ce flock lèverait BlockingIOError.
    probe_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe_fd, fcntl.LOCK_UN)
    except BlockingIOError:
        pytest.fail("le verrou est resté tenu après un refus en phase d'inspection")
    finally:
        os.close(probe_fd)


def test_lock_is_released_after_a_successful_run(tmp_path: Path):
    """Même contrôle après un run réussi (pas seulement après un refus) :
    le verrou ne doit jamais survivre à la fin de publish_scaffold()."""
    rendered = _rendered()
    report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)
    assert report.write_completed is True

    probe_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe_fd, fcntl.LOCK_UN)
    except BlockingIOError:
        pytest.fail("le verrou est resté tenu après un run réussi")
    finally:
        os.close(probe_fd)


def test_second_lock_acquisition_is_blocked_while_first_is_held(tmp_path: Path):
    """Preuve directe que le verrou sérialise réellement, pas seulement une
    déclaration d'intention (D-SCAFFOLD-26) : tant qu'un premier détenteur
    garde le verrou, une seconde tentative non bloquante doit échouer
    immédiatement (BlockingIOError), pas réussir silencieusement."""
    holder_fd = safe_fs.open_root_dir_fd(tmp_path)
    safe_fs.lock_root_exclusive(holder_fd)
    try:
        second_fd = safe_fs.open_root_dir_fd(tmp_path)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(second_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(second_fd)
    finally:
        safe_fs.unlock_root(holder_fd)
        os.close(holder_fd)

    # Une fois libéré par le premier détenteur, la seconde acquisition
    # doit désormais réussir immédiatement.
    third_fd = safe_fs.open_root_dir_fd(tmp_path)
    try:
        fcntl.flock(third_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(third_fd, fcntl.LOCK_UN)
    finally:
        os.close(third_fd)


def test_publish_scaffold_blocks_a_concurrent_second_call_via_the_lock(tmp_path: Path):
    """Bout en bout : pendant qu'un premier appel détient le verrou (simulé
    en l'acquirant manuellement avant d'invoquer publish_scaffold dans un
    thread), un second appel concurrent ne peut pas procéder en parallèle
    — il doit attendre la libération, pas s'exécuter simultanément."""
    import threading
    import time

    rendered = _rendered()
    holder_fd = safe_fs.open_root_dir_fd(tmp_path)
    safe_fs.lock_root_exclusive(holder_fd)

    result: dict[str, object] = {}

    def _run_publish():
        report, manifest = publish_scaffold(rendered, tmp_path, WriteMode.CREATE_ONLY)
        result["report"] = report
        result["manifest"] = manifest

    thread = threading.Thread(target=_run_publish)
    thread.start()
    # Le thread doit être bloqué sur l'acquisition du verrou tant qu'on ne
    # l'a pas libéré nous-mêmes : il ne doit pas avoir terminé prématurément.
    thread.join(timeout=0.3)
    assert thread.is_alive(), "publish_scaffold n'a pas attendu le verrou detenu par le test"
    assert "report" not in result

    safe_fs.unlock_root(holder_fd)
    os.close(holder_fd)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result["report"].write_completed is True
