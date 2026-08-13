"""CSA-101 — Vérification de l'intégrité cryptographique (contrat
d'exécution v1, voir DECISION-CSA-101-EXEC-v1.md).

Révisé après revue du 2026-08-12 (v2) puis du 2026-08-13 (v3, voir
DECISION-CSA-101-EXEC-v1.md, addendum 2) : `re.fullmatch` au lieu de
`re.match` (rejette une entrée avec saut de ligne final que `$` seul
acceptait), toutes les erreurs système capturées explicitement (pas
seulement `os.open`), identité de fichier vérifiée via `fstat(fd)`
avant/après lecture (pas `path.stat()`, qui rouvre le chemin plutôt que
de vérifier l'objet réellement ouvert), validateur de cohérence sur
`IntegrityCheckResult` (un état donné impose une forme de résultat
précise, pas seulement en pratique mais en contrat).

Source authentique, écrite et testée à la main — jamais du texte
templaté dans scaffold_renderer.py (D-CSA101-EXEC-01). Autonome et
indépendante du pipeline de scaffold L2/L3.

Lecture seule stricte (D-CSA101-EXEC-04) : ne modifie jamais l'objet
contrôlé.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from rocsa_generator.models.fn_csa import ResultState

# Re-déclaration locale et DÉLIBÉRÉE du motif SHA-256 hexadécimal —
# PAS un import de compilation_artifact.py::Sha256Hex. Un import
# créerait une dépendance de ce module vers le pipeline de compilation,
# ce que D-CSA101-EXEC-01 interdit explicitement (indépendance du
# noyau métier). Même valeur que Sha256Hex par coïncidence normative
# (SHA-256 fait 64 caractères hexadécimaux, un fait mathématique, pas
# un choix arbitraire) — pas une "réutilisation", une redéclaration
# assumée pour préserver l'indépendance.
_SHA256_HEX_PATTERN = re.compile(r"[0-9a-fA-F]{64}")

SUPPORTED_ALGORITHM = "SHA-256"
_READ_CHUNK_SIZE = 65536


class _VerifyIntegrityInput(BaseModel):
    """Validation d'entrée stricte : toute entrée de type incorrect
    (int au lieu de str, None au lieu de Path, etc.) est rejetée ici
    avec ValidationError, convertie en ERROR par l'appelant."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, arbitrary_types_allowed=True)

    scientific_object: Path
    reference_hash: Annotated[str, Field(min_length=1)]
    declared_algorithm: str


class IntegrityCheckResult(BaseModel):
    """Résultat technique minimal du noyau B1 (D-CSA101-EXEC-01).
    Réutilise uniquement le vocabulaire canonique d'état (ResultState)
    — la construction du résultat FN-CSA complet (prescription d'échec,
    preuves d'exécution) relève de l'adaptateur statique L4-B2, pas de
    ce noyau. Le module importe déjà ResultState de fn_csa.py : le
    noyau B1 n'est pas totalement indépendant du vocabulaire FN-CSA, il
    n'est indépendant que du pipeline de compilation (CompilationArtifact,
    ScaffoldPlan, etc.).

    Validateur de cohérence : PASSED/FAILED exigent computed_hash
    renseigné ; ERROR exige computed_hash=None. NOT_APPLICABLE n'est pas
    un état valide pour ce résultat technique (D-CSA101-EXEC-03 : jamais
    produit par CSA-101 v1)."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state: ResultState
    detail: Annotated[str, Field(min_length=1)]
    computed_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    bytes_read: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def _state_and_hash_are_consistent(self) -> "IntegrityCheckResult":
        if self.state is ResultState.NOT_APPLICABLE:
            raise ValueError("NOT_APPLICABLE n'est jamais un etat valide pour CSA-101 v1 (D-CSA101-EXEC-03)")
        if self.state in (ResultState.PASSED, ResultState.FAILED) and self.computed_hash is None:
            raise ValueError(f"computed_hash requis pour l'etat {self.state}")
        if self.state is ResultState.ERROR and self.computed_hash is not None:
            raise ValueError("computed_hash doit etre None pour l'etat ERROR")
        return self


def _error(detail: str, bytes_read: int = 0) -> IntegrityCheckResult:
    return IntegrityCheckResult(state=ResultState.ERROR, detail=detail, computed_hash=None, bytes_read=bytes_read)


def _close_quietly(fd: int) -> None:
    """Ferme un descripteur sans jamais laisser remonter d'OSError —
    utilisée systématiquement, y compris dans les chemins d'erreur où
    une fermeture qui échouerait ne doit pas masquer ni contredire le
    diagnostic déjà établi (revue du 2026-08-13, correction mineure)."""
    try:
        os.close(fd)
    except OSError:
        pass


def _open_regular_file_no_symlink(path: Path) -> int | None:
    """Ouvre un fichier régulier, en refusant explicitement de suivre
    un symlink terminal. Retourne None si absent, symlink, non un
    fichier régulier, ou toute erreur système à l'ouverture.

    Portabilité (revue du 2026-08-13, pt.7) : `os.O_NOFOLLOW` n'est pas
    garanti sur toutes les plateformes. Si absent, un `lstat()` manuel
    détecte le symlink avant l'ouverture (fenêtre TOCTOU résiduelle
    documentée, acceptée pour une vérification en lecture seule — pas
    comparable en gravité à la fenêtre d'écriture que L3 devait fermer).
    Jamais de repli qui accepterait silencieusement un symlink faute de
    `O_NOFOLLOW` : sur une plateforme sans ce drapeau, on referme
    seulement pour les symlinks détectés par `lstat()`, pas pour tous
    les fichiers.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow == 0:
        try:
            if stat.S_ISLNK(os.lstat(path).st_mode):
                return None
        except OSError:
            return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | nofollow)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
    except OSError:
        _close_quietly(fd)
        return None
    if not stat.S_ISREG(st.st_mode):
        _close_quietly(fd)
        return None
    return fd


