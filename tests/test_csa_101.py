"""Tests de CSA-101 (DECISION-CSA-101-EXEC-v1.md), révisés après revue
du 2026-08-12 : vecteurs SHA-256 normatifs (pas d'oracle circulaire),
types d'entrée incorrects, symlinks, mutation concurrente, streaming
réel (pas d'accumulation mémoire)."""

from __future__ import annotations

import hashlib
import os
import stat as stat_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from rocsa_generator.csa_controls.csa_101 import IntegrityCheckResult, verify_integrity
from rocsa_generator.models.fn_csa import ResultState

# Vecteurs SHA-256 normatifs (NIST/FIPS 180-4), indépendants de
# l'implémentation testée — corrige l'oracle circulaire de la revue
# précédente, où les tests utilisaient hashlib.sha256() pour générer
# la valeur attendue ET l'implémentation utilisait hashlib.sha256()
# pour la calculer : ça prouvait la cohérence interne, pas la
# conformité à l'algorithme reel.
SHA256_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SHA256_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_passed_with_normative_vector_empty_string(tmp_path: Path):
    obj = tmp_path / "empty.bin"
    obj.write_bytes(b"")
    result = verify_integrity(obj, SHA256_EMPTY, "SHA-256")
    assert result.state == ResultState.PASSED
    assert result.computed_hash == SHA256_EMPTY
    assert result.bytes_read == 0


def test_passed_with_normative_vector_abc(tmp_path: Path):
    obj = tmp_path / "abc.bin"
    obj.write_bytes(b"abc")
    result = verify_integrity(obj, SHA256_ABC, "SHA-256")
    assert result.state == ResultState.PASSED
    assert result.computed_hash == SHA256_ABC
    assert result.bytes_read == 3


def test_failed_when_single_byte_altered(tmp_path: Path):
    """Une seule alteration d'octet doit produire FAILED, pas une
    fausse conformite."""
    obj = tmp_path / "altered.bin"
    obj.write_bytes(b"abd")  # dernier octet different de "abc"
    result = verify_integrity(obj, SHA256_ABC, "SHA-256")
    assert result.state == ResultState.FAILED
    assert result.computed_hash != SHA256_ABC


def test_error_when_object_does_not_exist(tmp_path: Path):
    missing = tmp_path / "nexiste_pas.bin"
    result = verify_integrity(missing, "a" * 64, "SHA-256")
    assert result.state == ResultState.ERROR
    assert result.computed_hash is None


def test_error_when_object_is_a_directory(tmp_path: Path):
    directory = tmp_path / "un_repertoire"
    directory.mkdir()
    result = verify_integrity(directory, "a" * 64, "SHA-256")
    assert result.state == ResultState.ERROR


def test_error_when_object_is_a_fifo_not_blocking(tmp_path: Path):
    """Regression liee au bug FIFO trouve dans safe_fs.py (L3). Ce test
    doit se terminer rapidement, pas rester suspendu."""
    fifo_path = tmp_path / "special.bin"
    os.mkfifo(fifo_path)
    assert stat_module.S_ISFIFO(os.lstat(fifo_path).st_mode)
    result = verify_integrity(fifo_path, "a" * 64, "SHA-256")
    assert result.state == ResultState.ERROR


def test_error_when_object_is_a_symlink(tmp_path: Path):
    """Politique tranchee apres revue : symlinks refuses par defaut
    (O_NOFOLLOW), coherent avec la doctrine de confinement de L3."""
    real_file = tmp_path / "real.bin"
    real_file.write_bytes(b"abc")
    symlink = tmp_path / "link.bin"
    symlink.symlink_to(real_file)

    result = verify_integrity(symlink, SHA256_ABC, "SHA-256")
    assert result.state == ResultState.ERROR


@pytest.mark.parametrize("bad_hash", ["", "trop_court", "g" * 64, "A" * 64 + "extra"])
def test_error_when_reference_hash_is_malformed(tmp_path: Path, bad_hash):
    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")
    result = verify_integrity(obj, bad_hash, "SHA-256")
    assert result.state == ResultState.ERROR


