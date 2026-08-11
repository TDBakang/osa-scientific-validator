"""Primitives d'accès disque sûres (D-SCAFFOLD-25, révisées après revue
de sécurité du 2026-08-11 — voir DECISION-2.3-D-L3.md, addendum).

Défense en profondeur : ce module valide lui-même chaque chemin reçu
(rejet de `..`, chemins absolus, composants vides, octets nuls) au lieu
de faire confiance à l'appelant (L2). Un module nommé « safe » ne peut
pas dépendre uniquement de la discipline de qui l'invoque.

Deux marches distinctes dans l'arborescence, jamais confondues :
- `_walk_parent_inspect()` : lecture seule, ne crée jamais de répertoire.
  Utilisée par `lstat_leaf`/`read_leaf_nofollow` (phase d'inspection).
- `_walk_parent_ensure()` : peut créer des répertoires manquants.
  Utilisée uniquement par `stage_and_publish` (phase d'écriture réelle).

Publication atomique sans fenêtre TOCTOU : `stage_and_publish` écrit dans
un fichier temporaire puis le publie via `os.link()` (linkat) — succès ou
échec `FileExistsError` en un seul appel système, sans lstat préalable
séparé de l'opération de publication elle-même.
"""

from __future__ import annotations

import errno
import fcntl
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path


class PathSafetyError(RuntimeError):
    """Levée pour tout chemin dangereux, tout composant symlink/non-
    répertoire, ou tout état disque incompatible avec le mode d'écriture
    demandé (D-SCAFFOLD-25, SCAFFOLD-15, SCAFFOLD-16)."""


class OwnershipLostError(RuntimeError):
    """Levée au rollback quand la cible à supprimer ne correspond plus à
    l'objet (device, inode) publié par ce run — jamais supprimée dans ce
    cas, pour ne jamais détruire l'objet d'un processus concurrent."""


@dataclass(frozen=True, slots=True)
class OwnedDirectory:
    relative_path: str
    device: int
    inode: int
    fd: int


def lock_root_exclusive(root_fd: int) -> None:
    """Sérialise les writers ROCSA coopératifs sans créer de lockfile.

    La garantie ne couvre volontairement pas un processus externe qui ignore
    ce verrou consultatif. Cette limite est documentée dans la décision L3.
    """
    fcntl.flock(root_fd, fcntl.LOCK_EX)


def unlock_root(root_fd: int) -> None:
    fcntl.flock(root_fd, fcntl.LOCK_UN)


def close_owned_directories(owned_directories: list[OwnedDirectory]) -> None:
    for owned in owned_directories:
        try:
            os.close(owned.fd)
        except OSError:
            pass


def _validate_relative_path(relative_path: str) -> None:
    """Validation défensive indépendante de tout appelant. Rejette : chemin
    vide, chemin absolu, octet nul, antislash, lettre de lecteur Windows,
    et tout composant vide/`.`/`..`."""
    if not relative_path or "\x00" in relative_path or relative_path.startswith("/"):
        raise PathSafetyError(f"unsafe relative path: {relative_path!r}")
    if "\\" in relative_path:
        raise PathSafetyError(f"unsafe relative path (backslash): {relative_path!r}")
    if len(relative_path) >= 2 and relative_path[1] == ":":
        raise PathSafetyError(f"unsafe relative path (drive letter): {relative_path!r}")
    parts = relative_path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PathSafetyError(f"unsafe relative path component (empty, '.', or '..'): {relative_path!r}")


def open_root_dir_fd(root: Path) -> int:
    """Ouvre la racine du projet, en refusant qu'elle soit elle-même un
    symlink. Le descripteur retourné doit être fermé par l'appelant."""
    try:
        return os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PathSafetyError(f"project root is a symlink, refusing: {root}") from exc
        raise


def _open_existing_dir_nofollow(name: str, dir_fd: int) -> int:
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)


def _walk_parent_inspect(root_fd: int, relative_path: str) -> tuple[int, str, bool] | None:
    """Marche jusqu'au parent de `relative_path`, EN LECTURE SEULE : ne
    crée jamais de répertoire. Si un composant intermédiaire est absent,
    la cible est nécessairement absente aussi — retourne None sans
    aucune écriture sur disque, jamais une exception dans ce cas précis.

    Retourne (fd_parent, nom_de_base, doit_etre_ferme) sinon."""
    parts = relative_path.split("/")
    *dirs, basename = parts
    current_fd = root_fd
    owns_current = False
    for d in dirs:
        try:
            next_fd = _open_existing_dir_nofollow(d, current_fd)
        except FileNotFoundError:
            if owns_current:
                os.close(current_fd)
            return None
        except OSError as exc:
            if owns_current:
                os.close(current_fd)
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise PathSafetyError(f"unsafe path component (symlink or non-directory): {d!r}") from exc
            raise
        if owns_current:
            os.close(current_fd)
        current_fd = next_fd
        owns_current = True
    return current_fd, basename, owns_current