def _fd_identity(fd: int) -> tuple[int, int, int, int, int] | None:
    """(device, inode, taille, mtime_ns, ctime_ns) du descripteur
    ouvert — vérifie l'objet réellement ouvert via fstat(fd), pas le
    chemin (path.stat() rouvrirait potentiellement un objet différent
    entre-temps si le nom avait été remplacé, cf. revue du
    2026-08-13, pt.3)."""
    try:
        st = os.fstat(fd)
    except OSError:
        return None
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _hash_file_streaming(path: Path) -> tuple[str, int] | None:
    """Calcule l'empreinte SHA-256 réellement en flux (digest.update()
    par bloc, jamais d'accumulation complète en mémoire). Détecte une
    mutation concurrente en comparant l'identité du descripteur ouvert
    juste après l'ouverture et juste avant la fermeture. Toute erreur
    système à n'importe quelle étape (fstat, get_blocking, set_blocking,
    read, close) est capturée et traduite en None -> ERROR, jamais
    laissée remonter brute (revue du 2026-08-13, pt.2 : toutes les
    erreurs système capturées, pas seulement celle d'ouverture)."""
    fd = _open_regular_file_no_symlink(path)
    if fd is None:
        return None
    try:
        identity_before = _fd_identity(fd)
        if identity_before is None:
            return None

        try:
            flags = os.get_blocking(fd)
            if not flags:
                os.set_blocking(fd, True)
        except OSError:
            return None

        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                chunk = os.read(fd, _READ_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
        except OSError:
            return None

        identity_after = _fd_identity(fd)
        if identity_after is None or identity_after != identity_before:
            return None

        return digest.hexdigest(), total
    finally:
        _close_quietly(fd)


def verify_integrity(
    scientific_object: Path,
    reference_hash: str,
    declared_algorithm: str,
) -> IntegrityCheckResult:
    """Vérifie que `scientific_object` correspond à `reference_hash`
    selon `declared_algorithm` (profil v1 : SHA-256 uniquement).

    Ne lève jamais d'exception pour un cas prévu — toute situation
    anormale (objet inaccessible, empreinte mal formée, algorithme non
    supporté, type d'entrée incorrect, symlink, mutation concurrente,
    erreur système à n'importe quelle étape de la lecture) produit un
    ResultState.ERROR explicite.
    """
    try:
        validated = _VerifyIntegrityInput(
            scientific_object=scientific_object,
            reference_hash=reference_hash,
            declared_algorithm=declared_algorithm,
        )
    except ValidationError as exc:
        return _error(f"entree invalide (type ou format incorrect): {exc}")

    # fullmatch, pas match : match+$ accepte un saut de ligne final
    # (particularite de re en Python), fullmatch ne l'accepte jamais -
    # confirme par reproduction lors de la revue du 2026-08-13.
    if not _SHA256_HEX_PATTERN.fullmatch(validated.reference_hash):
        return _error(f"reference_hash absent ou mal forme (attendu: exactement 64 caracteres hexadecimaux): {validated.reference_hash!r}")

    if validated.declared_algorithm != SUPPORTED_ALGORITHM:
        return _error(f"algorithme non supporte par le profil v1 (seul {SUPPORTED_ALGORITHM!r} est accepte): {validated.declared_algorithm!r}")

    outcome = _hash_file_streaming(validated.scientific_object)
    if outcome is None:
        return _error(
            f"scientific_object inaccessible, symlink, non un fichier regulier, modifie pendant la verification, ou erreur systeme: {validated.scientific_object}"
        )
    computed, bytes_read = outcome
    expected = validated.reference_hash.lower()

    if computed == expected:
        return IntegrityCheckResult(state=ResultState.PASSED, detail="empreinte SHA-256 conforme a reference_hash", computed_hash=computed, bytes_read=bytes_read)
    return IntegrityCheckResult(
        state=ResultState.FAILED,
        detail=f"empreinte SHA-256 non conforme: calcule={computed} attendu={expected}",
        computed_hash=computed,
        bytes_read=bytes_read,
    )