@pytest.mark.parametrize("bad_hash", [
    "a" * 64 + "\n",
    "a" * 64 + "\r\n",
    " " + "a" * 64,
    "a" * 64 + " ",
])
def test_error_when_reference_hash_has_extra_whitespace_or_newline(tmp_path: Path, bad_hash):
    """Regression directe : re.match(pattern + '$') acceptait un saut de
    ligne final (particularite de re en Python), classant a tort une
    entree malformee en FAILED plutot qu'ERROR. Confirme par
    reproduction lors de la revue du 2026-08-13, corrige par
    re.fullmatch()."""
    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")
    result = verify_integrity(obj, bad_hash, "SHA-256")
    assert result.state == ResultState.ERROR


def test_reference_hash_uppercase_is_still_accepted(tmp_path: Path):
    """Decision confirmee explicitement : la casse de reference_hash
    est normalisee avant comparaison (equivalence de representation,
    pas une deduction d'algorithme)."""
    obj = tmp_path / "object.bin"
    obj.write_bytes(b"abc")
    result = verify_integrity(obj, SHA256_ABC.upper(), "SHA-256")
    assert result.state == ResultState.PASSED


@pytest.mark.parametrize("bad_algorithm", ["MD5", "SHA-1", "sha-256", "SHA256", ""])
def test_error_when_algorithm_is_not_supported_by_v1_profile(tmp_path: Path, bad_algorithm):
    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")
    result = verify_integrity(obj, "a" * 64, bad_algorithm)
    assert result.state == ResultState.ERROR


# --- Robustesse aux types d'entree incorrects (revue 2026-08-12, pt.7) -----

def test_error_when_reference_hash_is_wrong_type_not_str(tmp_path: Path):
    """Avant correctif : AttributeError brut ('int' object has no
    attribute 'lower'), confirme par reproduction. Apres : ERROR propre."""
    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")
    result = verify_integrity(obj, 123, "SHA-256")  # type: ignore[arg-type]
    assert result.state == ResultState.ERROR


def test_error_when_scientific_object_is_none():
    """Avant correctif : TypeError brut non capture par 'except OSError',
    confirme par reproduction. Apres : ERROR propre."""
    result = verify_integrity(None, "a" * 64, "SHA-256")  # type: ignore[arg-type]
    assert result.state == ResultState.ERROR


def test_error_when_declared_algorithm_is_wrong_type():
    result = verify_integrity(Path("/tmp/x"), "a" * 64, 42)  # type: ignore[arg-type]
    assert result.state == ResultState.ERROR


# --- Mutation concurrente (revue 2026-08-12, pt.9) --------------------------

def test_error_when_object_mutates_during_verification(tmp_path: Path):
    """Simule une mutation concurrente : le fichier change entre la
    premiere et la deuxieme mesure d'identite (fstat(fd) avant/apres
    lecture). Le module n'a pas de point d'injection direct pour une
    vraie course inter-processus, donc ce test verifie le mecanisme via
    une mutation declenchee entre les deux appels de _fd_identity."""
    import rocsa_generator.csa_controls.csa_101 as module

    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu original")

    original_fd_identity = module._fd_identity
    call_count = {"n": 0}

    def _flaky_identity(fd):
        call_count["n"] += 1
        if call_count["n"] == 2:
            # Simule une mutation detectee juste avant la comparaison
            # finale (apres la lecture du contenu).
            obj.write_bytes(b"contenu modifie pendant verification, plus long")
        return original_fd_identity(fd)

    module._fd_identity = _flaky_identity
    try:
        result = verify_integrity(obj, "a" * 64, "SHA-256")
        assert result.state == ResultState.ERROR
    finally:
        module._fd_identity = original_fd_identity


def test_never_modifies_the_scientific_object(tmp_path: Path):
    content = b"contenu original"
    obj = tmp_path / "object.bin"
    obj.write_bytes(content)
    mtime_before = obj.stat().st_mtime_ns

    verify_integrity(obj, hashlib.sha256(content).hexdigest(), "SHA-256")
    verify_integrity(obj, "a" * 64, "SHA-256")

    assert obj.read_bytes() == content
    assert obj.stat().st_mtime_ns == mtime_before


# --- Streaming reel, pas d'accumulation memoire (revue 2026-08-12, pt.3) ---