def _step_into_directory_ensure(
    name: str, parent_fd: int, created: list[OwnedDirectory], path_so_far: str
) -> int:
    """Ouvre ou crée le sous-répertoire `name` sous `parent_fd`. N'est
    appelée que pendant la transaction d'écriture réelle (jamais pendant
    l'inspection). Ajoute à `created` le chemin relatif de tout
    répertoire réellement créé par cet appel (pour rollback ultérieur)."""
    try:
        return _open_existing_dir_nofollow(name, parent_fd)
    except FileNotFoundError:
        pass
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise PathSafetyError(f"unsafe path component (symlink or non-directory): {name!r}") from exc
        raise
    try:
        os.mkdir(name, mode=0o755, dir_fd=parent_fd)
    except FileExistsError:
        # Course bénigne entre writers non coopératifs : ouvrir et valider
        # l'objet existant, sans jamais en revendiquer la propriété.
        return _open_existing_dir_nofollow(name, parent_fd)
    child_fd = _open_existing_dir_nofollow(name, parent_fd)
    st = os.fstat(child_fd)
    # Garder un fd ouvert empêche la réutilisation de l'inode avant la fin
    # de la transaction et fournit une identité stable malgré les changements
    # légitimes de ctime lorsque des enfants sont ajoutés/supprimés.
    created.append(OwnedDirectory(path_so_far, st.st_dev, st.st_ino, os.dup(child_fd)))
    return child_fd


def _walk_parent_ensure(
    root_fd: int, relative_path: str, created: list[OwnedDirectory]
) -> tuple[int, str, bool]:
    """Comme `_walk_parent_inspect`, mais crée les répertoires manquants.
    Réservée à la phase d'écriture réelle (`stage_and_publish`). Retourne
    en plus la liste des chemins relatifs de répertoires créés par cet
    appel, dans l'ordre de création — pour rollback si le run échoue."""
    parts = relative_path.split("/")
    *dirs, basename = parts
    current_fd = root_fd
    owns_current = False
    path_so_far = ""
    for d in dirs:
        path_so_far = f"{path_so_far}/{d}" if path_so_far else d
        next_fd = _step_into_directory_ensure(d, current_fd, created, path_so_far)
        if owns_current:
            os.close(current_fd)
        current_fd = next_fd
        owns_current = True
    return current_fd, basename, owns_current