def test_hashing_is_streamed_not_accumulated_in_memory(tmp_path: Path, monkeypatch):
    """Verifie que digest.update() est appele par bloc (streaming reel)
    plutot que hashlib.sha256(contenu_complet) en un seul appel apres
    accumulation - regression directe du bug confirme lors de la revue."""
    import rocsa_generator.csa_controls.csa_101 as module

    content = os.urandom(200_000)
    obj = tmp_path / "large.bin"
    obj.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()

    update_calls: list[int] = []
    real_sha256 = hashlib.sha256

    class _TrackedDigest:
        def __init__(self):
            self._real = real_sha256()

        def update(self, chunk: bytes) -> None:
            update_calls.append(len(chunk))
            self._real.update(chunk)

        def hexdigest(self) -> str:
            return self._real.hexdigest()

    monkeypatch.setattr(module.hashlib, "sha256", _TrackedDigest)

    result = verify_integrity(obj, expected, "SHA-256")

    assert result.state == ResultState.PASSED
    # Plusieurs appels update() avec des blocs <= 64 Kio chacun, jamais
    # un unique appel avec la totalite du contenu (200 000 octets d'un
    # coup indiquerait une accumulation memoire, pas un vrai flux).
    assert len(update_calls) > 1
    assert all(size <= 65536 for size in update_calls)
    assert sum(update_calls) == len(content)


def test_large_file_hash_is_still_correct(tmp_path: Path):
    content = os.urandom(200_000)
    obj = tmp_path / "large.bin"
    obj.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    result = verify_integrity(obj, expected, "SHA-256")
    assert result.state == ResultState.PASSED
    assert result.bytes_read == len(content)


# --- Erreurs systeme capturees a chaque etape (revue 2026-08-13, pt.2) -----

def test_error_when_read_raises_oserror(tmp_path: Path, monkeypatch):
    """Avant correctif : seul os.open() etait protege. Une erreur sur
    os.read() (ex. erreur disque) remontait brute. Confirme par lecture
    de code, corrige par capture explicite dans _hash_file_streaming."""
    import rocsa_generator.csa_controls.csa_101 as module

    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")

    real_read = os.read
    call_count = {"n": 0}

    def _flaky_read(fd, size):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("simulated disk read error")
        return real_read(fd, size)

    monkeypatch.setattr(module.os, "read", _flaky_read)
    result = verify_integrity(obj, "a" * 64, "SHA-256")
    assert result.state == ResultState.ERROR


def test_error_when_fstat_raises_oserror_after_open(tmp_path: Path, monkeypatch):
    import rocsa_generator.csa_controls.csa_101 as module

    obj = tmp_path / "object.bin"
    obj.write_bytes(b"contenu")

    real_fstat = os.fstat
    call_count = {"n": 0}

    def _flaky_fstat(fd):
        call_count["n"] += 1
        if call_count["n"] == 2:  # premier appel: verification regulier; deuxieme: identite
            raise OSError("simulated fstat error")
        return real_fstat(fd)

    monkeypatch.setattr(module.os, "fstat", _flaky_fstat)
    result = verify_integrity(obj, "a" * 64, "SHA-256")
    assert result.state == ResultState.ERROR


# --- Coherence du modele de resultat (revue 2026-08-13, pt.4) --------------

def test_result_model_rejects_passed_without_computed_hash():
    with pytest.raises(ValidationError):
        IntegrityCheckResult(state=ResultState.PASSED, detail="x", computed_hash=None, bytes_read=0)


def test_result_model_rejects_error_with_computed_hash():
    with pytest.raises(ValidationError):
        IntegrityCheckResult(state=ResultState.ERROR, detail="x", computed_hash="a" * 64)


def test_result_model_rejects_not_applicable_entirely():
    with pytest.raises(ValidationError):
        IntegrityCheckResult(state=ResultState.NOT_APPLICABLE, detail="x", computed_hash=None)


def test_result_model_accepts_failed_with_computed_hash():
    result = IntegrityCheckResult(state=ResultState.FAILED, detail="x", computed_hash="a" * 64)
    assert result.state == ResultState.FAILED


# --- Modele de resultat -----------------------------------------------------

def test_result_model_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        IntegrityCheckResult(state=ResultState.PASSED, detail="x", computed_hash="a" * 64, unknown_field=True)


def test_result_model_requires_valid_computed_hash_format_when_present():
    with pytest.raises(ValidationError):
        IntegrityCheckResult(state=ResultState.PASSED, detail="x", computed_hash="pas_une_empreinte_valide")