def lstat_leaf(root_fd: int, relative_path: str) -> os.stat_result | None:
    """Renvoie le lstat de la cible sans suivre de symlink, ou None si
    absente (y compris si un composant intermédiaire est absent). Lecture
    seule : ne crée jamais de répertoire (D-SCAFFOLD-25, addendum)."""
    _validate_relative_path(relative_path)
    walked = _walk_parent_inspect(root_fd, relative_path)
    if walked is None:
        return None
    parent_fd, basename, owns = walked
    try:
        try:
            return os.lstat(basename, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
    finally:
        if owns:
            os.close(parent_fd)


def read_leaf_nofollow(root_fd: int, relative_path: str) -> bytes | None:
    """Lit le contenu de la cible sans jamais suivre un symlink terminal.
    Renvoie None si absente. Ouvre avec `O_NONBLOCK` pour ne jamais
    bloquer à l'ouverture même d'un FIFO sans écrivain (une simple
    vérification `fstat` après un `open()` bloquant serait trop tardive
    — le blocage se produit avant qu'on puisse vérifier quoi que ce
    soit). Après ouverture, vérifie via `fstat` que l'objet est un
    fichier régulier ; sinon, refuse et ferme sans lire. Repasse ensuite
    en mode bloquant standard pour la lecture elle-même (un fichier
    régulier ne bloque jamais en lecture). Lecture seule : ne crée jamais
    de répertoire."""
    _validate_relative_path(relative_path)
    walked = _walk_parent_inspect(root_fd, relative_path)
    if walked is None:
        return None
    parent_fd, basename, owns = walked
    try:
        try:
            fd = os.open(basename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise PathSafetyError(f"target is not a regular file (possible race with a special file): {relative_path}")
            # Fichier régulier confirmé : repasser en mode bloquant
            # standard ne change rien pour un régulier (jamais de
            # blocage en lecture), mais évite toute surprise sur des
            # systèmes où O_NONBLOCK affecterait aussi read().
            flags = os.get_blocking(fd)
            if not flags:
                os.set_blocking(fd, True)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        if owns:
            os.close(parent_fd)


def _write_all(fd: int, content: bytes) -> None:
    """`os.write()` peut écrire moins d'octets que demandé (POSIX ne
    garantit pas une écriture complète en un seul appel) — boucle jusqu'à
    écriture intégrale, sans quoi un fichier tronqué pourrait être publié
    silencieusement sous l'empreinte SHA-256 du contenu attendu, pas du
    contenu réellement écrit."""
    view = memoryview(content)
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written == 0:
            raise OSError("os.write made no progress (returned 0)")
        total += written


def stage_and_publish(
    root_fd: int,
    relative_path: str,
    content: bytes,
    created_directories: list[OwnedDirectory] | None = None,
) -> tuple[int, int, int]:
    """Écrit `content` de façon atomique, sans fenêtre TOCTOU.

    Toujours en mode « créer seulement, jamais remplacer » : la cible ne
    doit pas exister. (Le mode REGENERATE_VERIFIED du writer n'appelle
    jamais cette fonction sur un fichier déjà présent et conforme — dans
    ce cas, rien n'est écrit, cf. writer.py. Un fichier présent avec un
    contenu différent est refusé dès la phase d'inspection, avant que
    cette fonction ne soit jamais appelée.)

    Protocole : écrit dans un fichier temporaire (O_CREAT|O_EXCL, même
    répertoire), fsync, puis publie via `os.link()` — succès ou échec
    FileExistsError en un seul appel système atomique, sans lstat séparé
    de l'opération de publication (donc sans fenêtre entre vérification
    et action).

    Retourne (st_dev, st_ino, répertoires_créés) de l'objet publié, pour
    que l'appelant puisse vérifier l'ownership exact au rollback (jamais
    supprimer un objet qui ne correspond plus à ce qui a été publié)."""
    _validate_relative_path(relative_path)
    journal = created_directories if created_directories is not None else []
    parent_fd, basename, owns = _walk_parent_ensure(root_fd, relative_path, journal)
    tmp_name: str | None = None
    try:
        tmp_name = f".{basename}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent_fd)
        try:
            _write_all(fd, content)
            os.fsync(fd)
            published_stat = os.fstat(fd)
        finally:
            os.close(fd)

        try:
            os.link(tmp_name, basename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except FileExistsError as exc:
            raise PathSafetyError(f"target appeared during staging, refusing publish (no FORCE mode exists): {relative_path}") from exc
        finally:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass

        # Durabilité du nom lui-même (pas seulement du contenu déjà
        # fsync-é ci-dessus) : fsync du répertoire parent après la
        # publication du lien.
        os.fsync(parent_fd)

        # Le ctime est relu après link(), car la création du lien peut le
        # modifier. Il protège aussi contre la réutilisation rapide d'un inode.
        published_stat = os.lstat(basename, dir_fd=parent_fd)
        return published_stat.st_dev, published_stat.st_ino, published_stat.st_ctime_ns
    except BaseException:
        # Nettoyage local best-effort du temporaire. Les répertoires sont
        # déjà inscrits dans le journal partagé et seront compensés par le
        # writer, même si l'échec survient avant le retour de cette fonction.
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except (FileNotFoundError, OSError):
                pass
        raise
    finally:
        if owns:
            os.close(parent_fd)


def remove_leaf_if_owned(
    root_fd: int, relative_path: str, expected_dev: int, expected_ino: int,
    expected_ctime_ns: int,
) -> str:
    """Rollback d'un fichier créé par ce run. Ne supprime QUE si la cible
    actuelle correspond exactement (device, inode) à ce qui a été publié
    par ce run — sinon, un processus concurrent a pu remplacer le
    fichier entre publication et rollback, et le supprimer détruirait
    l'objet de ce tiers, pas le nôtre.

    Retourne "ROLLED_BACK", "ALREADY_ABSENT", ou "OWNERSHIP_LOST" (dans
    ce dernier cas, rien n'est supprimé)."""
    _validate_relative_path(relative_path)
    walked = _walk_parent_inspect(root_fd, relative_path)
    if walked is None:
        return "ALREADY_ABSENT"
    parent_fd, basename, owns = walked
    try:
        try:
            st = os.lstat(basename, dir_fd=parent_fd)
        except FileNotFoundError:
            return "ALREADY_ABSENT"
        if (st.st_dev, st.st_ino, st.st_ctime_ns) != (
            expected_dev, expected_ino, expected_ctime_ns
        ):
            return "OWNERSHIP_LOST"
        os.unlink(basename, dir_fd=parent_fd)
        return "ROLLED_BACK"
    finally:
        if owns:
            os.close(parent_fd)


def remove_directory_if_empty_and_owned(root_fd: int, owned: OwnedDirectory) -> str:
    """Rollback d'un répertoire créé par ce run, uniquement s'il est
    encore vide (jamais supprimer un répertoire qui contient quelque
    chose, même déposé par un tiers pendant la fenêtre du run)."""
    relative_dir_path = owned.relative_path
    _validate_relative_path(relative_dir_path)
    walked = _walk_parent_inspect(root_fd, relative_dir_path)
    if walked is None:
        return "ALREADY_ABSENT"
    parent_fd, basename, owns = walked
    try:
        try:
            st = os.lstat(basename, dir_fd=parent_fd)
            held = os.fstat(owned.fd)
            if (st.st_dev, st.st_ino) != (held.st_dev, held.st_ino):
                return "OWNERSHIP_LOST"
            os.rmdir(basename, dir_fd=parent_fd)
            os.fsync(parent_fd)
            return "ROLLED_BACK"
        except FileNotFoundError:
            return "ALREADY_ABSENT"
        except OSError as exc:
            if exc.errno == errno.ENOTEMPTY:
                return "NOT_EMPTY"
            return f"IO_ERROR:{exc.errno}"
    finally:
        if owns:
            os.close(parent_fd)
